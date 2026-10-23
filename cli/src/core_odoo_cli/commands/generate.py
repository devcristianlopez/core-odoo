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
from ..project_paths import project_dir as find_project_dir
from ..sdk import SdkError, generate_sdk
from ..settings import RuntimeSettings


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
    project_path = find_project_dir(settings, project)
    module_title = title or name.replace("_", " ").title()
    try:
        result = build_module(project_path, name, module_title, model, fields, force=force)
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
    project_path = find_project_dir(settings, project)
    if not model:
        raise CliError(t("error.model_required"), code="model_required")
    try:
        result = build_resource(
            project_path,
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


def sdk(
    ctx: typer.Context,
    project: str = argument("arg.project"),
    stage: str = option("opt.stage", "dev", "--stage"),
    output: str | None = option("opt.output", None, "--output"),
    force: bool = option("opt.force", False, "--force"),
) -> None:
    """Generate a typed TypeScript client from backend.yaml."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    project_path = find_project_dir(settings, project)
    target = Path(output).expanduser() if output else None
    if target is not None and not target.is_absolute():
        target = project_path / target
    try:
        result = generate_sdk(
            project_path,
            project,
            stage=stage,
            output=target,
            force=force,
        )
    except SdkError as exc:
        raise CliError(str(exc), code="generate_failed") from exc
    if machine_output():
        emit(result)
        return
    success(t("msg.sdk_generated", path=result["path"]))
