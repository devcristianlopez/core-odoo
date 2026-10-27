"""Request/response models exposed by the API."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Stage = Literal["dev", "staging", "prod"]


class HealthResponse(BaseModel):
    status: str
    version: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


Role = Literal["admin", "operator", "viewer"]


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class PasswordChangeResponse(BaseModel):
    changed: bool = True


class MeResponse(BaseModel):
    username: str
    role: Role = "viewer"


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: Role = "viewer"


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=256)
    role: Role | None = None
    active: bool | None = None


class UserRead(BaseModel):
    username: str
    role: Role
    active: bool
    created_at: datetime


class EnvironmentRead(BaseModel):
    project: str
    stage: str
    status: str
    url: str
    compose_project: str
    services: list[dict[str, Any]] = Field(default_factory=list)
    branch: str | None = None
    modules: list[str] = Field(default_factory=list)
    last_good_iteration: str | None = None
    last_good_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProjectRead(BaseModel):
    name: str
    template: str
    repo_url: str | None = None
    created_at: datetime
    environments: list[EnvironmentRead] = Field(default_factory=list)


ProjectRole = Literal["owner", "developer", "viewer"]


class ProjectMemberCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    role: ProjectRole = "developer"


class ProjectMemberUpdate(BaseModel):
    role: ProjectRole


class ProjectMemberRead(BaseModel):
    username: str
    role: ProjectRole
    user_role: Role = "viewer"
    created_at: datetime


class ProjectAccessRead(BaseModel):
    role: Literal["admin", "owner", "developer", "viewer"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    template: str = Field(default="odoo-module", min_length=1, max_length=64)
    repo_url: str | None = Field(default=None, max_length=512)

    @field_validator("name")
    @classmethod
    def _slug(cls, value: str) -> str:
        candidate = value.strip().lower()
        if not candidate or not all(ch.isalnum() or ch == "-" for ch in candidate):
            raise ValueError("project name may only contain letters, numbers and dashes")
        if candidate[0] == "-" or candidate[-1] == "-":
            raise ValueError("project name cannot start or end with a dash")
        if len(candidate) < 2:
            raise ValueError("project name must be at least 2 characters long")
        return candidate

    @field_validator("template")
    @classmethod
    def _template_slug(cls, value: str) -> str:
        candidate = value.strip()
        if not re.match(r"^[a-z][a-z0-9-]{0,63}$", candidate):
            raise ValueError("template must be a lowercase slug")
        return candidate


class DeployRequest(BaseModel):
    stage: Stage
    branch: str | None = Field(default=None, max_length=255)
    modules: list[str] | None = None
    iteration: str | None = Field(default=None, max_length=32)
    confirm: str | None = Field(default=None, max_length=64)


class RollbackRequest(BaseModel):
    confirm: str | None = Field(default=None, max_length=64)


class PromoteRequest(BaseModel):
    source_stage: Stage = "staging"
    confirm: str | None = Field(default=None, max_length=64)
    neutralize: bool = True


class RestoreDatabaseRequest(BaseModel):
    stage: Stage = "dev"
    confirm: str | None = Field(default=None, max_length=64)


class IterationCreate(BaseModel):
    version: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=255)
    notes: str = Field(default="", max_length=8000)
    branch: str | None = Field(default=None, max_length=255)
    commit_sha: str | None = Field(default=None, max_length=64)
    modules: list[str] | None = None


class IterationRead(BaseModel):
    project: str
    version: str
    title: str
    notes: str
    status: str
    stage: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    modules: list[str] = Field(default_factory=list)
    has_snapshot: bool = True
    created_at: datetime
    deployed_at: datetime | None = None


class IterationDiff(BaseModel):
    project: str
    from_version: str | None = None
    to_version: str
    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class IterationBackupRead(BaseModel):
    project: str
    version: str
    stage: str
    path: str
    created_at: datetime


class DeploymentRequestCreate(BaseModel):
    iteration: str = Field(min_length=1, max_length=32)
    reason: str = Field(default="", max_length=2000)


class DeploymentRequestRead(BaseModel):
    id: int
    project: str
    stage: str
    iteration: str
    reason: str
    status: str
    requested_by: str
    decided_by: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    deployed_at: datetime | None = None


class DeletedResponse(BaseModel):
    deleted: bool = True


class LogsResponse(BaseModel):
    logs: str


class BackupResponse(BaseModel):
    backup: bool
    path: str
    created_at: datetime


class DockerStatus(BaseModel):
    available: bool
    version: str | None = None
    error: str | None = None


class DiskStatus(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


class StatusResponse(BaseModel):
    docker: DockerStatus
    disk: DiskStatus
    environments: int
    version: str


class AuditEventRead(BaseModel):
    id: int
    actor: str
    action: str
    target: str
    status: str
    details: dict[str, Any]
    created_at: datetime
