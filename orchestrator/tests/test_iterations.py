from __future__ import annotations

from pathlib import Path

from .conftest import AppHarness


def _create_iteration(harness: AppHarness, headers: dict[str, str], version: str = "0.1.0"):
    return harness.client.post(
        "/api/v1/projects/smoke-test/iterations",
        json={"version": version, "title": "First iteration", "notes": "baseline"},
        headers=headers,
    )


def test_iteration_snapshot_restore_and_deploy(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    project_dir = harness.settings.core_projects_dir / "smoke-test"
    backend = project_dir / "backend.yaml"
    backend.write_text("app: smoke-test\n", encoding="utf-8")

    created = _create_iteration(harness, auth_headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["version"] == "0.1.0"
    assert body["status"] == "created"
    assert body["has_snapshot"] is True
    assert app_path(harness, "smoke-test", "0.1.0").is_dir()

    listing = harness.client.get("/api/v1/projects/smoke-test/iterations", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    backend.write_text("app: changed\n", encoding="utf-8")
    restored = harness.client.post(
        "/api/v1/projects/smoke-test/iterations/0.1.0/restore",
        headers=auth_headers,
    )
    assert restored.status_code == 200, restored.text
    assert backend.read_text(encoding="utf-8") == "app: smoke-test\n"

    deployed = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "dev", "iteration": "0.1.0"},
        headers=auth_headers,
    )
    assert deployed.status_code == 200, deployed.text
    iteration = harness.client.get(
        "/api/v1/projects/smoke-test/iterations/0.1.0", headers=auth_headers
    ).json()
    assert iteration["status"] == "deployed"
    assert iteration["stage"] == "dev"
    assert iteration["deployed_at"] is not None


def test_iteration_duplicate_is_rejected(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    assert _create_iteration(harness, auth_headers).status_code == 201
    assert _create_iteration(harness, auth_headers).status_code == 409


def test_iteration_missing_is_404(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    response = harness.client.post(
        "/api/v1/projects/smoke-test/iterations/9.9.9/restore",
        headers=auth_headers,
    )
    assert response.status_code == 404


def app_path(harness: AppHarness, project: str, version: str) -> Path:
    return harness.settings.iterations_dir / project / version


def test_iteration_diff_between_versions(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    project_dir = harness.settings.core_projects_dir / "smoke-test"
    source = project_dir / "backend.yaml"
    source.write_text("app: one\n", encoding="utf-8")
    assert _create_iteration(harness, auth_headers, "0.1.0").status_code == 201

    source.write_text("app: two\n", encoding="utf-8")
    (project_dir / "new.txt").write_text("new\n", encoding="utf-8")
    assert _create_iteration(harness, auth_headers, "0.2.0").status_code == 201

    response = harness.client.get(
        "/api/v1/projects/smoke-test/iterations/0.2.0/diff",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["from_version"] == "0.1.0"
    assert "backend.yaml" in body["modified"]
    assert "new.txt" in body["added"]


def test_iteration_database_backup(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    assert _create_iteration(harness, auth_headers).status_code == 201
    deploy = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "dev"},
        headers=auth_headers,
    )
    assert deploy.status_code == 200, deploy.text

    response = harness.client.post(
        "/api/v1/projects/smoke-test/iterations/0.1.0/backup?stage=dev",
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version"] == "0.1.0"
    assert body["stage"] == "dev"
    assert body["path"].endswith(".sql")

    backups = harness.client.get(
        "/api/v1/projects/smoke-test/iterations/0.1.0/backups",
        headers=auth_headers,
    )
    assert backups.status_code == 200
    assert len(backups.json()) == 1


def test_production_deploy_requires_confirmation_iteration_and_backup(
    harness: AppHarness, auth_headers: dict[str, str], create_project
) -> None:
    create_project("smoke-test")
    assert _create_iteration(harness, auth_headers).status_code == 201
    assert (
        harness.client.post(
            "/api/v1/projects/smoke-test/deploy",
            json={"stage": "dev"},
            headers=auth_headers,
        ).status_code
        == 200
    )
    missing_confirm = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "prod", "iteration": "0.1.0"},
        headers=auth_headers,
    )
    assert missing_confirm.status_code == 400

    missing_iteration = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "prod", "confirm": "smoke-test"},
        headers=auth_headers,
    )
    assert missing_iteration.status_code == 409

    missing_backup = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "prod", "confirm": "smoke-test", "iteration": "0.1.0"},
        headers=auth_headers,
    )
    assert missing_backup.status_code == 409

    backup = harness.client.post(
        "/api/v1/projects/smoke-test/iterations/0.1.0/backup?stage=dev",
        headers=auth_headers,
    )
    assert backup.status_code == 201, backup.text
    deployed = harness.client.post(
        "/api/v1/projects/smoke-test/deploy",
        json={"stage": "prod", "confirm": "smoke-test", "iteration": "0.1.0"},
        headers=auth_headers,
    )
    assert deployed.status_code == 200, deployed.text
