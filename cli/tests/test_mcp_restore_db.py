"""MCP ``restore_iteration_db`` tool uses the shared CLI service helper."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core_odoo_cli import mcp_server


class StubClient:
    calls: list[tuple[str, str, str, str | None]] = []

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def restore_iteration_database(
        self,
        name: str,
        version: str,
        stage: str = "dev",
        confirm: str | None = None,
    ) -> dict[str, Any]:
        StubClient.calls.append((name, version, stage, confirm))
        return {"project": name, "stage": stage, "status": "running"}


@pytest.fixture(autouse=True)
def stub_api(monkeypatch: pytest.MonkeyPatch) -> type[StubClient]:
    StubClient.calls = []
    monkeypatch.setattr(mcp_server, "OrchestratorClient", StubClient)
    return StubClient


def _call(payload: dict[str, Any]) -> dict[str, Any]:
    server = mcp_server.build_server()
    result = asyncio.run(server.call_tool("restore_iteration_db", payload))
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    raise AssertionError(f"expected structured tool output, got {result!r}")


def test_mcp_restore_db_returns_environment() -> None:
    payload = _call({"project": "demo", "version": "0.1.0"})

    assert payload == {
        "ok": True,
        "environment": {"project": "demo", "stage": "dev", "status": "running"},
    }
    assert StubClient.calls == [("demo", "0.1.0", "dev", None)]


def test_mcp_restore_db_enforces_prod_confirmation() -> None:
    payload = _call({"project": "demo", "version": "0.1.0", "stage": "prod"})

    assert payload["ok"] is False
    assert "confirm" in payload["error"].lower()
    assert StubClient.calls == []
