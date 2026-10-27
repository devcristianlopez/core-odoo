"""MCP ``promote_environment`` tool uses the shared CLI service helper."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core_odoo_cli import mcp_server


class StubClient:
    calls: list[tuple[str, str, str | None, bool]] = []

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def promote_environment(
        self,
        name: str,
        source_stage: str = "staging",
        confirm: str | None = None,
        neutralize: bool = True,
    ) -> dict[str, Any]:
        StubClient.calls.append((name, source_stage, confirm, neutralize))
        return {"project": name, "stage": "prod", "status": "running"}


@pytest.fixture(autouse=True)
def stub_api(monkeypatch: pytest.MonkeyPatch) -> type[StubClient]:
    StubClient.calls = []
    monkeypatch.setattr(mcp_server, "OrchestratorClient", StubClient)
    return StubClient


def _call(payload: dict[str, Any]) -> dict[str, Any]:
    server = mcp_server.build_server()
    result = asyncio.run(server.call_tool("promote_environment", payload))
    if isinstance(result, tuple):
        return result[1]
    raise AssertionError(f"expected structured tool output, got {result!r}")


def test_mcp_promote_returns_environment() -> None:
    payload = _call({"project": "demo", "confirm": "demo"})

    assert payload == {
        "ok": True,
        "environment": {"project": "demo", "stage": "prod", "status": "running"},
    }
    assert StubClient.calls == [("demo", "staging", "demo", True)]


def test_mcp_promote_requires_confirmation() -> None:
    payload = _call({"project": "demo"})

    assert payload["ok"] is False
    assert "confirm" in payload["error"].lower()
    assert StubClient.calls == []
