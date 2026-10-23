from __future__ import annotations

from .conftest import AppHarness


def _operator_token(harness: AppHarness, auth_headers: dict[str, str]) -> str:
    created = harness.client.post(
        "/api/v1/users",
        json={"username": "approver_test", "password": "password-123", "role": "operator"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    login = harness.client.post(
        "/api/v1/auth/login",
        json={"username": "approver_test", "password": "password-123"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _prepare_iteration(harness: AppHarness, auth_headers: dict[str, str], create_project) -> None:
    create_project("smoke-test")
    iteration = harness.client.post(
        "/api/v1/projects/smoke-test/iterations",
        json={"version": "0.1.0", "title": "Production candidate"},
        headers=auth_headers,
    )
    assert iteration.status_code == 201, iteration.text
    deploy = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "dev"},
        headers=auth_headers,
    )
    assert deploy.status_code == 200, deploy.text
    backup = harness.client.post(
        "/api/v1/projects/smoke-test/iterations/0.1.0/backup?stage=dev",
        headers=auth_headers,
    )
    assert backup.status_code == 201, backup.text


def test_operator_requests_and_admin_approves_production(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    _prepare_iteration(harness, auth_headers, create_project)
    token = _operator_token(harness, auth_headers)
    harness.client.post(
        "/api/v1/projects/smoke-test/members",
        json={"username": "approver_test"},
        headers=auth_headers,
    )
    operator_headers = {"Authorization": f"Bearer {token}"}
    requested = harness.client.post(
        "/api/v1/projects/smoke-test/deploy-requests",
        json={"iteration": "0.1.0", "reason": "ready for production"},
        headers=operator_headers,
    )
    assert requested.status_code == 201, requested.text
    request_id = requested.json()["id"]
    assert requested.json()["status"] == "pending"

    listed = harness.client.get("/api/v1/deploy-requests?status=pending", headers=auth_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [request_id]

    forbidden = harness.client.post(
        f"/api/v1/deploy-requests/{request_id}/approve",
        headers=operator_headers,
    )
    assert forbidden.status_code == 403

    approved = harness.client.post(
        f"/api/v1/deploy-requests/{request_id}/approve",
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "deployed"
    assert approved.json()["deployed_at"] is not None


def test_admin_can_reject_production_request(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    _prepare_iteration(harness, auth_headers, create_project)
    token = _operator_token(harness, auth_headers)
    harness.client.post(
        "/api/v1/projects/smoke-test/members",
        json={"username": "approver_test"},
        headers=auth_headers,
    )
    requested = harness.client.post(
        "/api/v1/projects/smoke-test/deploy-requests",
        json={"iteration": "0.1.0"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert requested.status_code == 201, requested.text
    rejected = harness.client.post(
        f"/api/v1/deploy-requests/{requested.json()['id']}/reject",
        headers=auth_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
