"""Project and environment commands (orchestrator API)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from ..api import OrchestratorClient
from ..errors import CliError
from ..i18n import t
from ..options import argument, option
from ..output import emit, info, logs_output, machine_output, success
from ..settings import RuntimeSettings

console = Console()


class Stage(StrEnum):
    dev = "dev"
    staging = "staging"
    prod = "prod"


def _client(ctx: typer.Context) -> OrchestratorClient:
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    return OrchestratorClient(settings)


def _short_date(value: Any) -> str:
    text = str(value or "")
    return text[:19].replace("T", " ") if text else "-"


def _project_table(projects: list[dict[str, Any]]) -> None:
    table = Table()
    table.add_column(t("header.name"))
    table.add_column(t("header.template"))
    table.add_column(t("header.environments"))
    table.add_column(t("header.created"))
    for project in projects:
        environments = project.get("environments") or []
        stages = ", ".join(str(env.get("stage", "?")) for env in environments) or "-"
        table.add_row(
            str(project.get("name", "-")),
            str(project.get("template", "-")),
            stages,
            _short_date(project.get("created_at")),
        )
    console.print(table)


# ---------------------------------------------------------------------- projects


def project_create(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    template: str = option("opt.template", "odoo-module", "--template"),
) -> None:
    """Create a project."""
    project = _client(ctx).create_project(name, template)
    if machine_output():
        emit(project)
        return
    success(t("msg.project_created", name=project.get("name", name)))


def project_list(ctx: typer.Context) -> None:
    """List projects."""
    projects = _client(ctx).list_projects()
    if machine_output():
        emit(projects)
        return
    if not projects:
        info(t("msg.no_projects"))
        return
    _project_table(projects)


def project_delete(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    yes: bool = option("opt.yes", False, "--yes", "-y"),
    confirm: str | None = option("opt.confirm", None, "--confirm"),
    purge: bool = option("opt.purge", False, "--purge"),
) -> None:
    """Delete a project (use --purge to remove source and snapshots)."""
    expected = name
    if confirm is None:
        if machine_output() and not yes:
            raise CliError(t("error.confirmation_required"), code="confirmation_required")
        if not yes:
            typed = typer.prompt(t("prompt.type_project_name", name=name))
            if typed != expected:
                info(t("msg.cancelled"))
                return
        confirm = expected
    elif confirm != expected:
        raise CliError(t("error.confirmation_mismatch"), code="confirmation_mismatch")
    _client(ctx).delete_project(name, confirm, purge)
    if machine_output():
        emit({"deleted": True, "name": name})
        return
    success(t("msg.project_deleted", name=name))


# ------------------------------------------------------------------ environments


def deploy(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
    branch: str | None = option("opt.branch", None, "--branch"),
    iteration: str | None = option("opt.iteration", None, "--iteration"),
    confirm: str | None = option("opt.confirm", None, "--confirm"),
) -> None:
    """Deploy a project to an environment."""
    environment = _client(ctx).deploy(name, stage.value, branch, iteration, confirm)
    if machine_output():
        emit(environment)
        return
    success(
        t(
            "msg.env_deployed",
            name=name,
            stage=stage.value,
            url=environment.get("url", "-"),
            status=environment.get("status", "-"),
        )
    )


def _environment_action(
    ctx: typer.Context, name: str, stage: Stage, action: str, message_key: str
) -> None:
    environment = _client(ctx).environment_action(name, stage.value, action)
    if machine_output():
        emit(environment)
        return
    success(
        t(
            message_key,
            name=name,
            stage=stage.value,
            status=environment.get("status", "-"),
        )
    )


def env_stop(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
) -> None:
    """Stop an environment."""
    _environment_action(ctx, name, stage, "stop", "msg.env_stopped")


def env_start(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
) -> None:
    """Start an environment."""
    _environment_action(ctx, name, stage, "start", "msg.env_started")


def env_restart(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
) -> None:
    """Restart an environment."""
    _environment_action(ctx, name, stage, "restart", "msg.env_restarted")


def perform_rollback(
    client: OrchestratorClient,
    project: str,
    stage: str,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Shared CLI/MCP rollback policy: production needs the typed confirmation."""
    if stage == "prod":
        if confirm is None:
            raise CliError(t("error.prod_confirm_required"), code="confirmation_required")
        if confirm != project:
            raise CliError(t("error.confirmation_mismatch"), code="confirmation_mismatch")
    return client.rollback_environment(project, stage, confirm)


def perform_promote(
    client: OrchestratorClient,
    project: str,
    *,
    source_stage: str = "staging",
    confirm: str | None = None,
    neutralize: bool = True,
) -> dict[str, Any]:
    """Shared CLI/MCP policy: a promotion always needs the typed confirmation."""
    if confirm is None:
        raise CliError(t("error.prod_confirm_required"), code="confirmation_required")
    if confirm != project:
        raise CliError(t("error.confirmation_mismatch"), code="confirmation_mismatch")
    return client.promote_environment(project, source_stage, confirm, neutralize)


def promote(
    ctx: typer.Context,
    name: str = argument("arg.name"),
    source_stage: Stage = option("opt.source_stage", Stage.staging, "--source"),
    confirm: str | None = option("opt.confirm", None, "--confirm"),
    neutralize: bool = option("opt.neutralize", True, "--neutralize/--no-neutralize"),
) -> None:
    """Clone a source environment into production and neutralize the data."""
    if confirm is None:
        if machine_output():
            raise CliError(t("error.prod_confirm_required"), code="confirmation_required")
        confirm = typer.prompt(t("prompt.type_project_name", name=name))
        if confirm != name:
            info(t("msg.cancelled"))
            return
    environment = perform_promote(
        _client(ctx),
        name,
        source_stage=source_stage.value,
        confirm=confirm,
        neutralize=neutralize,
    )
    if machine_output():
        emit(
            {
                "project": name,
                "stage": environment.get("stage", "prod"),
                "source": source_stage.value,
                "status": environment.get("status", "-"),
                "neutralized": neutralize,
            }
        )
        return
    success(
        t(
            "msg.promoted",
            project=name,
            source=source_stage.value,
            status=environment.get("status", "-"),
        )
    )


def env_rollback(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
    confirm: str | None = option("opt.confirm", None, "--confirm"),
) -> None:
    """Roll an environment back to its last successful iteration."""
    if stage == Stage.prod and confirm is None:
        if machine_output():
            raise CliError(t("error.prod_confirm_required"), code="confirmation_required")
        confirm = typer.prompt(t("prompt.type_project_name", name=name))
        if confirm != name:
            info(t("msg.cancelled"))
            return
    environment = perform_rollback(_client(ctx), name, stage.value, confirm)
    if machine_output():
        emit(
            {
                "project": name,
                "stage": stage.value,
                "status": environment.get("status", "-"),
                "last_good_iteration": environment.get("last_good_iteration"),
            }
        )
        return
    success(
        t(
            "msg.env_rolled_back",
            name=name,
            stage=stage.value,
            iteration=environment.get("last_good_iteration", "-"),
            status=environment.get("status", "-"),
        )
    )


def env_delete(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
    yes: bool = option("opt.yes", False, "--yes", "-y"),
    confirm: str | None = option("opt.confirm", None, "--confirm"),
) -> None:
    """Delete an environment."""
    expected = f"{name}/{stage.value}"
    if confirm is None:
        if machine_output() and not yes:
            raise CliError(t("error.confirmation_required"), code="confirmation_required")
        if not yes:
            typed = typer.prompt(t("prompt.type_environment", value=expected))
            if typed != expected:
                info(t("msg.cancelled"))
                return
        confirm = expected
    elif confirm != expected:
        raise CliError(t("error.confirmation_mismatch"), code="confirmation_mismatch")
    _client(ctx).delete_environment(name, stage.value, confirm)
    if machine_output():
        emit({"deleted": True, "name": name, "stage": stage.value})
        return
    success(t("msg.env_deleted", name=name, stage=stage.value))


def logs(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
    tail: int = option("opt.tail", 200, "--tail", min=1, max=10000),
) -> None:
    """Show environment logs."""
    text = _client(ctx).logs(name, stage.value, tail)
    logs_output(text)


def backup(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
) -> None:
    """Back up an environment database."""
    payload = _client(ctx).backup(name, stage.value)
    if machine_output():
        emit(payload)
        return
    success(t("msg.backup_done", path=payload.get("path", "-")))
