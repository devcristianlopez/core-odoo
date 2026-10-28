"""MCP ``deploy_project`` forwards the module list to the orchestrator."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core_odoo_cli import mcp_server


class StubClient:
    calls: list[tuple[Any, ...]] = []

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def deploy(self, *args: Any) -> dict[str, Any]:
        StubClient.calls.append(args)
        return {"project": "demo", "stage": "dev", "status": "running"}


@pytest.fixture(autouse=True)
def stub_api(monkeypatch: pytest.MonkeyPatch) -> type[StubClient]:
    StubClient.calls = []
    monkeypatch.setattr(mcp_server, "OrchestratorClient", StubClient)
    return StubClient


def _call(payload: dict[str, Any]) -> dict[str, Any]:
    server = mcp_server.build_server()
    result = asyncio.run(server.call_tool("deploy_project", payload))
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    raise AssertionError(f"expected structured tool output, got {result!r}")


def test_mcp_deploy_forwards_modules() -> None:
    payload = _call(
        {"project": "demo", "stage": "dev", "modules": ["salon", "account", "stock"]}
    )

    assert payload["ok"] is True
    assert StubClient.calls == [
        ("demo", "dev", None, None, None, ["salon", "account", "stock"])
    ]


def test_mcp_deploy_without_modules_keeps_none() -> None:
    _call({"project": "demo"})

    assert StubClient.calls == [("demo", "dev", None, None, None, None)]
