"""``core-odoo deploy`` reports when the environment was auto-rolled back."""

from __future__ import annotations

import re
from typing import Any

import pytest
from typer.testing import CliRunner

from core_odoo_cli.commands import projects as project_commands
from core_odoo_cli.main import app

runner = CliRunner()

PAYLOAD: dict[str, Any] = {
    "project": "demo",
    "stage": "dev",
    "status": "running",
    "url": "http://demo-dev.core-odoo.test",
    "last_good_iteration": "0.1.0",
    "auto_rolled_back": True,
}


class StubClient:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or PAYLOAD
        self.calls: list[tuple[Any, ...]] = []

    def deploy(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((args, kwargs))
        return self.payload


@pytest.fixture()
def stub_client(monkeypatch: pytest.MonkeyPatch) -> StubClient:
    stub = StubClient()
    monkeypatch.setattr(project_commands, "_client", lambda ctx: stub)
    return stub


def test_deploy_warns_about_the_auto_rollback(stub_client: StubClient) -> None:
    result = runner.invoke(app, ["--lang", "en", "deploy", "demo", "--stage", "dev"])

    assert result.exit_code == 0, result.output
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "rolled back to iteration 0.1.0" in plain
    assert len(stub_client.calls) == 1
