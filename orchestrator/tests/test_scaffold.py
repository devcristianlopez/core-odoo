from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.scaffold import _adopt_ownership, _reference_owner, ensure_project_layout

from .conftest import API_TOKEN, FakeProvider

REPO_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
PLACEHOLDERS = ("__MODULE__", "__MODULE_TITLE__")


@pytest.fixture
def repo_templates_settings(tmp_path: Path) -> Settings:
    return Settings(
        core_api_token=API_TOKEN,
        core_data_dir=tmp_path / "data",
        core_projects_dir=tmp_path / "projects",
        core_templates_dir=REPO_TEMPLATES,
        core_gateway_dir=tmp_path / "gateway",
        core_domain_suffix="test.local",
    )


def _all_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def test_module_template_is_installed_under_addons(repo_templates_settings: Settings) -> None:
    project_dir = ensure_project_layout(repo_templates_settings, "upgrade-check", "odoo-module")

    module_dir = project_dir / "odoo" / "addons" / "upgrade_check"
    assert module_dir.is_dir()
    assert not (project_dir / "__manifest__.py").exists()
    assert not (project_dir / "models").exists()

    for relative in (
        "__init__.py",
        "__manifest__.py",
        "README.md",
        "models/example_model.py",
        "views/example_views.xml",
        "security/ir.access.csv",
        "tests/test_example.py",
        "i18n/es.po",
    ):
        assert (module_dir / relative).is_file(), relative

    manifest = (module_dir / "__manifest__.py").read_text(encoding="utf-8")
    assert '"name": "Upgrade Check"' in manifest
    model = (module_dir / "models" / "example_model.py").read_text(encoding="utf-8")
    assert '_name = "upgrade_check.example"' in model
    assert '_description = "Upgrade Check example record"' in model

    for path in _all_files(project_dir):
        text = path.read_text(encoding="utf-8")
        assert all(token not in text for token in PLACEHOLDERS), path


def test_project_template_without_manifest_copies_to_root(tmp_path: Path) -> None:
    templates_dir = tmp_path / "templates"
    (templates_dir / "plain").mkdir(parents=True)
    (templates_dir / "plain" / "README.md").write_text("# Plain\n", encoding="utf-8")
    (templates_dir / "plain" / "notes.txt").write_text("hello\n", encoding="utf-8")
    settings = Settings(
        core_projects_dir=tmp_path / "projects",
        core_templates_dir=templates_dir,
    )

    project_dir = ensure_project_layout(settings, "plain-demo", "plain")

    assert (project_dir / "README.md").read_text(encoding="utf-8") == "# Plain\n"
    assert (project_dir / "notes.txt").is_file()
    assert (project_dir / "odoo" / "addons").is_dir()
    assert not (project_dir / "odoo" / "addons" / "plain_demo").exists()


def test_module_template_layout_is_idempotent(repo_templates_settings: Settings) -> None:
    project_dir = ensure_project_layout(repo_templates_settings, "upgrade-check", "odoo-module")
    module_dir = project_dir / "odoo" / "addons" / "upgrade_check"
    (module_dir / "custom.py").write_text("CUSTOM = True\n", encoding="utf-8")

    ensure_project_layout(repo_templates_settings, "upgrade-check", "odoo-module")

    assert (module_dir / "custom.py").is_file()
    manifest = (module_dir / "__manifest__.py").read_text(encoding="utf-8")
    assert manifest.count('"name": "Upgrade Check"') == 1


def test_existing_module_dir_is_not_clobbered(repo_templates_settings: Settings) -> None:
    project_dir = repo_templates_settings.core_projects_dir / "upgrade-check"
    module_dir = project_dir / "odoo" / "addons" / "upgrade_check"
    module_dir.mkdir(parents=True)
    (module_dir / "__manifest__.py").write_text('{"name": "Handwritten"}\n', encoding="utf-8")

    ensure_project_layout(repo_templates_settings, "upgrade-check", "odoo-module")

    manifest = (module_dir / "__manifest__.py").read_text(encoding="utf-8")
    assert manifest == '{"name": "Handwritten"}\n'
    assert not (module_dir / "models").exists()


def test_project_creation_installs_the_module(repo_templates_settings: Settings) -> None:
    app = create_app(repo_templates_settings, provider=FakeProvider())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            json={"name": "upgrade-check", "template": "odoo-module"},
            headers={"Authorization": f"Bearer {API_TOKEN}"},
        )

    assert response.status_code == 201, response.text
    project_dir = repo_templates_settings.core_projects_dir / "upgrade-check"
    module_dir = project_dir / "odoo" / "addons" / "upgrade_check"
    assert (module_dir / "__manifest__.py").is_file()
    assert not (project_dir / "__manifest__.py").exists()


def _sample_tree(projects_dir: Path) -> Path:
    tree = projects_dir / "upgrade-check"
    (tree / "odoo" / "addons" / "upgrade_check").mkdir(parents=True)
    (tree / "odoo" / "addons" / "upgrade_check" / "models.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    (tree / "README.md").write_text("# Upgrade Check\n", encoding="utf-8")
    return tree


def test_adopt_ownership_is_a_noop_when_not_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    projects_dir = tmp_path / "projects"
    tree = _sample_tree(projects_dir)
    chowns: list[tuple[object, ...]] = []

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(os, "chown", lambda *args, **kwargs: chowns.append(args))

    _adopt_ownership(tree, projects_dir)

    assert chowns == []


def test_adopt_ownership_gives_every_entry_to_the_reference_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    projects_dir = tmp_path / "projects"
    tree = _sample_tree(projects_dir)
    expected = {tree, *tree.rglob("*")}
    calls: list[tuple[Path, int, int, bool]] = []

    def record_chown(
        path: str | os.PathLike[str],
        uid: int,
        gid: int,
        *,
        follow_symlinks: bool = True,
    ) -> None:
        calls.append((Path(path), uid, gid, follow_symlinks))

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", record_chown)
    monkeypatch.setattr("app.scaffold._reference_owner", lambda _reference: (4242, 4343))

    _adopt_ownership(tree, projects_dir)

    assert {path for path, _, _, _ in calls} == expected
    assert {uid for _, uid, _, _ in calls} == {4242}
    assert {gid for _, _, gid, _ in calls} == {4343}
    assert all(follow is False for _, _, _, follow in calls)


def test_adopt_ownership_skips_entries_that_already_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    projects_dir = tmp_path / "projects"
    tree = _sample_tree(projects_dir)
    chowns: list[tuple[object, ...]] = []

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda *args, **kwargs: chowns.append(args))

    _adopt_ownership(tree, projects_dir)

    assert chowns == []


def test_reference_owner_prefers_the_reference_and_falls_back_to_its_parent(
    tmp_path: Path,
) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    missing = tmp_path / "missing" / "projects"
    missing.parent.mkdir()

    projects_owner = _reference_owner(projects_dir)
    parent_owner = _reference_owner(missing)

    assert projects_owner == (projects_dir.stat().st_uid, projects_dir.stat().st_gid)
    assert parent_owner == (missing.parent.stat().st_uid, missing.parent.stat().st_gid)
    assert _reference_owner(tmp_path / "ghost" / "projects") is None


def test_adopt_ownership_survives_chown_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    projects_dir = tmp_path / "projects"
    tree = _sample_tree(projects_dir)
    attempts: list[Path] = []

    def failing_chown(
        path: str | os.PathLike[str], _uid: int, _gid: int, **_kwargs: object
    ) -> None:
        attempts.append(Path(path))
        raise PermissionError(1, "Operation not permitted", str(path))

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", failing_chown)
    monkeypatch.setattr("app.scaffold._reference_owner", lambda _reference: (4242, 4343))

    _adopt_ownership(tree, projects_dir)

    assert {tree, *tree.rglob("*")} == set(attempts)


def test_project_layout_adopts_ownership_of_the_project_dir(
    monkeypatch: pytest.MonkeyPatch, repo_templates_settings: Settings
) -> None:
    adopted: list[tuple[Path, Path]] = []

    monkeypatch.setattr(
        "app.scaffold._adopt_ownership",
        lambda path, reference: adopted.append((path, reference)),
    )

    project_dir = ensure_project_layout(repo_templates_settings, "upgrade-check", "odoo-module")

    assert adopted == [(project_dir, repo_templates_settings.core_projects_dir)]
