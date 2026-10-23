"""Persistent state for the orchestrator (SQLite via SQLModel)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

VALID_STAGES: tuple[str, ...] = ("dev", "staging", "prod")


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=64)
    password_hash: str = Field(max_length=255)
    role: str = Field(default="viewer", max_length=16)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=64)
    template: str = Field(default="odoo-module", max_length=64)
    repo_url: str | None = Field(default=None, max_length=512)
    created_at: datetime = Field(default_factory=utcnow)


class ProjectMember(SQLModel, table=True):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Environment(SQLModel, table=True):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "stage", name="uq_environment_project_stage"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    stage: str = Field(index=True, max_length=16)
    status: str = Field(default="stopped", max_length=32)
    url: str = Field(default="", max_length=512)
    compose_project: str = Field(max_length=128)
    services: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    branch: str | None = Field(default=None, max_length=255)
    modules: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    # Per-environment secrets. Never serialized by the API.
    db_name: str = Field(max_length=64)
    db_password: str = Field(max_length=128)
    master_password: str = Field(max_length=128)
    odoo_api_key: str = Field(max_length=128)
    gateway_jwt_secret: str = Field(max_length=128)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Iteration(SQLModel, table=True):
    """Immutable snapshot of a project iteration over time."""

    __tablename__ = "iterations"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_iteration_project_version"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    version: str = Field(index=True, max_length=32)
    title: str = Field(max_length=255)
    notes: str = Field(default="", max_length=8000)
    status: str = Field(default="created", max_length=32)
    stage: str | None = Field(default=None, max_length=16)
    branch: str | None = Field(default=None, max_length=255)
    commit_sha: str | None = Field(default=None, max_length=64)
    modules: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    snapshot_path: str = Field(max_length=512)
    created_at: datetime = Field(default_factory=utcnow)
    deployed_at: datetime | None = Field(default=None)


class IterationBackup(SQLModel, table=True):
    """Database dump associated with an iteration snapshot."""

    __tablename__ = "iteration_backups"

    id: int | None = Field(default=None, primary_key=True)
    iteration_id: int = Field(foreign_key="iterations.id", index=True)
    stage: str = Field(max_length=16)
    path: str = Field(max_length=512)
    created_at: datetime = Field(default_factory=utcnow)


class DeploymentRequest(SQLModel, table=True):
    __tablename__ = "deployment_requests"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    stage: str = Field(default="prod", max_length=16)
    iteration: str = Field(max_length=32)
    reason: str = Field(default="", max_length=2000)
    status: str = Field(default="pending", max_length=16)
    requested_by: str = Field(max_length=64)
    decided_by: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = Field(default=None)
    deployed_at: datetime | None = Field(default=None)


class AuditEvent(SQLModel, table=True):
    __tablename__ = "audit_events"

    id: int | None = Field(default=None, primary_key=True)
    actor: str = Field(default="system", max_length=128)
    action: str = Field(index=True, max_length=64)
    target: str = Field(default="", max_length=255)
    status: str = Field(default="success", max_length=16)
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, index=True)
