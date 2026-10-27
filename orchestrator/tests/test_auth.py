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


def _login(harness: AppHarness, password: str, username: str = "admin"):
    return harness.client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )


def test_change_password_rotates_credentials(harness: AppHarness) -> None:
    token = _login(harness, "admin-password").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = harness.client.post(
        "/api/v1/auth/password",
        json={"current_password": "admin-password", "new_password": "new-password-123"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"changed": True}

    assert _login(harness, "admin-password").status_code == 401
    assert _login(harness, "new-password-123").status_code == 200

    audit = harness.client.get("/api/v1/audit", headers=headers).json()
    event = next(item for item in audit if item["action"] == "user.password_change")
    assert event["target"] == "admin"
    assert event["details"] == {"self": True}


def test_change_password_rejects_wrong_current(harness: AppHarness) -> None:
    token = _login(harness, "admin-password").json()["access_token"]
    response = harness.client.post(
        "/api/v1/auth/password",
        json={"current_password": "wrong", "new_password": "new-password-123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "current password is incorrect"


def test_change_password_requires_a_different_value(harness: AppHarness) -> None:
    token = _login(harness, "admin-password").json()["access_token"]
    response = harness.client.post(
        "/api/v1/auth/password",
        json={"current_password": "admin-password", "new_password": "admin-password"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "new password must differ from the current one"


def test_change_password_rejects_the_api_token(
    harness: AppHarness, auth_headers: dict[str, str]
) -> None:
    response = harness.client.post(
        "/api/v1/auth/password",
        json={"current_password": "x", "new_password": "new-password-123"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "the API token has no password to change"
