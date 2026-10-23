from __future__ import annotations

from .conftest import AppHarness


def _create_user(harness: AppHarness, headers: dict[str, str], username: str, role: str):
    return harness.client.post(
        "/api/v1/users",
        json={"username": username, "password": "password-123", "role": role},
        headers=headers,
    )


def _login(harness: AppHarness, username: str) -> str:
    response = harness.client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "password-123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_admin_can_create_and_list_users(
    harness: AppHarness, auth_headers: dict[str, str]
) -> None:
    created = _create_user(harness, auth_headers, "operator", "operator")
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "operator"

    users = harness.client.get("/api/v1/users", headers=auth_headers)
    assert users.status_code == 200
    assert {user["username"] for user in users.json()} >= {"admin", "operator"}


def test_operator_cannot_create_projects_but_can_deploy_dev(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    assert _create_user(harness, auth_headers, "operator", "operator").status_code == 201
    token = _login(harness, "operator")
    headers = {"Authorization": f"Bearer {token}"}

    forbidden = harness.client.post(
        "/api/v1/projects",
        json={"name": "other-project", "template": "odoo-module"},
        headers=headers,
    )
    assert forbidden.status_code == 403

    create_project("smoke-test")
    deployed = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "dev"},
        headers=headers,
    )
    assert deployed.status_code == 200, deployed.text
    prod = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "prod"},
        headers=headers,
    )
    assert prod.status_code == 403


def test_viewer_is_read_only(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    assert _create_user(harness, auth_headers, "viewer", "viewer").status_code == 201
    token = _login(harness, "viewer")
    headers = {"Authorization": f"Bearer {token}"}

    assert harness.client.get("/api/v1/projects", headers=headers).status_code == 200
    create_project("smoke-test")
    response = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "dev"},
        headers=headers,
    )
    assert response.status_code == 403


def test_last_admin_cannot_be_demoted(
    harness: AppHarness, auth_headers: dict[str, str]
) -> None:
    response = harness.client.patch(
        "/api/v1/users/admin",
        json={"role": "viewer"},
        headers=auth_headers,
    )
    assert response.status_code == 409
