"""Code generators for Odoo modules and BFF resources."""

from __future__ import annotations

from pathlib import Path

import typer

from ..errors import CliError
from ..generator import GeneratorError
from ..generator import generate_module as build_module
from ..generator import generate_resource as build_resource
from ..i18n import t
from ..options import argument, option
from ..output import emit, info, machine_output, success
from ..settings import RuntimeSettings


def _projects_root(settings: RuntimeSettings) -> Path:
    raw = settings.values.get("CORE_PROJECTS_DIR", "./projects")
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (settings.repo_root / path).resolve()


def _project_dir(settings: RuntimeSettings, project: str) -> Path:
    root = _projects_root(settings)
    path = root / project
    if not path.is_dir():
        raise CliError(
            t("error.project_missing", project=project, projects=str(root)),
            code="project_missing",
        )
    return path


def module(
    ctx: typer.Context,
    project: str = argument("arg.project"),
    name: str = argument("arg.module"),
    title: str | None = option("opt.module_title", None, "--title"),
    model: str = option("opt.model", "record", "--model"),
    fields: str = option("opt.fields", "name:char", "--fields"),
    force: bool = option("opt.force", False, "--force"),
) -> None:
    """Generate an Odoo 20 module with model, ACL, views and tests."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    project_dir = _project_dir(settings, project)
    module_title = title or name.replace("_", " ").title()
    try:
        result = build_module(project_dir, name, module_title, model, fields, force=force)
    except GeneratorError as exc:
        raise CliError(str(exc), code="generate_failed") from exc
    if machine_output():
        emit(result)
        return
    success(t("msg.module_generated", module=name, path=result["path"]))
    info(t("msg.module_hint", model=result["model"]))


def resource(
    ctx: typer.Context,
    project: str = argument("arg.project"),
    name: str = argument("arg.resource"),
    model: str = option("opt.model", "", "--model"),
    fields: str = option("opt.fields", "name", "--fields"),
    operations: str = option("opt.operations", "list,read,create,update,delete", "--operations"),
    search_fields: str = option("opt.search_fields", "name", "--search-fields"),
    order: str | None = option("opt.order", None, "--order"),
) -> None:
    """Add or replace a resource in the project's backend.yaml."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    project_dir = _project_dir(settings, project)
    if not model:
        raise CliError(t("error.model_required"), code="model_required")
    try:
        result = build_resource(
            project_dir,
            name,
            model,
            fields,
            operations=operations,
            search_fields=search_fields,
            order=order,
        )
    except GeneratorError as exc:
        raise CliError(str(exc), code="generate_failed") from exc
    if machine_output():
        emit(result)
        return
    success(t("msg.resource_generated", resource=name, path=result["path"]))
