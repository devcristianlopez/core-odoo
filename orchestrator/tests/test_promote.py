from __future__ import annotations

from app.providers.base import ProviderError

from .conftest import AppHarness


def _deploy(harness: AppHarness, headers: dict[str, str], stage: str = "staging"):
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
        json={"version": version, "title": "Base"},
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _promote(
    harness: AppHarness,
    headers: dict[str, str],
    *,
    confirm: str | None = "smoke-test",
    source: str = "staging",
    neutralize: bool = True,
    skip_smoke: bool = False,
):
    body: dict[str, object] = {
        "source_stage": source,
        "neutralize": neutralize,
        "skip_smoke": skip_smoke,
    }
    if confirm is not None:
        body["confirm"] = confirm
    return harness.client.post(
        "/api/v1/projects/smoke-test/promote", json=body, headers=headers
    )


def _operator_headers(harness: AppHarness, auth_headers: dict[str, str]) -> dict[str, str]:
    created = harness.client.post(
        "/api/v1/users",
        json={"username": "promote_operator", "password": "password-123", "role": "operator"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    added = harness.client.post(
        "/api/v1/projects/smoke-test/members",
        json={"username": "promote_operator", "role": "developer"},
        headers=auth_headers,
    )
    assert added.status_code == 201, added.text
    login = harness.client.post(
        "/api/v1/auth/login",
        json={"username": "promote_operator", "password": "password-123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_promote_requires_admin_and_confirmation(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    assert _deploy(harness, auth_headers).status_code == 200
    operator = _operator_headers(harness, auth_headers)

    assert _promote(harness, operator).status_code == 403

    missing = _promote(harness, auth_headers, confirm=None)
    assert missing.status_code == 400
    assert "confirm" in missing.json()["detail"]

    mismatch = _promote(harness, auth_headers, confirm="other")
    assert mismatch.status_code == 400
    assert harness.provider.restored_dumps == []


def test_promote_rejects_prod_as_source(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    response = _promote(harness, auth_headers, source="prod")
    assert response.status_code == 400
    assert "source stage" in response.json()["detail"]


def test_promote_requires_a_deployed_source(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    response = _promote(harness, auth_headers)
    assert response.status_code == 404
    assert "source environment staging not found" in response.json()["detail"]


def test_promote_clones_and_neutralizes_staging(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200

    response = _promote(harness, auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "prod"
    assert body["status"] == "running"
    assert body["last_good_iteration"] == "0.1.0"
    assert body["url"] == "http://smoke-test-prod.core-odoo.test.local"

    actions = [call[0] for call in harness.provider.calls]
    assert actions == [
        "deploy",
        "smoke",
        "prepare",
        "backup",
        "restore_database",
        "copy_filestore",
        "neutralize_database",
        "deploy",
    ]
    dump = harness.provider.restored_dumps[-1]
    assert dump.is_file()
    assert "promote-" in dump.name
    assert harness.provider.neutralized == ["http://smoke-test-prod.core-odoo.test.local"]
    assert harness.provider.copied_filestores == [
        ("core-smoke-test-staging", "core-smoke-test-prod")
    ]

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    event = next(item for item in audit if item["action"] == "environment.promote")
    assert event["status"] == "success"
    assert event["details"]["source"] == "staging"
    assert event["details"]["iteration"] == "0.1.0"
    assert event["details"]["neutralized"] is True


def test_promote_can_skip_neutralization(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200

    response = _promote(harness, auth_headers, neutralize=False)

    assert response.status_code == 200, response.text
    assert harness.provider.neutralized == []
    actions = [call[0] for call in harness.provider.calls]
    assert "neutralize_database" not in actions


def test_promote_failure_marks_prod_error(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200

    harness.provider.fail_with = ProviderError("promotion failed")
    harness.provider.fail_on = "restore_database"
    response = _promote(harness, auth_headers)

    assert response.status_code == 502
    assert response.json()["detail"] == "promotion failed"
    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    prod = next(env for env in environments if env["stage"] == "prod")
    assert prod["status"] == "error"

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    event = next(item for item in audit if item["action"] == "environment.promote")
    assert event["status"] == "failed"


def test_promote_smoke_gate_blocks_an_unhealthy_source(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    assert _deploy(harness, auth_headers).status_code == 200
    harness.provider.smoke_ok = False

    response = _promote(harness, auth_headers)

    assert response.status_code == 409
    assert response.json()["detail"].startswith("smoke gate failed on staging")
    assert harness.provider.restored_dumps == []
    environments = harness.client.get(
        "/api/v1/projects/smoke-test/environments", headers=auth_headers
    ).json()
    assert all(env["stage"] != "prod" for env in environments)

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    event = next(item for item in audit if item["action"] == "environment.promote")
    assert event["status"] == "failed"
    assert event["details"]["gate"] == "smoke"


def test_promote_can_skip_the_smoke_gate(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    _create_iteration(harness, auth_headers)
    assert _deploy(harness, auth_headers).status_code == 200
    harness.provider.smoke_ok = False

    response = _promote(harness, auth_headers, skip_smoke=True)

    assert response.status_code == 200, response.text
    actions = [call[0] for call in harness.provider.calls]
    assert "smoke" not in actions


def test_promote_requires_an_iteration(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    assert _deploy(harness, auth_headers).status_code == 200

    response = _promote(harness, auth_headers)

    assert response.status_code == 409
    assert "iteration" in response.json()["detail"]
    assert harness.provider.restored_dumps == []
