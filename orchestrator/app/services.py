"""Domain helpers shared by the API routers."""

from __future__ import annotations

import re
import secrets
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from .config import Settings
from .models import AuditEvent, Environment, Project, utcnow
from .providers.base import EnvironmentSpec
from .schemas import EnvironmentRead, ProjectRead

_DB_NAME_SAFE = re.compile(r"[^a-z0-9_]+")


def new_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def database_name(project: str, stage: str) -> str:
    base = _DB_NAME_SAFE.sub("_", project.lower().replace("-", "_")).strip("_")
    return f"{base}_{stage}"[:63]


def compose_project_name(project: str, stage: str) -> str:
    return f"core-{project}-{stage}"


def build_spec(settings: Settings, project: Project, environment: Environment) -> EnvironmentSpec:
    env_dir = settings.envs_dir / f"{project.name}-{environment.stage}"
    return EnvironmentSpec(
        project=project.name,
        stage=environment.stage,
        compose_project=environment.compose_project,
        env_dir=env_dir,
        project_dir=settings.core_projects_dir / project.name,
        addons_dir=settings.core_projects_dir / project.name / "odoo" / "addons",
        gateway_dir=settings.core_gateway_dir,
        backend_config=env_dir / "backend.yaml",
        db_name=environment.db_name,
        db_password=environment.db_password,
        master_password=environment.master_password,
        odoo_api_key=environment.odoo_api_key,
        gateway_jwt_secret=environment.gateway_jwt_secret,
        domain_suffix=settings.core_domain_suffix,
        template=project.template,
        branch=environment.branch,
        modules=list(environment.modules or []),
    )


def environment_url(settings: Settings, project: str, stage: str) -> str:
    return f"http://{project}-{stage}.core-odoo.{settings.core_domain_suffix}"


def environment_read(project_name: str, environment: Environment) -> EnvironmentRead:
    return EnvironmentRead(
        project=project_name,
        stage=environment.stage,
        status=environment.status,
        url=environment.url,
        compose_project=environment.compose_project,
        services=list(environment.services or []),
        created_at=environment.created_at,
        updated_at=environment.updated_at,
    )


def project_read(session: Session, project: Project) -> ProjectRead:
    environments = session.exec(
        select(Environment).where(Environment.project_id == project.id).order_by(Environment.stage)
    ).all()
    return ProjectRead(
        name=project.name,
        template=project.template,
        repo_url=project.repo_url,
        created_at=project.created_at,
        environments=[environment_read(project.name, env) for env in environments],
    )


def record_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    target: str,
    status: str = "success",
    details: dict[str, Any] | None = None,
    when: datetime | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor=actor,
        action=action,
        target=target,
        status=status,
        details=details or {},
        created_at=when or utcnow(),
    )
    session.add(event)
    return event
