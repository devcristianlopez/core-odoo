from __future__ import annotations

import shutil
from pathlib import Path

from app.providers.base import ProviderError

from .conftest import AppHarness


def _deploy(harness: AppHarness, headers: dict[str, str], stage: str = "dev", **extra):
    payload = {"stage": stage, "branch": "main"}
    payload.update(extra)
    return harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json=payload,
        headers=headers,
    )


def _create_iteration(harness: AppHarness, headers: dict[str, str], version: str = "0.1.0") -> None:
    response = harness.client.post(
        "/api/v1/projects/smoke-test/iterations",
        json={"version": version, "title": "First iteration"},
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _rollback(
    harness: AppHarness,
    headers: dict[str, str],
    stage: str = "dev",
    *,
    confirm: str | None = None,
):
    # A dev rollback needs no body; the confirmation only matters for prod.
    extra = {} if confirm is None else {"json": {"confirm": confirm}}
    return harness.client.post(
        f"/api/v1/projects/smoke-test/environments/{stage}/rollback",
        headers=headers,
        **extra,
    )


def _operator_headers(
    harness: AppHarness, auth_headers: dict[str, str], username: str = "rollback_operator"
) -> dict[str, str]:
    created = harness.client.post(
        "/api/v1/users",
        json={"username": username, "password": "password-123", "role": "operator"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    added = harness.client.post(
        "/api/v1/projects/smoke-test/members",
        json={"username": username, "role": "developer"},
        headers=auth_headers,
    )
    assert added.status_code == 201, added.text
    login = harness.client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "password-123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_deploy_creates_environment(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    response = _deploy(harness, auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"] == "smoke-test"
    assert body["stage"] == "dev"
    assert body["status"] == "running"
    assert body["url"] == "http://smoke-test-dev.core-odoo.test.local"
    assert body["compose_project"] == "core-smoke-test-dev"
    assert body["services"][0]["name"] == "odoo"
    # A fresh environment has no successful iteration to roll back to yet.
    assert body["last_good_iteration"] is None
    assert body["last_good_at"] is None
    assert harness.provider.calls[0][0] == "deploy"

    spec = harness.provider.specs[0]
    assert spec.db_name == "smoke_test_dev"
    assert spec.branch == "main"
    assert spec.domain_suffix == "test.local"


def test_redeploy_preserves_environment_secrets(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _deploy(harness, auth_headers)
    first = harness.provider.specs[-1]
    _deploy(harness, auth_headers)
    second = harness.provider.specs[-1]
    assert first.db_password == second.db_password
    assert first.odoo_api_key == second.odoo_api_key
    assert first.gateway_jwt_secret == second.gateway_jwt_secret


def test_deploy_invalid_stage(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    response = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "qa"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_deploy_failure_sets_error_status(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    harness.provider.fail_with = ProviderError("docker compose up failed")
    response = _deploy(harness, auth_headers)
    assert response.status_code == 502
    assert response.json()["detail"] == "docker compose up failed"

    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert environments[0]["status"] == "error"

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    assert any(
        event["action"] == "environment.deploy" and event["status"] == "failed" for event in audit
    )


def test_environment_lifecycle(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _deploy(harness, auth_headers)

    stopped = harness.client.post(
        "/api/v1/projects/smoke-test/environments/dev/stop", headers=auth_headers
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"

    started = harness.client.post(
        "/api/v1/projects/smoke-test/environments/dev/start", headers=auth_headers
    )
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    restarted = harness.client.post(
        "/api/v1/projects/smoke-test/environments/dev/restart", headers=auth_headers
    )
    assert restarted.status_code == 200
    assert [call[0] for call in harness.provider.calls[-3:]] == ["stop", "start", "restart"]


def test_logs_and_backup(
    harness: AppHarness, auth_headers: dict[str, str], create_project, settings
) -> None:
    create_project("smoke-test")
    _deploy(harness, auth_headers)

    logs = harness.client.get(
        "/api/v1/projects/smoke-test/environments/dev/logs?tail=50", headers=auth_headers
    )
    assert logs.status_code == 200
    assert logs.json() == {"logs": "log tail 50"}

    backup = harness.client.post(
        "/api/v1/projects/smoke-test/environments/dev/backup", headers=auth_headers
    )
    assert backup.status_code == 201
    payload = backup.json()
    assert payload["backup"] is True
    path = Path(payload["path"])
    assert path.is_file()
    assert path.parent == settings.backups_dir / "smoke-test-dev"


def test_environment_not_found(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    response = harness.client.post(
        "/api/v1/projects/smoke-test/environments/dev/start", headers=auth_headers
    )
    assert response.status_code == 404


def test_delete_environment(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _deploy(harness, auth_headers)
    response = harness.client.delete(
        "/api/v1/projects/smoke-test/environments/dev?confirm=smoke-test%2Fdev",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert harness.provider.calls[-1][0] == "delete"
    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert environments == []


def test_operations_on_undeployed_environment_return_conflict(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _deploy(harness, auth_headers)
    harness.provider.fail_with = ProviderError("environment smoke-test/dev has not been deployed")
    response = harness.client.post(
        "/api/v1/projects/smoke-test/environments/dev/stop", headers=auth_headers
    )
    assert response.status_code == 409


def test_module_update_flag_tracks_environment_state(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")

    assert _deploy(harness, auth_headers).status_code == 200
    # Redeploying a running environment asks the provider to upgrade modules.
    assert _deploy(harness, auth_headers).status_code == 200

    harness.provider.fail_with = ProviderError("docker compose up failed")
    assert _deploy(harness, auth_headers).status_code == 502
    harness.provider.fail_with = None

    # The provider decides from the real database whether -u applies, so a
    # retry after a failure still requests module updates.
    assert _deploy(harness, auth_headers).status_code == 200
    assert harness.provider.deploy_updates == [False, True, True, True]


def test_deploy_after_failure_requests_module_update(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")

    # A brand-new environment has no database, so the provider must install.
    assert _deploy(harness, auth_headers).status_code == 200
    assert harness.provider.deploy_updates == [False]

    harness.provider.fail_with = ProviderError("odoo module update failed")
    assert _deploy(harness, auth_headers).status_code == 502
    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert environments[0]["status"] == "error"
    harness.provider.fail_with = None

    # Fix the module and redeploy: the environment stays in ``error`` but the
    # database exists, so the update flag must be true again.
    assert _deploy(harness, auth_headers).status_code == 200
    assert harness.provider.deploy_updates == [False, True, True]


def test_redeploy_without_modules_preserves_stored_modules(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")

    first = _deploy(harness, auth_headers, modules=["upgrade_check"])
    assert first.status_code == 200, first.text
    assert first.json()["modules"] == ["upgrade_check"]

    # Omitting --modules must not erase the list discovered/stored on deploy 1.
    second = _deploy(harness, auth_headers)
    assert second.status_code == 200, second.text
    assert second.json()["modules"] == ["upgrade_check"]
    assert harness.provider.deploy_updates == [False, True]
    assert harness.provider.specs[-1].modules == ["upgrade_check"]


def test_iteration_deploy_records_last_good_iteration(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")

    deployed = _deploy(harness, auth_headers, iteration="0.1.0")
    assert deployed.status_code == 200, deployed.text
    body = deployed.json()
    assert body["last_good_iteration"] == "0.1.0"
    assert body["last_good_at"] is not None
    last_good_at = body["last_good_at"]

    plain = _deploy(harness, auth_headers)
    assert plain.status_code == 200, plain.text
    assert plain.json()["last_good_iteration"] == "0.1.0"
    assert plain.json()["last_good_at"] == last_good_at


def test_rollback_without_last_good_iteration_conflicts(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    assert _deploy(harness, auth_headers).status_code == 200

    response = _rollback(harness, auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "no successful iteration to roll back to"
    assert harness.provider.deploy_updates == [False]


def test_rollback_restores_last_good_iteration(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers, iteration="0.1.0").status_code == 200

    response = _rollback(harness, auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["last_good_iteration"] == "0.1.0"
    assert body["last_good_at"] is not None
    assert body["status"] == "running"
    assert harness.provider.deploy_updates[-1] is True

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    rollback = next(event for event in audit if event["action"] == "environment.rollback")
    assert rollback["status"] == "success"
    assert rollback["details"] == {"iteration": "0.1.0"}


def test_rollback_failure_sets_error_and_returns_bad_gateway(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers, iteration="0.1.0").status_code == 200

    harness.provider.fail_with = ProviderError("docker compose up failed")
    response = _rollback(harness, auth_headers)
    assert response.status_code == 502
    assert response.json()["detail"] == "docker compose up failed"

    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert environments[0]["status"] == "error"


def test_prod_rollback_requires_admin_and_confirmation(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200
    backup = harness.client.post(
        "/api/v1/projects/smoke-test/iterations/0.1.0/backup?stage=dev",
        headers=auth_headers,
    )
    assert backup.status_code == 201, backup.text
    prod = _deploy(harness, auth_headers, stage="prod", confirm="smoke-test", iteration="0.1.0")
    assert prod.status_code == 200, prod.text
    assert prod.json()["last_good_iteration"] == "0.1.0"

    operator_headers = _operator_headers(harness, auth_headers)
    forbidden = _rollback(harness, operator_headers, stage="prod", confirm="smoke-test")
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "production deploys require the admin role"

    wrong_confirm = _rollback(harness, auth_headers, stage="prod", confirm="nope")
    assert wrong_confirm.status_code == 400
    assert (
        wrong_confirm.json()["detail"]
        == "confirm must exactly match the project name for production"
    )

    rolled_back = _rollback(harness, auth_headers, stage="prod", confirm="smoke-test")
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["last_good_iteration"] == "0.1.0"
    assert harness.provider.deploy_updates[-1] is True


def test_rollback_missing_snapshot_conflicts(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers, iteration="0.1.0").status_code == 200
    snapshot = harness.settings.iterations_dir / "smoke-test" / "0.1.0"
    shutil.rmtree(snapshot)

    response = _rollback(harness, auth_headers)
    assert response.status_code == 409
    assert "snapshot not found" in response.json()["detail"]
