from __future__ import annotations

import os
import time
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.backups import backup_control_plane, prune_backups, run_backups_once
from app.config import Settings
from app.db import init_db, make_engine
from app.models import Environment, Project

from .conftest import FakeProvider


def _session_factory(settings: Settings):
    settings.ensure_dirs()
    engine = make_engine(settings.database_url)
    init_db(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _project_with_env(session_factory, *, with_compose: bool, settings: Settings) -> None:
    with session_factory() as session:
        project = Project(name="demo")
        session.add(project)
        session.commit()
        session.refresh(project)
        session.add(
            Environment(
                project_id=project.id,
                stage="dev",
                status="running",
                url="http://demo-dev.test",
                compose_project="core-demo-dev",
                db_name="demo_dev",
                db_password="x",
                master_password="x",
                odoo_api_key="x",
                gateway_jwt_secret="x",
            )
        )
        session.commit()
    if with_compose:
        env_dir = settings.envs_dir / "demo-dev"
        env_dir.mkdir(parents=True, exist_ok=True)
        (env_dir / "docker-compose.yml").write_text("name: x\n", encoding="utf-8")


def test_run_backups_once_dumps_environments_and_control_plane(settings: Settings) -> None:
    session_factory = _session_factory(settings)
    _project_with_env(session_factory, with_compose=True, settings=settings)
    provider = FakeProvider()

    created = run_backups_once(settings, session_factory, provider)

    scheduled = [path for path in created if path.name.startswith("scheduled-")]
    assert scheduled and scheduled[0].is_file()
    assert any(path.name.startswith("control-") for path in created)
    assert provider.calls[-1][0] == "backup"


def test_run_backups_once_skips_environments_without_compose(settings: Settings) -> None:
    session_factory = _session_factory(settings)
    _project_with_env(session_factory, with_compose=False, settings=settings)
    provider = FakeProvider()

    created = run_backups_once(settings, session_factory, provider)

    assert all(not path.name.startswith("scheduled-") for path in created)
    assert all(call[0] != "backup" for call in provider.calls)


def test_prune_backups_respects_the_retention_window(settings: Settings) -> None:
    directory = settings.backups_dir / "demo-dev"
    directory.mkdir(parents=True, exist_ok=True)
    old = directory / "scheduled-old.sql"
    old.write_text("old\n", encoding="utf-8")
    ten_days_ago = time.time() - 10 * 86400
    os.utime(old, (ten_days_ago, ten_days_ago))
    recent = directory / "scheduled-recent.sql"
    recent.write_text("new\n", encoding="utf-8")

    removed = prune_backups(settings, now=datetime.now(UTC))

    assert old in removed
    assert not old.exists()
    assert recent.exists()


def test_backup_control_plane_copies_the_sqlite_database(settings: Settings) -> None:
    _session_factory(settings)

    path = backup_control_plane(settings, now=datetime.now(UTC))

    assert path is not None and path.is_file()
    assert path.parent.name == "control-plane"
