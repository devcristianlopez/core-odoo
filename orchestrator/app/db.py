"""Database engine/session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


def make_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine_kwargs: dict[str, object] = {"connect_args": connect_args}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        engine_kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **engine_kwargs)


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    # Lightweight additive migration for the membership role. New installs get
    # the column from SQLModel; existing SQLite databases need the ALTER.
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("project_members")}
        if "role" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE project_members ADD COLUMN role "
                "VARCHAR(16) NOT NULL DEFAULT 'developer'"
            )


def session_from_factory(session_factory) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        yield session
