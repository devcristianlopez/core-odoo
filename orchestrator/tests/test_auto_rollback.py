from __future__ import annotations

from app.providers.base import ProviderError

from .conftest import AppHarness


def _deploy(harness: AppHarness, headers: dict[str, str], **extra):
    payload: dict[str, object] = {"stage": "dev", "branch": "main"}
    payload.update(extra)
    return harness.client.post(
        "/api/v1/projects/smoke-test/deploy", json=payload, headers=headers
    )


def _create_iteration(harness: AppHarness, headers: dict[str, str]) -> None:
    response = harness.client.post(
        "/api/v1/projects/smoke-test/iterations",
        json={"version": "0.1.0", "title": "First iteration"},
        headers=headers,
    )
    assert response.status_code == 201, response.text


def test_failed_deploy_rolls_back_to_last_good(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers, iteration="0.1.0").status_code == 200

    harness.provider.fail_with = ProviderError("module update failed")
    harness.provider.fail_on = "deploy"
    harness.provider.fail_times = 1

    response = _deploy(harness, auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["auto_rolled_back"] is True
    assert body["status"] == "running"
    assert body["last_good_iteration"] == "0.1.0"
    assert harness.provider.deploy_updates == [False, True, True]

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    actions = [event["action"] for event in audit]
    assert "environment.deploy" in actions
    recovery = next(event for event in audit if event["action"] == "environment.auto_rollback")
    assert recovery["status"] == "success"
    assert recovery["details"]["iteration"] == "0.1.0"


def test_auto_rollback_disabled_keeps_the_error(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers, iteration="0.1.0").status_code == 200
    harness.settings.core_auto_rollback = False

    harness.provider.fail_with = ProviderError("module update failed")
    response = _deploy(harness, auth_headers)

    assert response.status_code == 502
    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert environments[0]["status"] == "error"
    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    assert all(event["action"] != "environment.auto_rollback" for event in audit)


def test_first_failed_deploy_has_nothing_to_roll_back(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    harness.provider.fail_with = ProviderError("install failed")

    response = _deploy(harness, auth_headers)

    assert response.status_code == 502
    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert environments[0]["status"] == "error"
    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    assert all(event["action"] != "environment.auto_rollback" for event in audit)


def test_failed_recovery_is_not_retried(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers, iteration="0.1.0").status_code == 200

    harness.provider.fail_with = ProviderError("cluster is down")

    response = _deploy(harness, auth_headers)

    assert response.status_code == 502
    assert response.json()["detail"] == "cluster is down"
    # initial deploy + one recovery attempt, never a third deploy
    assert harness.provider.deploy_updates == [False, True, True]
    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    recovery = next(event for event in audit if event["action"] == "environment.auto_rollback")
    assert recovery["status"] == "failed"

    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert environments[0]["status"] == "error"
