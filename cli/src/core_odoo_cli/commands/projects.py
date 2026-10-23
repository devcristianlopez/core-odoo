"""Project and environment commands (orchestrator API)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import typer
from rich.console import Console
from rich.prompt import Confirm
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
) -> None:
    """Delete a project."""
    if not yes:
        if machine_output():
            raise CliError(t("error.confirmation_required"), code="confirmation_required")
        if not Confirm.ask(t("prompt.confirm_delete", name=name), default=False):
            info(t("msg.cancelled"))
            return
    _client(ctx).delete_project(name)
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
) -> None:
    """Deploy a project to an environment."""
    environment = _client(ctx).deploy(name, stage.value, branch)
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


def env_delete(
    ctx: typer.Context,
    name: str = argument("arg.name", ...),
    stage: Stage = option("opt.stage", ..., "--stage"),
    yes: bool = option("opt.yes", False, "--yes", "-y"),
) -> None:
    """Delete an environment."""
    if not yes:
        if machine_output():
            raise CliError(t("error.confirmation_required"), code="confirmation_required")
        if not Confirm.ask(
            t("prompt.confirm_delete_env", name=name, stage=stage.value), default=False
        ):
            info(t("msg.cancelled"))
            return
    _client(ctx).delete_environment(name, stage.value)
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
