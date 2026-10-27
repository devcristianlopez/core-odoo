"""Project and environment lifecycle endpoints."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from ..deps import (
    AdminDep,
    PrincipalDep,
    ProviderDep,
    SessionDep,
    SettingsDep,
    require_project_access,
    require_write,
)
from ..metrics import record_backup_success, record_deploy
from ..models import (
    DeploymentRequest,
    Environment,
    Iteration,
    IterationBackup,
    Project,
    ProjectMember,
    User,
    utcnow,
)
from ..providers.base import EnvironmentSpec, ProviderError, ProviderStatus
from ..providers.docker import backup_filename
from ..scaffold import ensure_project_layout
from ..schemas import (
    BackupResponse,
    DeletedResponse,
    DeploymentRequestCreate,
    DeploymentRequestRead,
    DeployRequest,
    EnvironmentRead,
    LogsResponse,
    ProjectAccessRead,
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    PromoteRequest,
    RollbackRequest,
)
from ..services import (
    build_spec,
    compose_project_name,
    database_name,
    environment_read,
    environment_url,
    new_secret,
    project_read,
    record_audit,
    restore_iteration_snapshot,
)

router = APIRouter(
    tags=["projects"],
    dependencies=[Depends(require_project_access), Depends(require_write)],
)

ProviderOperation = Callable[[EnvironmentSpec], ProviderStatus]


# --------------------------------------------------------------------- helpers


def _get_project(session: SessionDep, name: str) -> Project:
    project = session.exec(select(Project).where(Project.name == name)).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


def _get_environment(session: SessionDep, project: Project, stage: str) -> Environment:
    environment = session.exec(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.stage == stage,
        )
    ).first()
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="environment not found")
    return environment


def _audit_failure(
    session: SessionDep,
    *,
    actor: str,
    action: str,
    target: str,
    exc: ProviderError,
) -> None:
    record_audit(
        session,
        actor=actor,
        action=action,
        target=target,
        status="failed",
        details={"error": exc.message, "output": exc.details},
    )
    session.commit()


# --------------------------------------------------------------------- projects


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(session: SessionDep, principal: PrincipalDep) -> list[ProjectRead]:
    if principal.role == "admin":
        projects = session.exec(select(Project).order_by(Project.name)).all()
    else:
        user = session.exec(select(User).where(User.username == principal.username)).first()
        if user is None:
            return []
        project_ids = session.exec(
            select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        ).all()
        projects = session.exec(
            select(Project).where(Project.id.in_(project_ids)).order_by(Project.name)
        ).all()
    return [project_read(session, project) for project in projects]


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    session: SessionDep,
    principal: AdminDep,
    settings: SettingsDep,
) -> ProjectRead:
    existing = session.exec(select(Project).where(Project.name == payload.name)).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="project already exists")

    ensure_project_layout(settings, payload.name, payload.template)
    project = Project(
        name=payload.name,
        template=payload.template,
        repo_url=payload.repo_url,
        created_at=utcnow(),
    )
    session.add(project)
    session.flush()
    record_audit(
        session,
        actor=principal.username,
        action="project.create",
        target=payload.name,
        details={"template": payload.template, "repo_url": payload.repo_url},
    )
    session.commit()
    session.refresh(project)
    return project_read(session, project)


@router.get("/projects/{name}/access", response_model=ProjectAccessRead)
def project_access(
    name: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> ProjectAccessRead:
    project = _get_project(session, name)
    if principal.role == "admin" or principal.method == "api_token":
        return ProjectAccessRead(role="admin")
    user = session.exec(select(User).where(User.username == principal.username)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="project access denied")
    member = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="project access denied")
    return ProjectAccessRead(role=member.role)  # type: ignore[arg-type]


@router.get("/projects/{name}", response_model=ProjectRead)
def get_project(name: str, session: SessionDep, principal: PrincipalDep) -> ProjectRead:
    project = _get_project(session, name)
    return project_read(session, project)


@router.delete("/projects/{name}", response_model=DeletedResponse)
def delete_project(
    name: str,
    session: SessionDep,
    principal: AdminDep,
    provider: ProviderDep,
    settings: SettingsDep,
    confirm: str = Query(..., min_length=1, max_length=64),
    purge: bool = Query(default=False),
) -> DeletedResponse:
    if confirm != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm must exactly match the project name",
        )
    project = _get_project(session, name)
    environments = session.exec(
        select(Environment).where(Environment.project_id == project.id)
    ).all()

    for environment in environments:
        spec = build_spec(settings, project, environment)
        try:
            provider.delete(spec)
        except ProviderError as exc:
            _audit_failure(
                session,
                actor=principal.username,
                action="project.delete",
                target=name,
                exc=exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message
            ) from exc

    for environment in environments:
        session.delete(environment)
    members = session.exec(
        select(ProjectMember).where(ProjectMember.project_id == project.id)
    ).all()
    for member in members:
        session.delete(member)
    session.delete(project)
    if purge:
        for path in (
            settings.core_projects_dir / name,
            settings.iterations_dir / name,
        ):
            if path.exists():
                shutil.rmtree(path)
        for backup_dir in settings.backups_dir.glob(f"{name}-*"):
            if backup_dir.is_dir():
                shutil.rmtree(backup_dir)
    record_audit(
        session,
        actor=principal.username,
        action="project.delete",
        target=name,
        details={
            "environments": [env.stage for env in environments],
            "purged": purge,
        },
    )
    session.commit()
    return DeletedResponse(deleted=True)


# ------------------------------------------------------------- deploy requests


@router.post(
    "/projects/{name}/deploy-requests",
    response_model=DeploymentRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_deploy_request(
    name: str,
    payload: DeploymentRequestCreate,
    session: SessionDep,
    principal: PrincipalDep,
) -> DeploymentRequestRead:
    project = _get_project(session, name)
    iteration = session.exec(
        select(Iteration).where(
            Iteration.project_id == project.id,
            Iteration.version == payload.iteration,
        )
    ).first()
    if iteration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="iteration not found")
    if (
        session.exec(
            select(IterationBackup).where(IterationBackup.iteration_id == iteration.id)
        ).first()
        is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the iteration needs a database backup before requesting production",
        )
    pending = session.exec(
        select(DeploymentRequest).where(
            DeploymentRequest.project_id == project.id,
            DeploymentRequest.status == "pending",
        )
    ).first()
    if pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="there is already a pending production request for this project",
        )
    request = DeploymentRequest(
        project_id=project.id,
        stage="prod",
        iteration=payload.iteration,
        reason=payload.reason,
        requested_by=principal.username,
        status="pending",
    )
    session.add(request)
    record_audit(
        session,
        actor=principal.username,
        action="deploy_request.create",
        target=f"{name}/{payload.iteration}",
        details={"reason": payload.reason},
    )
    session.commit()
    session.refresh(request)
    return DeploymentRequestRead(
        id=request.id or 0,
        project=name,
        stage=request.stage,
        iteration=request.iteration,
        reason=request.reason,
        status=request.status,
        requested_by=request.requested_by,
        created_at=request.created_at,
    )


# --------------------------------------------------------------------- members


@router.get("/projects/{name}/members", response_model=list[ProjectMemberRead])
def list_project_members(
    name: str,
    session: SessionDep,
    principal: AdminDep,
) -> list[ProjectMemberRead]:
    project = _get_project(session, name)
    members = session.exec(
        select(ProjectMember).where(ProjectMember.project_id == project.id)
    ).all()
    result: list[ProjectMemberRead] = []
    for member in members:
        user = session.get(User, member.user_id)
        if user is not None:
            result.append(
                ProjectMemberRead(
                    username=user.username,
                    role=member.role,  # type: ignore[arg-type]
                    user_role=user.role,  # type: ignore[arg-type]
                    created_at=member.created_at,
                )
            )
    return sorted(result, key=lambda item: item.username)


@router.post(
    "/projects/{name}/members",
    response_model=ProjectMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    name: str,
    payload: ProjectMemberCreate,
    session: SessionDep,
    principal: AdminDep,
) -> ProjectMemberRead:
    project = _get_project(session, name)
    user = session.exec(select(User).where(User.username == payload.username)).first()
    if user is None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found or inactive"
        )
    existing = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user is already a member")
    member = ProjectMember(project_id=project.id, user_id=user.id, role=payload.role)
    session.add(member)
    record_audit(
        session,
        actor=principal.username,
        action="project.member.add",
        target=f"{name}/{user.username}",
        details={"role": user.role},
    )
    session.commit()
    session.refresh(member)
    return ProjectMemberRead(
        username=user.username,
        role=member.role,  # type: ignore[arg-type]
        user_role=user.role,  # type: ignore[arg-type]
        created_at=member.created_at,
    )


@router.patch(
    "/projects/{name}/members/{username}",
    response_model=ProjectMemberRead,
)
def update_project_member(
    name: str,
    username: str,
    payload: ProjectMemberUpdate,
    session: SessionDep,
    principal: AdminDep,
) -> ProjectMemberRead:
    project = _get_project(session, name)
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    member = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    member.role = payload.role
    session.add(member)
    record_audit(
        session,
        actor=principal.username,
        action="project.member.update",
        target=f"{name}/{username}",
        details={"role": payload.role},
    )
    session.commit()
    session.refresh(member)
    return ProjectMemberRead(
        username=user.username,
        role=member.role,  # type: ignore[arg-type]
        user_role=user.role,  # type: ignore[arg-type]
        created_at=member.created_at,
    )


@router.delete("/projects/{name}/members/{username}", response_model=DeletedResponse)
def remove_project_member(
    name: str,
    username: str,
    session: SessionDep,
    principal: AdminDep,
) -> DeletedResponse:
    project = _get_project(session, name)
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    member = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    session.delete(member)
    record_audit(
        session,
        actor=principal.username,
        action="project.member.remove",
        target=f"{name}/{username}",
    )
    session.commit()
    return DeletedResponse(deleted=True)


# ----------------------------------------------------------------- environments


@router.get("/projects/{name}/environments", response_model=list[EnvironmentRead])
def list_environments(
    name: str, session: SessionDep, principal: PrincipalDep
) -> list[EnvironmentRead]:
    project = _get_project(session, name)
    environments = session.exec(
        select(Environment).where(Environment.project_id == project.id).order_by(Environment.stage)
    ).all()
    return [environment_read(project.name, env) for env in environments]


@router.post(
    "/projects/{name}/deploy",
    response_model=EnvironmentRead,
)
def deploy(
    name: str,
    payload: DeployRequest,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
) -> EnvironmentRead:
    if payload.stage == "prod" and principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="production deploys require the admin role",
        )
    project = _get_project(session, name)
    if payload.stage == "prod":
        if payload.confirm != name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="confirm must exactly match the project name for production",
            )
        if not payload.iteration:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="production deploys require a versioned iteration",
            )
        iteration = session.exec(
            select(Iteration).where(
                Iteration.project_id == project.id,
                Iteration.version == payload.iteration,
            )
        ).first()
        if iteration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="iteration not found")
        backups = session.exec(
            select(IterationBackup).where(IterationBackup.iteration_id == iteration.id)
        ).all()
        if not backups:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="production deploys require a database backup for the iteration",
            )
        try:
            restore_iteration_snapshot(settings, name, iteration.snapshot_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    environment = session.exec(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.stage == payload.stage,
        )
    ).first()

    # Whether module updates (-u) are safe is decided by the provider, which
    # probes the actual database: retrying after a failed deploy must apply the
    # pending module upgrades even though the environment is still in ``error``.
    # A brand-new environment has no database yet, so the provider falls back
    # to the normal install path.
    update_modules = environment is not None

    now = utcnow()
    if environment is None:
        environment = Environment(
            project_id=project.id,
            stage=payload.stage,
            status="provisioning",
            url=environment_url(settings, project.name, payload.stage),
            compose_project=compose_project_name(project.name, payload.stage),
            services=[],
            branch=payload.branch,
            modules=list(payload.modules or []),
            db_name=database_name(project.name, payload.stage),
            db_password=new_secret(24),
            master_password=new_secret(24),
            odoo_api_key=new_secret(32),
            gateway_jwt_secret=new_secret(32),
            created_at=now,
            updated_at=now,
        )
        session.add(environment)
    else:
        environment.branch = payload.branch
        # Omitting ``modules`` keeps the stored list: the first deploy discovers
        # and stores the project addons, and a later deploy without --modules
        # must not erase them (otherwise module updates are silently skipped).
        if payload.modules is not None:
            environment.modules = list(payload.modules)
        environment.status = "provisioning"
        environment.updated_at = now
    session.commit()
    session.refresh(environment)

    spec = build_spec(settings, project, environment)
    try:
        result = provider.deploy(spec, update=update_modules)
    except ProviderError as exc:
        record_deploy(name, payload.stage, "failed")
        if payload.iteration:
            iteration = session.exec(
                select(Iteration).where(
                    Iteration.project_id == project.id,
                    Iteration.version == payload.iteration,
                )
            ).first()
            if iteration is not None:
                iteration.status = "failed"
                iteration.stage = payload.stage
                session.add(iteration)
        environment.status = "error"
        environment.updated_at = utcnow()
        session.add(environment)
        _audit_failure(
            session,
            actor=principal.username,
            action="environment.deploy",
            target=f"{name}/{payload.stage}",
            exc=exc,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc

    record_deploy(name, payload.stage, "success")
    if payload.iteration:
        iteration = session.exec(
            select(Iteration).where(
                Iteration.project_id == project.id,
                Iteration.version == payload.iteration,
            )
        ).first()
        if iteration is not None:
            iteration.status = "deployed"
            iteration.stage = payload.stage
            iteration.deployed_at = utcnow()
            session.add(iteration)
        # Only iteration deploys move the rollback target; iteration-less
        # deploys must keep the previous last-good values.
        environment.last_good_iteration = payload.iteration
        environment.last_good_at = utcnow()
    environment.status = result.status or "running"
    environment.services = result.services
    environment.url = spec.url
    environment.updated_at = utcnow()
    session.add(environment)
    record_audit(
        session,
        actor=principal.username,
        action="environment.deploy",
        target=f"{name}/{payload.stage}",
        details={
            "branch": payload.branch,
            "modules": list(payload.modules or []),
            "iteration": payload.iteration,
            "services": [service.get("name") for service in result.services],
        },
    )
    session.commit()
    session.refresh(environment)
    return environment_read(name, environment)


def _environment_action(
    *,
    action: str,
    name: str,
    stage: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
    operation: ProviderOperation,
) -> EnvironmentRead:
    project = _get_project(session, name)
    environment = _get_environment(session, project, stage)
    spec = build_spec(settings, project, environment)
    try:
        result = operation(spec)
    except ProviderError as exc:
        environment.status = "error"
        environment.updated_at = utcnow()
        session.add(environment)
        _audit_failure(
            session,
            actor=principal.username,
            action=action,
            target=f"{name}/{stage}",
            exc=exc,
        )
        code = (
            status.HTTP_409_CONFLICT
            if "has not been deployed" in exc.message
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=code, detail=exc.message) from exc

    environment.status = result.status
    environment.services = result.services
    environment.updated_at = utcnow()
    session.add(environment)
    record_audit(
        session,
        actor=principal.username,
        action=action,
        target=f"{name}/{stage}",
        details={"status": result.status},
    )
    session.commit()
    session.refresh(environment)
    return environment_read(name, environment)


@router.post("/projects/{name}/environments/{stage}/start", response_model=EnvironmentRead)
def start_environment(
    name: str,
    stage: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
) -> EnvironmentRead:
    return _environment_action(
        action="environment.start",
        name=name,
        stage=stage,
        session=session,
        principal=principal,
        provider=provider,
        settings=settings,
        operation=provider.start,
    )


@router.post("/projects/{name}/environments/{stage}/stop", response_model=EnvironmentRead)
def stop_environment(
    name: str,
    stage: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
) -> EnvironmentRead:
    return _environment_action(
        action="environment.stop",
        name=name,
        stage=stage,
        session=session,
        principal=principal,
        provider=provider,
        settings=settings,
        operation=provider.stop,
    )


@router.post("/projects/{name}/environments/{stage}/restart", response_model=EnvironmentRead)
def restart_environment(
    name: str,
    stage: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
) -> EnvironmentRead:
    return _environment_action(
        action="environment.restart",
        name=name,
        stage=stage,
        session=session,
        principal=principal,
        provider=provider,
        settings=settings,
        operation=provider.restart,
    )


@router.post(
    "/projects/{name}/environments/{stage}/rollback",
    response_model=EnvironmentRead,
)
def rollback_environment(
    name: str,
    stage: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
    payload: RollbackRequest | None = None,
) -> EnvironmentRead:
    confirm = payload.confirm if payload is not None else None
    if stage == "prod" and principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="production deploys require the admin role",
        )
    project = _get_project(session, name)
    if stage == "prod" and confirm != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm must exactly match the project name for production",
        )
    environment = _get_environment(session, project, stage)
    version = environment.last_good_iteration
    if not version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no successful iteration to roll back to",
        )
    iteration = session.exec(
        select(Iteration).where(
            Iteration.project_id == project.id,
            Iteration.version == version,
        )
    ).first()
    if iteration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="iteration not found")
    try:
        restore_iteration_snapshot(settings, name, iteration.snapshot_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    environment.status = "provisioning"
    environment.updated_at = utcnow()
    session.add(environment)
    session.commit()
    session.refresh(environment)

    spec = build_spec(settings, project, environment)
    try:
        result = provider.deploy(spec, update=True)
    except ProviderError as exc:
        environment.status = "error"
        environment.updated_at = utcnow()
        session.add(environment)
        record_deploy(name, stage, "failed")
        _audit_failure(
            session,
            actor=principal.username,
            action="environment.rollback",
            target=f"{name}/{stage}",
            exc=exc,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc

    environment.status = result.status
    environment.services = result.services
    environment.url = spec.url
    environment.last_good_at = utcnow()
    environment.updated_at = utcnow()
    session.add(environment)
    record_deploy(name, stage, "success")
    record_audit(
        session,
        actor=principal.username,
        action="environment.rollback",
        target=f"{name}/{stage}",
        details={"iteration": version},
    )
    session.commit()
    session.refresh(environment)
    return environment_read(name, environment)


@router.post("/projects/{name}/promote", response_model=EnvironmentRead)
def promote_environment(
    name: str,
    payload: PromoteRequest,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
) -> EnvironmentRead:
    """Clone a source environment database into production and neutralize it."""
    if principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="promotions require the admin role",
        )
    if payload.confirm != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm must exactly match the project name for production",
        )
    if payload.source_stage == "prod":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="the source stage must be dev or staging",
        )
    project = _get_project(session, name)
    source = session.exec(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.stage == payload.source_stage,
        )
    ).first()
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"source environment {payload.source_stage} not found",
        )

    now = utcnow()
    target = session.exec(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.stage == "prod",
        )
    ).first()
    target_existed = target is not None
    if target is None:
        target = Environment(
            project_id=project.id,
            stage="prod",
            status="provisioning",
            url=environment_url(settings, project.name, "prod"),
            compose_project=compose_project_name(project.name, "prod"),
            services=[],
            modules=[],
            db_name=database_name(project.name, "prod"),
            db_password=new_secret(24),
            master_password=new_secret(24),
            odoo_api_key=new_secret(32),
            gateway_jwt_secret=new_secret(32),
            created_at=now,
            updated_at=now,
        )
        session.add(target)
    else:
        target.status = "provisioning"
        target.updated_at = now
    session.commit()
    session.refresh(target)

    source_spec = build_spec(settings, project, source)
    target_spec = build_spec(settings, project, target)
    dump = (
        settings.backups_dir
        / f"{name}-{source.stage}"
        / f"promote-{now.strftime('%Y%m%dT%H%M%S')}.sql"
    )

    try:
        provider.prepare(target_spec)
        provider.backup(source_spec, dump)
        provider.restore_database(target_spec, dump)
        if payload.neutralize:
            provider.neutralize_database(target_spec, target_spec.url)
        result = provider.deploy(target_spec, update=target_existed)
    except ProviderError as exc:
        target.status = "error"
        target.updated_at = utcnow()
        session.add(target)
        record_deploy(name, "prod", "failed")
        _audit_failure(
            session,
            actor=principal.username,
            action="environment.promote",
            target=f"{name}/prod",
            exc=exc,
        )
        code = (
            status.HTTP_409_CONFLICT
            if "has not been deployed" in exc.message
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=code, detail=exc.message) from exc

    target.status = result.status
    target.services = result.services
    target.url = target_spec.url
    target.updated_at = utcnow()
    session.add(target)
    record_deploy(name, "prod", "success")
    record_audit(
        session,
        actor=principal.username,
        action="environment.promote",
        target=f"{name}/prod",
        details={
            "source": source.stage,
            "dump": str(dump),
            "neutralized": payload.neutralize,
        },
    )
    session.commit()
    session.refresh(target)
    return environment_read(name, target)


@router.delete("/projects/{name}/environments/{stage}", response_model=DeletedResponse)
def delete_environment(
    name: str,
    stage: str,
    session: SessionDep,
    principal: AdminDep,
    provider: ProviderDep,
    settings: SettingsDep,
    confirm: str = Query(..., min_length=1, max_length=80),
) -> DeletedResponse:
    if confirm != f"{name}/{stage}":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm must match '<project>/<stage>'",
        )
    project = _get_project(session, name)
    environment = _get_environment(session, project, stage)
    spec = build_spec(settings, project, environment)
    try:
        provider.delete(spec)
    except ProviderError as exc:
        _audit_failure(
            session,
            actor=principal.username,
            action="environment.delete",
            target=f"{name}/{stage}",
            exc=exc,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc

    session.delete(environment)
    record_audit(
        session,
        actor=principal.username,
        action="environment.delete",
        target=f"{name}/{stage}",
    )
    session.commit()
    return DeletedResponse(deleted=True)


@router.get("/projects/{name}/environments/{stage}/logs", response_model=LogsResponse)
def environment_logs(
    name: str,
    stage: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
    tail: int = Query(default=200, ge=1, le=10000),
) -> LogsResponse:
    project = _get_project(session, name)
    environment = _get_environment(session, project, stage)
    spec = build_spec(settings, project, environment)
    try:
        logs = provider.logs(spec, tail)
    except ProviderError as exc:
        code = (
            status.HTTP_409_CONFLICT
            if "has not been deployed" in exc.message
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=code, detail=exc.message) from exc
    return LogsResponse(logs=logs)


@router.post(
    "/projects/{name}/environments/{stage}/backup",
    response_model=BackupResponse,
    status_code=status.HTTP_201_CREATED,
)
def backup_environment(
    name: str,
    stage: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
) -> BackupResponse:
    project = _get_project(session, name)
    environment = _get_environment(session, project, stage)
    spec = build_spec(settings, project, environment)
    created_at = datetime.now(UTC)
    destination = (
        settings.backups_dir / f"{name}-{stage}" / backup_filename(name, stage, created_at)
    )
    try:
        path = provider.backup(spec, destination)
    except ProviderError as exc:
        _audit_failure(
            session,
            actor=principal.username,
            action="environment.backup",
            target=f"{name}/{stage}",
            exc=exc,
        )
        code = (
            status.HTTP_409_CONFLICT
            if "has not been deployed" in exc.message
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=code, detail=exc.message) from exc

    record_backup_success(name, stage, created_at.timestamp())
    record_audit(
        session,
        actor=principal.username,
        action="environment.backup",
        target=f"{name}/{stage}",
        details={"path": str(path)},
    )
    session.commit()
    return BackupResponse(backup=True, path=str(path), created_at=created_at)
