"""Project validation command."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..checker import check_project
from ..i18n import t
from ..options import argument, option
from ..output import emit, fail, machine_output, success
from ..project_paths import project_dir as find_project_dir
from ..settings import RuntimeSettings

console = Console()


def check(
    ctx: typer.Context,
    project: str = argument("arg.project"),
    stage: str = option("opt.stage", "dev", "--stage"),
    catalog: bool = option("opt.catalog", False, "--catalog"),
    frontend: bool = option("opt.frontend", False, "--frontend"),
) -> None:
    """Validate a project before deploying it."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    project_path = find_project_dir(settings, project)
    result = check_project(
        project_path,
        project,
        stage=stage,
        catalog=catalog,
        frontend=frontend,
    )
    if machine_output():
        emit(result)
    else:
        table = Table(title=t("msg.check_title", project=project))
        table.add_column(t("header.level"))
        table.add_column(t("header.check"))
        table.add_column(t("header.message"))
        for issue in result["errors"] + result["warnings"]:
            table.add_row(
                "ERROR" if issue["level"] == "error" else "WARN",
                str(issue.get("code", "")),
                str(issue.get("message", "")),
            )
        console.print(table)
        if result["ok"]:
            success(t("msg.check_ok", project=project))
        else:
            fail(t("msg.check_failed", count=len(result["errors"])))
    if not result["ok"]:
        raise typer.Exit(1)
