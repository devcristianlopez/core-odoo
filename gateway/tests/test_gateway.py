from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from app.security import TokenService

from .conftest import GatewayHarness, make_config


def test_health_reports_odoo(harness: GatewayHarness) -> None:
    response = harness.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "odoo": True,
        "odoo_version": "20.0",
        "version": "0.1.0",
    }


def test_health_degrades_when_odoo_is_down(harness: GatewayHarness) -> None:
    harness.mock.routes["/web/webclient/version_info"] = httpx.Response(502)
    response = harness.client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["odoo"] is False


def test_login_success(harness: GatewayHarness) -> None:
    response = harness.client.post("/auth/login", json={"login": "alice", "password": "secret"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"

    body = harness.mock.bodies("/web/session/authenticate")[0]
    assert body["params"] == {"db": "smoke_test", "login": "alice", "password": "secret"}

    me = harness.client.get("/api/contacts", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


def test_login_failure_uses_error_envelope(harness: GatewayHarness) -> None:
    harness.mock.authenticate_ok = False
    response = harness.client.post("/auth/login", json={"login": "alice", "password": "wrong"})
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "unauthorized", "message": "invalid credentials"}}


def test_login_validation_error(harness: GatewayHarness) -> None:
    response = harness.client.post("/auth/login", json={"login": "alice"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert any(item["loc"][-1] == "password" for item in error["details"])


def test_resource_requires_token(harness: GatewayHarness) -> None:
    response = harness.client.get("/api/contacts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_resource_rejects_bad_token(harness: GatewayHarness) -> None:
    response = harness.client.get("/api/contacts", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


def test_auth_mode_none_allows_anonymous(build_harness) -> None:
    harness = build_harness(make_config(auth_mode="none"))
    response = harness.client.get("/api/contacts")
    assert response.status_code == 200
    login = harness.client.post("/auth/login", json={"login": "any", "password": "x"})
    assert login.status_code == 200


def test_list_uses_declared_domain_fields_and_order(harness: GatewayHarness) -> None:
    harness.mock.search_read_pages = [[{"id": 1, "name": "Acme", "email": "a@example.com"}]]
    response = harness.client.get("/api/contacts", headers=harness.auth_headers)
    assert response.status_code == 200
    assert response.json() == [{"id": 1, "name": "Acme", "email": "a@example.com"}]

    request = harness.mock.request_to("/res.partner/search_read")
    assert request.headers["Authorization"] == "bearer odoo-api-key"
    assert request.headers["X-Odoo-Database"] == "smoke_test"
    body = harness.mock.bodies("/res.partner/search_read")[0]
    assert body["domain"] == [["is_company", "=", False]]
    assert body["fields"] == ["id", "name", "email", "phone", "city"]
    assert body["order"] == "name asc"
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_list_search_and_pagination(harness: GatewayHarness) -> None:
    response = harness.client.get(
        "/api/contacts",
        params={"q": "acme", "limit": 5, "offset": 10, "order": "email desc"},
        headers=harness.auth_headers,
    )
    assert response.status_code == 200
    body = harness.mock.bodies("/res.partner/search_read")[0]
    assert body["domain"] == [
        ["is_company", "=", False],
        "|",
        ["name", "ilike", "%acme%"],
        ["email", "ilike", "%acme%"],
    ]
    assert body["limit"] == 5
    assert body["offset"] == 10
    assert body["order"] == "email desc"


def test_list_rejects_unknown_order_field(harness: GatewayHarness) -> None:
    response = harness.client.get(
        "/api/contacts", params={"order": "password desc"}, headers=harness.auth_headers
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
    assert "not allowed" in response.json()["error"]["message"]


def test_search_without_search_fields_is_rejected(build_harness) -> None:
    harness = build_harness(make_config(search_fields=[]))
    response = harness.client.get("/api/contacts", params={"q": "x"}, headers=harness.auth_headers)
    assert response.status_code == 400
    assert "not enabled" in response.json()["error"]["message"]


def test_read_returns_record(harness: GatewayHarness) -> None:
    harness.mock.search_read_pages = [[{"id": 3, "name": "Globex"}]]
    response = harness.client.get("/api/contacts/3", headers=harness.auth_headers)
    assert response.status_code == 200
    assert response.json() == {"id": 3, "name": "Globex"}
    body = harness.mock.bodies("/res.partner/search_read")[0]
    assert body == {
        "domain": [["id", "=", 3], ["is_company", "=", False]],
        "fields": ["id", "name", "email", "phone", "city"],
        "limit": 1,
        "offset": 0,
    }


def test_read_missing_record(harness: GatewayHarness) -> None:
    harness.mock.search_read_pages = [[]]
    response = harness.client.get("/api/contacts/99", headers=harness.auth_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_by_id_operations_enforce_declared_domain(harness: GatewayHarness) -> None:
    harness.mock.search_read_pages = [[], []]
    assert harness.client.get("/api/contacts/99", headers=harness.auth_headers).status_code == 404
    assert (
        harness.client.patch(
            "/api/contacts/99", json={"phone": "555"}, headers=harness.auth_headers
        ).status_code
        == 404
    )
    for body in harness.mock.bodies("/res.partner/search_read"):
        assert body["domain"][0] == ["id", "=", 99]
        assert body["domain"][1] == ["is_company", "=", False]
    assert harness.mock.bodies("/res.partner/write") == []


def test_create_validates_fields(harness: GatewayHarness) -> None:
    response = harness.client.post(
        "/api/contacts",
        json={"name": "Acme", "password": "hunter2"},
        headers=harness.auth_headers,
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["error"]["message"]
    assert harness.mock.bodies("/res.partner/create") == []


def test_create_success(harness: GatewayHarness) -> None:
    response = harness.client.post(
        "/api/contacts",
        json={"name": "Acme", "email": "a@example.com"},
        headers=harness.auth_headers,
    )
    assert response.status_code == 201
    assert response.json() == {"id": 7}
    body = harness.mock.bodies("/res.partner/create")[0]
    assert body == {"vals_list": [{"name": "Acme", "email": "a@example.com"}]}


def test_update_success_and_missing(harness: GatewayHarness) -> None:
    harness.mock.search_read_pages = [[{"id": 4}]]
    response = harness.client.patch(
        "/api/contacts/4", json={"phone": "555"}, headers=harness.auth_headers
    )
    assert response.status_code == 200
    assert response.json() == {"updated": True, "id": 4}
    assert harness.mock.bodies("/res.partner/write")[0] == {
        "ids": [4],
        "vals": {"phone": "555"},
    }

    harness.mock.search_read_pages = [[]]
    missing = harness.client.patch(
        "/api/contacts/99", json={"phone": "555"}, headers=harness.auth_headers
    )
    assert missing.status_code == 404


def test_delete_success_and_missing(harness: GatewayHarness) -> None:
    harness.mock.search_read_pages = [[{"id": 5}]]
    response = harness.client.delete("/api/contacts/5", headers=harness.auth_headers)
    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": 5}
    assert harness.mock.bodies("/res.partner/unlink")[0] == {"ids": [5]}

    harness.mock.search_read_pages = [[]]
    missing = harness.client.delete("/api/contacts/99", headers=harness.auth_headers)
    assert missing.status_code == 404


def test_undeclared_operation_is_not_routed(build_harness) -> None:
    harness = build_harness(make_config(operations=["list"]))
    response = harness.client.post(
        "/api/contacts", json={"name": "x"}, headers=harness.auth_headers
    )
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_odoo_errors_are_sanitised(harness: GatewayHarness) -> None:
    harness.mock.routes["/json/2/res.partner/search_read"] = httpx.Response(
        500,
        json={
            "message": "Access Error",
            "debug": "Traceback (most recent call last): secret-token",
        },
    )
    response = harness.client.get("/api/contacts", headers=harness.auth_headers)
    assert response.status_code == 502
    payload = response.json()
    assert payload["error"]["code"] == "upstream_error"
    assert payload["error"]["message"] == "Access Error"
    assert "secret-token" not in response.text
    assert "Traceback" not in response.text


def test_odoo_unreachable_is_mapped(build_harness) -> None:
    config = make_config()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    app = create_app(config, odoo_transport=httpx.MockTransport(handler))
    client = TestClient(app)
    token = TokenService(config.auth).issue("tester")
    response = client.get("/api/contacts", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Odoo is unreachable"


def test_openapi_includes_dynamic_resources(harness: GatewayHarness) -> None:
    response = harness.client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.1")
    assert "/api/contacts" in spec["paths"]
    assert "/api/contacts/{record_id}" in spec["paths"]
    methods = spec["paths"]["/api/contacts"]
    assert {"get", "post"} <= set(methods)
    detail_methods = spec["paths"]["/api/contacts/{record_id}"]
    assert {"get", "patch", "delete"} <= set(detail_methods)


def test_openapi_excludes_undeclared_resources(build_harness) -> None:
    harness = build_harness(make_config(operations=["list"]))
    spec = harness.client.get("/openapi.json").json()
    assert "/api/contacts" in spec["paths"]
    assert "/api/contacts/{record_id}" not in spec["paths"]


def test_unknown_route_uses_error_envelope(harness: GatewayHarness) -> None:
    response = harness.client.get("/api/does-not-exist", headers=harness.auth_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("payload", [[], "string", 42])
def test_non_object_create_body_is_rejected(harness: GatewayHarness, payload) -> None:
    response = harness.client.post("/api/contacts", json=payload, headers=harness.auth_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
