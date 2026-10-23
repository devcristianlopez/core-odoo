from __future__ import annotations

from .conftest import AppHarness


def _create_user(harness: AppHarness, headers: dict[str, str], username: str, role: str):
    response = harness.client.post(
        "/api/v1/users",
        json={"username": username, "password": "password-123", "role": role},
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _login(harness: AppHarness, username: str) -> str:
    response = harness.client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "password-123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_project_membership_controls_visibility(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    _create_user(harness, auth_headers, "operator", "operator")
    create_project("smoke-test")
    token = _login(harness, "operator")
    headers = {"Authorization": f"Bearer {token}"}

    assert harness.client.get("/api/v1/projects", headers=headers).json() == []
    assert harness.client.get("/api/v1/projects/smoke-test", headers=headers).status_code == 403

    added = harness.client.post(
        "/api/v1/projects/smoke-test/members",
        json={"username": "operator"},
        headers=auth_headers,
    )
    assert added.status_code == 201, added.text
    projects = harness.client.get("/api/v1/projects", headers=headers).json()
    assert [project["name"] for project in projects] == ["smoke-test"]
    assert harness.client.get("/api/v1/projects/smoke-test", headers=headers).status_code == 200

    removed = harness.client.delete(
        "/api/v1/projects/smoke-test/members/operator",
        headers=auth_headers,
    )
    assert removed.status_code == 200
    assert harness.client.get("/api/v1/projects/smoke-test", headers=headers).status_code == 403


def test_admin_sees_all_projects(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("one-project")
    create_project("two-project")
    projects = harness.client.get("/api/v1/projects", headers=auth_headers).json()
    assert {project["name"] for project in projects} == {"one-project", "two-project"}
