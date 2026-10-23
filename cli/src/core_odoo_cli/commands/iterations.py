"""Project iteration commands."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from ..api import OrchestratorClient
from ..options import argument, option
from ..output import emit, machine_output, success
from ..settings import RuntimeSettings

console = Console()


def _client(ctx: typer.Context) -> OrchestratorClient:
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    return OrchestratorClient(settings)


def _table(iterations: list[dict[str, Any]]) -> None:
    table = Table()
    table.add_column("Version")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Stage")
    table.add_column("Created")
    for iteration in iterations:
        table.add_row(
            str(iteration.get("version", "")),
            str(iteration.get("title", "")),
            str(iteration.get("status", "")),
            str(iteration.get("stage") or "-"),
            str(iteration.get("created_at", ""))[:19].replace("T", " "),
        )
    console.print(table)


def list_iterations(
    ctx: typer.Context,
    project: str = argument("arg.project"),
) -> None:
    """List project iterations."""
    iterations = _client(ctx).list_iterations(project)
    if machine_output():
        emit(iterations)
        return
    if not iterations:
        console.print("No iterations yet.")
        return
    _table(iterations)


def create_iteration(
    ctx: typer.Context,
    project: str = argument("arg.project"),
    version: str = option("opt.version", ..., "--version"),
    title: str | None = option("opt.title", None, "--title"),
    notes: str = option("opt.notes", "", "--notes"),
    branch: str | None = option("opt.branch", None, "--branch"),
    commit_sha: str | None = option("opt.commit", None, "--commit"),
    modules: str = option("opt.modules", "", "--modules"),
) -> None:
    """Snapshot the current project source as a new iteration."""
    module_list = [item.strip() for item in modules.split(",") if item.strip()]
    iteration = _client(ctx).create_iteration(
        project,
        version=version,
        title=title or version,
        notes=notes,
        branch=branch,
        commit_sha=commit_sha,
        modules=module_list or None,
    )
    if machine_output():
        emit(iteration)
        return
    success(f"Iteration {iteration.get('version')} created.")


def restore_iteration(
    ctx: typer.Context,
    project: str = argument("arg.project"),
    version: str = argument("arg.version"),
) -> None:
    """Restore a project's source from an iteration snapshot."""
    iteration = _client(ctx).restore_iteration(project, version)
    if machine_output():
        emit(iteration)
        return
    success(f"Iteration {iteration.get('version')} restored.")
