"""Additive schema migrations must upgrade databases created before the columns.

The orchestrator ships without Alembic: ``init_db`` creates missing tables from
SQLModel and then ALTERs pre-existing tables. These tests build the *old* shape
by hand so the upgrade path is exercised for real.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.db import init_db, make_engine
from app.models import Environment

OLD_ENVIRONMENTS_DDL = """
CREATE TABLE environments (
    id INTEGER NOT NULL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects (id),
    stage VARCHAR(16) NOT NULL,
    status VARCHAR(32) NOT NULL,
    url VARCHAR(512) NOT NULL,
    compose_project VARCHAR(128) NOT NULL,
    services JSON NOT NULL,
    branch VARCHAR(255),
    modules JSON NOT NULL,
    db_name VARCHAR(64) NOT NULL,
    db_password VARCHAR(128) NOT NULL,
    master_password VARCHAR(128) NOT NULL,
    odoo_api_key VARCHAR(128) NOT NULL,
    gateway_jwt_secret VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_environment_project_stage UNIQUE (project_id, stage)
)
"""

OLD_PROJECT_MEMBERS_DDL = """
CREATE TABLE project_members (
    id INTEGER NOT NULL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects (id),
    user_id INTEGER NOT NULL REFERENCES users (id),
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_project_member UNIQUE (project_id, user_id)
)
"""

OLD_ENVIRONMENT_INSERT = """
INSERT INTO environments (id, project_id, stage, status, url, compose_project, services,
    branch, modules, db_name, db_password, master_password, odoo_api_key,
    gateway_jwt_secret, created_at, updated_at)
VALUES (1, 1, 'dev', 'running', 'http://legacy', 'core-legacy-dev', '[]', 'main', '[]',
    'legacy_dev', 'db', 'master', 'key', 'jwt', '2026-01-01 00:00:00',
    '2026-01-01 00:00:00')
"""

OLD_PROJECT_MEMBER_INSERT = """
INSERT INTO project_members (id, project_id, user_id, created_at)
VALUES (1, 1, 1, '2026-01-01 00:00:00')
"""


@pytest.fixture
def old_schema_engine(tmp_path: Path) -> Iterator[Engine]:
    """SQLite database with the previous environments/project_members shape."""
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(OLD_ENVIRONMENTS_DDL)
        connection.exec_driver_sql(OLD_PROJECT_MEMBERS_DDL)
        connection.exec_driver_sql(OLD_ENVIRONMENT_INSERT)
        connection.exec_driver_sql(OLD_PROJECT_MEMBER_INSERT)
    yield engine
    engine.dispose()


def test_init_db_adds_environment_last_good_columns(old_schema_engine: Engine) -> None:
    init_db(old_schema_engine)

    with old_schema_engine.connect() as connection:
        columns = {
            column["name"]: column for column in inspect(connection).get_columns("environments")
        }

    assert "last_good_iteration" in columns
    assert "last_good_at" in columns
    for name in ("last_good_iteration", "last_good_at"):
        assert columns[name]["nullable"] is True
        assert columns[name]["default"] is None


def test_init_db_keeps_project_members_role_migration(old_schema_engine: Engine) -> None:
    init_db(old_schema_engine)

    with old_schema_engine.connect() as connection:
        columns = {
            column["name"]: column for column in inspect(connection).get_columns("project_members")
        }
        role = connection.exec_driver_sql("SELECT role FROM project_members WHERE id = 1").scalar()

    assert "role" in columns
    assert columns["role"]["nullable"] is False
    assert role == "developer"


def test_init_db_is_idempotent(old_schema_engine: Engine) -> None:
    init_db(old_schema_engine)
    init_db(old_schema_engine)

    with old_schema_engine.connect() as connection:
        environment_columns = {
            column["name"] for column in inspect(connection).get_columns("environments")
        }
        member_columns = {
            column["name"] for column in inspect(connection).get_columns("project_members")
        }

    assert {"last_good_iteration", "last_good_at"} <= environment_columns
    assert "role" in member_columns


def test_migrated_row_reads_null_last_good(old_schema_engine: Engine) -> None:
    init_db(old_schema_engine)

    with Session(old_schema_engine) as session:
        environment = session.get(Environment, 1)

    assert environment is not None
    assert environment.stage == "dev"
    assert environment.branch == "main"
    assert environment.last_good_iteration is None
    assert environment.last_good_at is None


def test_new_environment_can_record_last_good(old_schema_engine: Engine) -> None:
    init_db(old_schema_engine)

    deployed_at = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
    with Session(old_schema_engine) as session:
        environment = session.get(Environment, 1)
        assert environment is not None
        environment.last_good_iteration = "0.1.0"
        environment.last_good_at = deployed_at
        session.add(environment)
        session.commit()

    with Session(old_schema_engine) as session:
        environment = session.get(Environment, 1)

    assert environment is not None
    assert environment.last_good_iteration == "0.1.0"
    assert environment.last_good_at == deployed_at
