"""Domain helpers shared by the API routers."""

from __future__ import annotations

import hashlib
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from .config import Settings
from .models import AuditEvent, Environment, Iteration, Project, utcnow
from .providers.base import EnvironmentSpec
from .schemas import EnvironmentRead, IterationRead, ProjectRead

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
        branch=environment.branch,
        modules=list(environment.modules or []),
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


ITERATION_IGNORE = shutil.ignore_patterns(
    "node_modules",
    "dist",
    ".vite",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".git",
    ".env",
    "*.log",
)


def create_iteration_snapshot(settings: Settings, project_name: str, version: str) -> str:
    """Copy the project source into an immutable iteration directory."""
    source = settings.core_projects_dir / project_name
    if not source.is_dir():
        raise FileNotFoundError(f"project source not found: {source}")
    target = settings.iterations_dir / project_name / version
    if target.exists():
        raise FileExistsError(f"iteration snapshot already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=ITERATION_IGNORE)
    return str(target)


def restore_iteration_snapshot(settings: Settings, project_name: str, snapshot_path: str) -> None:
    """Restore a project source tree from an iteration snapshot."""
    snapshot = Path(snapshot_path)
    if not snapshot.is_dir():
        raise FileNotFoundError(f"iteration snapshot not found: {snapshot}")
    target = settings.core_projects_dir / project_name
    target.mkdir(parents=True, exist_ok=True)
    for name in ("backend.yaml", "odoo", "frontend", "odoo-sh.yaml", "README.md"):
        path = target / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    shutil.copytree(snapshot, target, dirs_exist_ok=True)


def snapshot_manifest(path: Path) -> dict[str, str]:
    """Hash every file in a snapshot so iterations can be compared."""
    manifest: dict[str, str] = {}
    root = Path(path)
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        relative = str(file_path.relative_to(root))
        manifest[relative] = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return manifest


def diff_snapshots(from_path: Path, to_path: Path) -> dict[str, list[str]]:
    from_manifest = snapshot_manifest(from_path)
    to_manifest = snapshot_manifest(to_path)
    from_files = set(from_manifest)
    to_files = set(to_manifest)
    return {
        "added": sorted(to_files - from_files),
        "modified": sorted(
            name for name in from_files & to_files if from_manifest[name] != to_manifest[name]
        ),
        "deleted": sorted(from_files - to_files),
    }


def iteration_read(project_name: str, iteration: Iteration) -> IterationRead:
    return IterationRead(
        project=project_name,
        version=iteration.version,
        title=iteration.title,
        notes=iteration.notes,
        status=iteration.status,
        stage=iteration.stage,
        branch=iteration.branch,
        commit_sha=iteration.commit_sha,
        modules=list(iteration.modules or []),
        has_snapshot=Path(iteration.snapshot_path).is_dir(),
        created_at=iteration.created_at,
        deployed_at=iteration.deployed_at,
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
