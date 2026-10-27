"""HTTP client contract: request shapes, auth header and error mapping."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from core_odoo_cli import api
from core_odoo_cli.errors import CliError
from core_odoo_cli.settings import RuntimeSettings


class FakeClient:
    """Minimal stand-in for ``httpx.Client`` recording every call."""

    instances: list[FakeClient] = []
    responses: list[httpx.Response] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        FakeClient.instances.append(self)

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self.calls.append({"method": method, "path": path, "json": json, "params": params})
        assert FakeClient.responses, f"unexpected request {method} {path}"
        return FakeClient.responses.pop(0)


@pytest.fixture()
def settings(tmp_path: Path) -> RuntimeSettings:
    return RuntimeSettings(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        config_file=tmp_path / "core-odoo.yaml",
        values={
            "CORE_API_URL": "http://localhost:8080",
            "CORE_API_TOKEN": "secret-token",
        },
    )


@pytest.fixture(autouse=True)
def fake_http(monkeypatch: pytest.MonkeyPatch) -> type[FakeClient]:
    FakeClient.instances = []
    FakeClient.responses = []
    monkeypatch.setattr(api.httpx, "Client", FakeClient)
    return FakeClient


def _ok(payload: Any) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_client_requires_token(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        config_file=tmp_path / "core-odoo.yaml",
        values={"CORE_API_URL": "http://localhost:8080"},
    )
    with pytest.raises(CliError) as excinfo:
        api.OrchestratorClient(settings)
    assert excinfo.value.code == "api_token_missing"


def test_client_rejects_invalid_url(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        repo_root=tmp_path,
        env_file=tmp_path / ".env",
        config_file=tmp_path / "core-odoo.yaml",
        values={"CORE_API_URL": "ftp://example.test", "CORE_API_TOKEN": "t"},
    )
    with pytest.raises(CliError) as excinfo:
        api.OrchestratorClient(settings)
    assert excinfo.value.code == "api_url"


def test_project_crud_shapes(settings: RuntimeSettings) -> None:
    FakeClient.responses = [
        _ok({"name": "demo"}),
        _ok([{"name": "demo"}]),
        _ok({"deleted": True}),
    ]
    client = api.OrchestratorClient(settings)

    assert client.create_project("demo", "odoo-module") == {"name": "demo"}
    assert client.list_projects() == [{"name": "demo"}]
    assert client.delete_project("demo", "demo") == {"deleted": True}

    calls = [call for instance in FakeClient.instances for call in instance.calls]
    assert calls[0] == {
        "method": "POST",
        "path": "/projects",
        "json": {"name": "demo", "template": "odoo-module"},
        "params": None,
    }
    assert calls[1]["method"] == "GET"
    assert calls[1]["path"] == "/projects"
    assert calls[2]["method"] == "DELETE"
    assert calls[2]["path"] == "/projects/demo"

    client_kwargs = FakeClient.instances[0].kwargs
    assert client_kwargs["base_url"] == "http://localhost:8080/api/v1"
    assert client_kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_environment_endpoints(settings: RuntimeSettings) -> None:
    FakeClient.responses = [
        _ok({"stage": "dev", "status": "running"}),
        _ok({"stage": "dev", "status": "stopped"}),
        _ok({"stage": "dev"}),
        _ok({"logs": "line"}),
        _ok({"path": "/tmp/backup.zip"}),
    ]
    client = api.OrchestratorClient(settings)

    client.deploy("demo", "dev", "main")
    client.environment_action("demo", "dev", "stop")
    client.delete_environment("demo", "dev", "demo/dev")
    assert client.logs("demo", "dev", 50) == "line"
    assert client.backup("demo", "dev") == {"path": "/tmp/backup.zip"}

    calls = [call for instance in FakeClient.instances for call in instance.calls]
    assert calls[0]["path"] == "/projects/demo/deploy"
    assert calls[0]["json"] == {"stage": "dev", "branch": "main"}
    assert calls[1]["path"] == "/projects/demo/environments/dev/stop"
    assert calls[2]["method"] == "DELETE"
    assert calls[2]["path"] == "/projects/demo/environments/dev"
    assert calls[3]["params"] == {"tail": 50}
    assert calls[4]["method"] == "POST"
    assert calls[4]["path"] == "/projects/demo/environments/dev/backup"


def test_rollback_omits_body_without_confirm(settings: RuntimeSettings) -> None:
    FakeClient.responses = [
        _ok({"last_good_iteration": "0.1.0"}),
        _ok({"last_good_iteration": "0.1.0"}),
    ]
    client = api.OrchestratorClient(settings)

    assert client.rollback_environment("demo", "dev") == {"last_good_iteration": "0.1.0"}
    assert client.rollback_environment("demo", "prod", "demo") == {"last_good_iteration": "0.1.0"}

    calls = [call for instance in FakeClient.instances for call in instance.calls]
    assert calls[0] == {
        "method": "POST",
        "path": "/projects/demo/environments/dev/rollback",
        "json": None,
        "params": None,
    }
    assert calls[1]["path"] == "/projects/demo/environments/prod/rollback"
    assert calls[1]["json"] == {"confirm": "demo"}


def test_base_url_keeps_existing_api_prefix(settings: RuntimeSettings) -> None:
    prefixed = RuntimeSettings(
        repo_root=settings.repo_root,
        env_file=settings.env_file,
        config_file=settings.config_file,
        values={
            "CORE_API_URL": "https://core.example.test/api/v1/",
            "CORE_API_TOKEN": "t",
        },
    )
    FakeClient.responses = [_ok([])]
    api.OrchestratorClient(prefixed).list_projects()
    assert FakeClient.instances[0].kwargs["base_url"] == "https://core.example.test/api/v1"


def test_error_envelope_is_surfaced(settings: RuntimeSettings) -> None:
    FakeClient.responses = [
        httpx.Response(
            404,
            json={"error": {"code": "not_found", "message": "Project missing"}},
        )
    ]
    with pytest.raises(CliError) as excinfo:
        api.OrchestratorClient(settings).delete_project("missing", "missing")
    assert excinfo.value.code == "http_error"
    assert "Project missing" in excinfo.value.message


def test_fastapi_validation_error_is_surfaced(settings: RuntimeSettings) -> None:
    FakeClient.responses = [
        httpx.Response(
            422,
            json={
                "detail": [
                    {"loc": ["body", "stage"], "msg": "invalid stage"},
                ]
            },
        )
    ]
    with pytest.raises(CliError) as excinfo:
        api.OrchestratorClient(settings).deploy("demo", "dev")
    assert "body.stage: invalid stage" in excinfo.value.message


def test_network_failures_are_wrapped(
    settings: RuntimeSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenClient(FakeClient):
        def request(self, *args: Any, **kwargs: Any) -> httpx.Response:
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(api.httpx, "Client", BrokenClient)
    with pytest.raises(CliError) as excinfo:
        api.OrchestratorClient(settings).list_projects()
    assert excinfo.value.code == "api_unreachable"
