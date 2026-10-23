from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import API_TOKEN, AppHarness


def test_health_is_public(harness: AppHarness) -> None:
    response = harness.client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "version" in response.json()


def test_login_and_me(harness: AppHarness) -> None:
    response = harness.client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-password"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"

    me = harness.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json() == {"username": "admin", "role": "admin"}

    alias = harness.client.post(
        "/auth/login", json={"username": "admin", "password": "admin-password"}
    )
    assert alias.status_code == 200


def test_login_rejects_bad_credentials(harness: AppHarness) -> None:
    response = harness.client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert response.status_code == 401


def test_api_token_identity(harness: AppHarness, auth_headers: dict[str, str]) -> None:
    response = harness.client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"username": "api", "role": "admin"}


def test_requires_auth(harness: AppHarness) -> None:
    assert harness.client.get("/api/v1/projects").status_code == 401
    assert (
        harness.client.get("/api/v1/projects", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )


def test_status(harness: AppHarness, auth_headers: dict[str, str]) -> None:
    response = harness.client.get("/api/v1/status", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["docker"] == {"available": True, "version": "test", "error": None}
    assert payload["disk"]["percent"] == 25.0
    assert payload["environments"] == 0


def test_metrics_endpoint_is_public(harness: AppHarness) -> None:
    response = TestClient(harness.app).get("/metrics")
    assert response.status_code == 200
    assert "core_odoo_up 1" in response.text


def test_audit_requires_auth(harness: AppHarness) -> None:
    assert harness.client.get("/api/v1/audit").status_code == 401
    assert (
        harness.client.get(
            "/api/v1/audit", headers={"Authorization": f"Bearer {API_TOKEN}"}
        ).status_code
        == 200
    )
