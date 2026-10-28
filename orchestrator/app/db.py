"""Database engine/session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# Additive migrations for columns introduced after the first release. New
# installs get these columns from SQLModel; existing SQLite databases need an
# ALTER TABLE. Both statements must stay backwards compatible: they only add
# nullable columns or columns with a default.
ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "project_members": {"role": "VARCHAR(16) NOT NULL DEFAULT 'developer'"},
    "environments": {
        "last_good_iteration": "VARCHAR(32)",
        "last_good_at": "DATETIME",
        "admin_password": "VARCHAR(128)",
    },
}


def make_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine_kwargs: dict[str, object] = {"connect_args": connect_args}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        engine_kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **engine_kwargs)


def _add_missing_columns(connection: Connection) -> None:
    """ALTER existing tables that predate a column declared in the models."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    for table, columns in ADDITIVE_COLUMNS.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name in existing:
                continue
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        _add_missing_columns(connection)


def session_from_factory(session_factory) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        yield session
