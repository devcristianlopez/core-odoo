"""``core-odoo env rollback`` command behaviour."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from typer.testing import CliRunner

from core_odoo_cli.commands import projects as project_commands
from core_odoo_cli.errors import CliError
from core_odoo_cli.main import app

runner = CliRunner()

ROLLBACK_PAYLOAD: dict[str, Any] = {
    "project": "demo",
    "stage": "dev",
    "status": "running",
    "url": "http://demo-dev.core-odoo.test",
    "last_good_iteration": "0.1.0",
}


class StubClient:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or ROLLBACK_PAYLOAD
        self.calls: list[tuple[str, str, str | None]] = []

    def rollback_environment(
        self, name: str, stage: str, confirm: str | None = None
    ) -> dict[str, Any]:
        self.calls.append((name, stage, confirm))
        return self.payload


@pytest.fixture()
def stub_client(monkeypatch: pytest.MonkeyPatch) -> StubClient:
    stub = StubClient()
    monkeypatch.setattr(project_commands, "_client", lambda ctx: stub)
    return stub


def test_rollback_json_output(stub_client: StubClient) -> None:
    result = runner.invoke(
        app, ["--lang", "en", "--json", "env", "rollback", "demo", "--stage", "dev"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "project": "demo",
        "stage": "dev",
        "status": "running",
        "last_good_iteration": "0.1.0",
    }
    assert "\x1b[" not in result.stdout
    assert stub_client.calls == [("demo", "dev", None)]


def test_rollback_human_output_names_the_iteration(stub_client: StubClient) -> None:
    result = runner.invoke(app, ["--lang", "en", "env", "rollback", "demo", "--stage", "dev"])

    assert result.exit_code == 0, result.output
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "rolled back to iteration 0.1.0" in plain
    assert stub_client.calls == [("demo", "dev", None)]


def test_prod_rollback_requires_confirm_before_http(
    stub_client: StubClient,
) -> None:
    result = runner.invoke(
        app, ["--lang", "en", "--json", "env", "rollback", "demo", "--stage", "prod"]
    )

    assert result.exit_code != 0
    assert stub_client.calls == []
    assert isinstance(result.exception, CliError)
    assert "confirm" in result.exception.message.lower()


def test_prod_rollback_forwards_confirm(stub_client: StubClient) -> None:
    stub_client.payload = {**ROLLBACK_PAYLOAD, "stage": "prod"}
    result = runner.invoke(
        app,
        [
            "--lang",
            "en",
            "--json",
            "env",
            "rollback",
            "demo",
            "--stage",
            "prod",
            "--confirm",
            "demo",
        ],
    )

    assert result.exit_code == 0, result.output
    assert stub_client.calls == [("demo", "prod", "demo")]
