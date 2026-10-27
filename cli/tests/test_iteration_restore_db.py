"""``core-odoo iteration restore-db`` command behaviour."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from typer.testing import CliRunner

from core_odoo_cli.commands import iterations as iteration_commands
from core_odoo_cli.errors import CliError
from core_odoo_cli.main import app

runner = CliRunner()

ENVIRONMENT_PAYLOAD: dict[str, Any] = {
    "project": "demo",
    "stage": "dev",
    "status": "running",
    "url": "http://demo-dev.core-odoo.test",
    "last_good_iteration": "0.1.0",
}


class StubClient:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or ENVIRONMENT_PAYLOAD
        self.calls: list[tuple[str, str, str, str | None]] = []

    def restore_iteration_database(
        self,
        name: str,
        version: str,
        stage: str = "dev",
        confirm: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((name, version, stage, confirm))
        return self.payload


@pytest.fixture()
def stub_client(monkeypatch: pytest.MonkeyPatch) -> StubClient:
    stub = StubClient()
    monkeypatch.setattr(iteration_commands, "_client", lambda ctx: stub)
    return stub


def test_restore_db_json_output(stub_client: StubClient) -> None:
    result = runner.invoke(
        app, ["--lang", "en", "--json", "iteration", "restore-db", "demo", "0.1.0"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "project": "demo",
        "version": "0.1.0",
        "stage": "dev",
        "status": "running",
    }
    assert "\x1b[" not in result.stdout
    assert stub_client.calls == [("demo", "0.1.0", "dev", None)]


def test_restore_db_human_output_names_the_version(stub_client: StubClient) -> None:
    result = runner.invoke(
        app, ["--lang", "en", "iteration", "restore-db", "demo", "0.1.0", "--stage", "dev"]
    )

    assert result.exit_code == 0, result.output
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "restored from 0.1.0" in plain
    assert stub_client.calls == [("demo", "0.1.0", "dev", None)]


def test_prod_restore_db_requires_confirm_before_http(stub_client: StubClient) -> None:
    result = runner.invoke(
        app,
        ["--lang", "en", "--json", "iteration", "restore-db", "demo", "0.1.0", "--stage", "prod"],
    )

    assert result.exit_code != 0
    assert stub_client.calls == []
    assert isinstance(result.exception, CliError)
    assert "confirm" in result.exception.message.lower()


def test_prod_restore_db_forwards_confirm(stub_client: StubClient) -> None:
    stub_client.payload = {**ENVIRONMENT_PAYLOAD, "stage": "prod"}
    result = runner.invoke(
        app,
        [
            "--lang",
            "en",
            "--json",
            "iteration",
            "restore-db",
            "demo",
            "0.1.0",
            "--stage",
            "prod",
            "--confirm",
            "demo",
        ],
    )

    assert result.exit_code == 0, result.output
    assert stub_client.calls == [("demo", "0.1.0", "prod", "demo")]
