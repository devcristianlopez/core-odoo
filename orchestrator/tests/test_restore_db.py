from __future__ import annotations

from app.providers.base import ProviderError

from .conftest import AppHarness


def _deploy(harness: AppHarness, headers: dict[str, str], stage: str = "dev"):
    return harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": stage, "branch": "main"},
        headers=headers,
    )


def _create_iteration(
    harness: AppHarness, headers: dict[str, str], version: str = "0.1.0"
) -> None:
    response = harness.client.post(
        "/api/v1/projects/smoke-test/iterations",
        json={"version": version, "title": "First iteration"},
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _backup(harness: AppHarness, headers: dict[str, str], stage: str = "dev"):
    return harness.client.post(
        f"/api/v1/projects/smoke-test/iterations/0.1.0/backup?stage={stage}",
        headers=headers,
    )


def _restore(
    harness: AppHarness,
    headers: dict[str, str],
    stage: str = "dev",
    *,
    confirm: str | None = None,
    version: str = "0.1.0",
):
    body: dict[str, str] = {"stage": stage}
    if confirm is not None:
        body["confirm"] = confirm
    return harness.client.post(
        f"/api/v1/projects/smoke-test/iterations/{version}/restore-db",
        json=body,
        headers=headers,
    )


def _operator_headers(harness: AppHarness, auth_headers: dict[str, str]) -> dict[str, str]:
    created = harness.client.post(
        "/api/v1/users",
        json={"username": "restore_operator", "password": "password-123", "role": "operator"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    added = harness.client.post(
        "/api/v1/projects/smoke-test/members",
        json={"username": "restore_operator", "role": "developer"},
        headers=auth_headers,
    )
    assert added.status_code == 201, added.text
    login = harness.client.post(
        "/api/v1/auth/login",
        json={"username": "restore_operator", "password": "password-123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_restore_requires_a_database_backup(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200

    response = _restore(harness, auth_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "iteration 0.1.0 has no database backup for dev"
    assert harness.provider.restored_dumps == []


def test_restore_loads_the_dump_and_redeploys(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200
    assert _backup(harness, auth_headers).status_code == 201

    response = _restore(harness, auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"] == "smoke-test"
    assert body["stage"] == "dev"
    assert body["status"] == "running"
    assert harness.provider.restored_dumps[-1].is_file()
    actions = [call[0] for call in harness.provider.calls]
    assert actions[-2:] == ["restore_database", "deploy"]
    assert harness.provider.deploy_updates[-1] is True

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    event = next(item for item in audit if item["action"] == "iteration.restore_db")
    assert event["status"] == "success"
    assert event["details"]["stage"] == "dev"


def test_restore_in_production_requires_admin_and_confirmation(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200
    operator = _operator_headers(harness, auth_headers)

    forbidden = _restore(harness, operator, stage="prod", confirm="smoke-test")
    assert forbidden.status_code == 403

    missing = _restore(harness, auth_headers, stage="prod")
    assert missing.status_code == 400
    assert "confirm" in missing.json()["detail"]

    mismatch = _restore(harness, auth_headers, stage="prod", confirm="other")
    assert mismatch.status_code == 400
    assert harness.provider.restored_dumps == []


def test_restore_failure_marks_environment_error(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200
    assert _backup(harness, auth_headers).status_code == 201

    harness.provider.fail_with = ProviderError("database restore failed")
    response = _restore(harness, auth_headers)

    assert response.status_code == 502
    assert response.json()["detail"] == "database restore failed"
    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert environments[0]["status"] == "error"

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    event = next(item for item in audit if item["action"] == "iteration.restore_db")
    assert event["status"] == "failed"
