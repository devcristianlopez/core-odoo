"""MCP ``rollback_environment`` tool uses the shared CLI service helper."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core_odoo_cli import mcp_server


class StubClient:
    calls: list[tuple[str, str, str | None]] = []

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def rollback_environment(
        self, name: str, stage: str, confirm: str | None = None
    ) -> dict[str, Any]:
        StubClient.calls.append((name, stage, confirm))
        return {
            "project": name,
            "stage": stage,
            "status": "running",
            "last_good_iteration": "0.1.0",
        }


@pytest.fixture(autouse=True)
def stub_api(monkeypatch: pytest.MonkeyPatch) -> type[StubClient]:
    StubClient.calls = []
    monkeypatch.setattr(mcp_server, "OrchestratorClient", StubClient)
    return StubClient


def _call(payload: dict[str, Any]) -> dict[str, Any]:
    server = mcp_server.build_server()
    result = asyncio.run(server.call_tool("rollback_environment", payload))
    if isinstance(result, tuple):
        return result[1]
    raise AssertionError(f"expected structured tool output, got {result!r}")


def test_mcp_rollback_returns_environment() -> None:
    payload = _call({"project": "demo"})

    assert payload == {
        "ok": True,
        "environment": {
            "project": "demo",
            "stage": "dev",
            "status": "running",
            "last_good_iteration": "0.1.0",
        },
    }
    assert StubClient.calls == [("demo", "dev", None)]


def test_mcp_rollback_enforces_prod_confirmation() -> None:
    payload = _call({"project": "demo", "stage": "prod"})

    assert payload["ok"] is False
    assert "confirm" in payload["error"].lower()
    assert StubClient.calls == []
