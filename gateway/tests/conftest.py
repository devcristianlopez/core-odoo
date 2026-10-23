from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import BackendConfig
from app.factory import create_app
from app.security import TokenService


def make_config(
    *,
    auth_mode: str = "jwt",
    operations: list[str] | None = None,
    search_fields: list[str] | None = None,
    with_notes: bool = False,
) -> BackendConfig:
    raw: dict[str, Any] = {
        "app": "smoke-test",
        "odoo": {
            "url": "http://odoo:8069/",
            "db": "smoke_test",
            "api_key": "odoo-api-key",
            "user": "bot",
        },
        "auth": {
            "mode": auth_mode,
            "jwt_secret": "gateway-test-secret-gateway-test-secret",
            "issuer": "core-odoo",
        },
        "resources": [
            {
                "name": "contacts",
                "model": "res.partner",
                "fields": ["name", "email", "phone", "city"],
                "operations": operations or ["list", "read", "create", "update", "delete"],
                "domain": [["is_company", "=", False]],
                "search_fields": ["name", "email"] if search_fields is None else search_fields,
                "order": "name asc",
            }
        ],
    }
    if with_notes:
        raw["resources"].append(
            {
                "name": "tasks",
                "model": "project.task",
                "fields": ["name"],
                "operations": ["list"],
                "domain": [],
            }
        )
    return BackendConfig.model_validate(raw)


@dataclass
class OdooMock:
    requests: list[httpx.Request] = field(default_factory=list)
    routes: dict[str, httpx.Response] = field(default_factory=dict)
    search_read_pages: list[list[dict[str, Any]]] = field(default_factory=list)
    read_pages: list[list[dict[str, Any]]] = field(default_factory=list)
    authenticate_ok: bool = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path in self.routes:
            return self.routes[path]
        if path == "/web/session/authenticate":
            if not self.authenticate_ok:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "error": {"message": "Odoo Server Error", "data": {"message": "bad login"}},
                    },
                )
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": {"uid": 2}})
        if path == "/web/webclient/version_info":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "result": {"server_version": "20.0"}}
            )
        if path.endswith("/search_read"):
            page = self.search_read_pages.pop(0) if self.search_read_pages else []
            return httpx.Response(200, json=page)
        if path.endswith("/read"):
            page = self.read_pages.pop(0) if self.read_pages else []
            return httpx.Response(200, json=page)
        if path.endswith("/create"):
            return httpx.Response(200, json=7)
        if path.endswith("/write") or path.endswith("/unlink"):
            return httpx.Response(200, json=True)
        return httpx.Response(404, json={"message": "not found"})

    def bodies(self, suffix: str) -> list[dict[str, Any]]:
        return [
            json.loads(request.content)
            for request in self.requests
            if request.url.path.endswith(suffix)
        ]

    def request_to(self, suffix: str) -> httpx.Request:
        return next(request for request in self.requests if request.url.path.endswith(suffix))


@dataclass
class GatewayHarness:
    client: TestClient
    app: Any = field(repr=False)
    mock: OdooMock = field(repr=False)
    config: BackendConfig = field(repr=False)
    token: str = field(repr=False)

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def build_harness():
    def _build(config: BackendConfig | None = None) -> GatewayHarness:
        config = config or make_config()
        mock = OdooMock()
        app = create_app(config, odoo_transport=httpx.MockTransport(mock.handler))
        token = TokenService(config.auth).issue("tester")
        client = TestClient(app)
        return GatewayHarness(client=client, app=app, mock=mock, config=config, token=token)

    return _build


@pytest.fixture
def harness(build_harness) -> GatewayHarness:
    return build_harness()
