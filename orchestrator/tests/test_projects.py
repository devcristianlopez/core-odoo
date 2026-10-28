from __future__ import annotations

from app.providers.base import ProviderError

from .conftest import AppHarness


def test_create_list_get_project(
    harness: AppHarness,
    auth_headers: dict[str, str],
    create_project,
    settings,
) -> None:
    project = create_project("smoke-test")
    assert project["name"] == "smoke-test"
    assert project["template"] == "empty"
    assert project["environments"] == []
    assert (settings.core_projects_dir / "smoke-test" / "odoo" / "addons").is_dir()
    assert not any((settings.core_projects_dir / "smoke-test" / "odoo" / "addons").iterdir())
    assert (settings.core_projects_dir / "smoke-test" / "frontend" / "Dockerfile").is_file()

    listing = harness.client.get("/api/v1/projects", headers=auth_headers)
    assert listing.status_code == 200
    assert [item["name"] for item in listing.json()] == ["smoke-test"]

    detail = harness.client.get(
        "/api/v1/projects/smoke-test?confirm=smoke-test", headers=auth_headers
    )
    assert detail.status_code == 200
    assert detail.json()["name"] == "smoke-test"


def test_duplicate_project_conflicts(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    response = harness.client.post(
        "/api/v1/projects", json={"name": "smoke-test"}, headers=auth_headers
    )
    assert response.status_code == 409


def test_project_name_is_validated(harness: AppHarness, auth_headers: dict[str, str]) -> None:
    response = harness.client.post(
        "/api/v1/projects", json={"name": "Bad Name!"}, headers=auth_headers
    )
    assert response.status_code == 422


def test_missing_project_returns_404(harness: AppHarness, auth_headers: dict[str, str]) -> None:
    assert harness.client.get("/api/v1/projects/nope", headers=auth_headers).status_code == 404


def test_delete_project_cleans_environments(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    deploy = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "dev"},
        headers=auth_headers,
    )
    assert deploy.status_code == 200

    response = harness.client.delete(
        "/api/v1/projects/smoke-test?confirm=smoke-test", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert harness.provider.calls[-1][0] == "delete"
    assert harness.client.get("/api/v1/projects", headers=auth_headers).json() == []

    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    actions = [event["action"] for event in audit]
    assert "project.delete" in actions


def test_delete_project_provider_failure_is_reported(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    harness.client.post(
        "/api/v1/projects/smoke-test/deploy", json={"stage": "dev"}, headers=auth_headers
    )
    harness.provider.fail_with = ProviderError("docker compose down failed")
    response = harness.client.delete(
        "/api/v1/projects/smoke-test?confirm=smoke-test", headers=auth_headers
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "docker compose down failed"
    # project is kept so the operation can be retried
    assert (
        harness.client.get(
            "/api/v1/projects/smoke-test?confirm=smoke-test", headers=auth_headers
        ).status_code
        == 200
    )


def test_created_project_is_recorded_in_audit(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("audited")
    audit = harness.client.get("/api/v1/audit", headers=auth_headers).json()
    assert audit[0]["action"] == "project.create"
    assert audit[0]["actor"] == "api"
    assert audit[0]["status"] == "success"


def test_project_files_are_removed_on_delete(
    harness: AppHarness, auth_headers: dict[str, str], create_project, settings
) -> None:
    create_project("smoke-test")
    harness.client.delete(
        "/api/v1/projects/smoke-test?confirm=smoke-test&purge=true",
        headers=auth_headers,
    )
    assert not (settings.core_projects_dir / "smoke-test").exists()
    assert not (settings.iterations_dir / "smoke-test").exists()


def test_delete_project_requires_typed_confirmation(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    assert (
        harness.client.delete("/api/v1/projects/smoke-test", headers=auth_headers).status_code
        == 422
    )
    wrong = harness.client.delete(
        "/api/v1/projects/smoke-test?confirm=nope",
        headers=auth_headers,
    )
    assert wrong.status_code == 400
    correct = harness.client.delete(
        "/api/v1/projects/smoke-test?confirm=smoke-test&purge=true",
        headers=auth_headers,
    )
    assert correct.status_code == 200


def test_deleting_a_project_removes_its_iterations(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    created = harness.client.post(
        "/api/v1/projects/smoke-test/iterations",
        json={"version": "0.1.0", "title": "Base"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    deleted = harness.client.delete(
        "/api/v1/projects/smoke-test?confirm=smoke-test&purge=true", headers=auth_headers
    )
    assert deleted.status_code == 200, deleted.text

    # SQLite reuses ids: a leftover iteration would attach to the new project and
    # block creating version 0.1.0 again.
    create_project("smoke-test")
    iterations = harness.client.get(
        "/api/v1/projects/smoke-test/iterations", headers=auth_headers
    ).json()
    assert iterations == []
    again = harness.client.post(
        "/api/v1/projects/smoke-test/iterations",
        json={"version": "0.1.0", "title": "Base"},
        headers=auth_headers,
    )
    assert again.status_code == 201, again.text
