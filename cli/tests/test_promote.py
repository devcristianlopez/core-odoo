"""``core-odoo promote`` command behaviour."""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from core_odoo_cli.commands import projects as project_commands
from core_odoo_cli.errors import CliError
from core_odoo_cli.main import app

runner = CliRunner()

ENVIRONMENT_PAYLOAD: dict[str, Any] = {
    "project": "demo",
    "stage": "prod",
    "status": "running",
    "url": "http://demo-prod.core-odoo.test",
}


class StubClient:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or ENVIRONMENT_PAYLOAD
        self.calls: list[tuple[str, str, str | None, bool, bool, str | None]] = []

    def promote_environment(
        self,
        name: str,
        source_stage: str = "staging",
        confirm: str | None = None,
        neutralize: bool = True,
        skip_smoke: bool = False,
        iteration: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((name, source_stage, confirm, neutralize, skip_smoke, iteration))
        return self.payload


@pytest.fixture()
def stub_client(monkeypatch: pytest.MonkeyPatch) -> StubClient:
    stub = StubClient()
    monkeypatch.setattr(project_commands, "_client", lambda ctx: stub)
    return stub


def test_promote_json_output(stub_client: StubClient) -> None:
    result = runner.invoke(
        app, ["--lang", "en", "--json", "promote", "demo", "--confirm", "demo"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "project": "demo",
        "stage": "prod",
        "source": "staging",
        "status": "running",
        "neutralized": True,
    }
    assert stub_client.calls == [("demo", "staging", "demo", True, False, None)]


def test_promote_requires_confirm_in_machine_mode(stub_client: StubClient) -> None:
    result = runner.invoke(app, ["--lang", "en", "--json", "promote", "demo"])

    assert result.exit_code != 0
    assert stub_client.calls == []
    assert isinstance(result.exception, CliError)
    assert "confirm" in result.exception.message.lower()


def test_promote_forwards_source_and_no_neutralize(stub_client: StubClient) -> None:
    result = runner.invoke(
        app,
        [
            "--lang",
            "en",
            "--json",
            "promote",
            "demo",
            "--source",
            "dev",
            "--no-neutralize",
            "--confirm",
            "demo",
        ],
    )

    assert result.exit_code == 0, result.output
    assert stub_client.calls == [("demo", "dev", "demo", False, False, None)]
    assert json.loads(result.stdout)["neutralized"] is False
