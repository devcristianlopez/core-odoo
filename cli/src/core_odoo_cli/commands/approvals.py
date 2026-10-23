"""Production deployment approval commands."""

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


def _table(requests: list[dict[str, Any]]) -> None:
    table = Table()
    table.add_column("ID")
    table.add_column("Project")
    table.add_column("Iteration")
    table.add_column("Status")
    table.add_column("Requested by")
    table.add_column("Created")
    for request in requests:
        table.add_row(
            str(request.get("id", "")),
            str(request.get("project", "")),
            str(request.get("iteration", "")),
            str(request.get("status", "")),
            str(request.get("requested_by", "")),
            str(request.get("created_at", ""))[:19].replace("T", " "),
        )
    console.print(table)


def list_requests(
    ctx: typer.Context,
    status: str | None = option("opt.status", None, "--status"),
) -> None:
    """List production deployment requests."""
    requests = _client(ctx).list_deploy_requests(status)
    if machine_output():
        emit(requests)
        return
    if not requests:
        console.print("No deployment requests.")
        return
    _table(requests)


def request_deploy(
    ctx: typer.Context,
    project: str = argument("arg.project"),
    iteration: str = option("opt.version", ..., "--iteration"),
    reason: str = option("opt.reason", "", "--reason"),
) -> None:
    """Request an admin approval for a production deploy."""
    result = _client(ctx).create_deploy_request(project, iteration, reason)
    if machine_output():
        emit(result)
        return
    success(f"Deployment request {result.get('id')} created (pending).")


def approve(
    ctx: typer.Context,
    request_id: int = argument("arg.request_id"),
) -> None:
    """Approve and execute a production deployment request (admin)."""
    result = _client(ctx).approve_deploy_request(request_id)
    if machine_output():
        emit(result)
        return
    success(f"Request {request_id} {result.get('status')}.")


def reject(
    ctx: typer.Context,
    request_id: int = argument("arg.request_id"),
) -> None:
    """Reject a production deployment request (admin)."""
    result = _client(ctx).reject_deploy_request(request_id)
    if machine_output():
        emit(result)
        return
    success(f"Request {request_id} {result.get('status')}.")
