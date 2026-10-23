from __future__ import annotations

from pathlib import Path

from app.providers.base import ProviderError

from .conftest import AppHarness


def _deploy(harness: AppHarness, headers: dict[str, str], stage: str = "dev"):
    return harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": stage, "branch": "main"},
        headers=headers,
    )


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
        "/api/v1/projects/smoke-test/environments/dev", headers=auth_headers
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
