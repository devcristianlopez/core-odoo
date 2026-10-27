"""Versioned project iterations and source snapshots."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from ..deps import (
    PrincipalDep,
    ProviderDep,
    SessionDep,
    SettingsDep,
    require_project_access,
    require_write,
)
from ..metrics import record_deploy
from ..models import Environment, Iteration, IterationBackup, Project, utcnow
from ..providers.base import ProviderError
from ..providers.docker import backup_filename
from ..schemas import (
    EnvironmentRead,
    IterationBackupRead,
    IterationCreate,
    IterationDiff,
    IterationRead,
    RestoreDatabaseRequest,
)
from ..services import (
    build_spec,
    create_iteration_snapshot,
    diff_snapshots,
    environment_read,
    iteration_read,
    record_audit,
    restore_iteration_snapshot,
    snapshot_manifest,
)

router = APIRouter(
    tags=["iterations"],
    dependencies=[Depends(require_project_access), Depends(require_write)],
)


def _get_project(session: SessionDep, name: str) -> Project:
    project = session.exec(select(Project).where(Project.name == name)).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


def _get_iteration(session: SessionDep, project: Project, version: str) -> Iteration:
    iteration = session.exec(
        select(Iteration).where(
            Iteration.project_id == project.id,
            Iteration.version == version,
        )
    ).first()
    if iteration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="iteration not found")
    return iteration


def _get_environment(session: SessionDep, project: Project, stage: str) -> Environment:
    environment = session.exec(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.stage == stage,
        )
    ).first()
    if environment is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="environment not deployed")
    return environment


@router.get("/projects/{name}/iterations", response_model=list[IterationRead])
def list_iterations(
    name: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> list[IterationRead]:
    project = _get_project(session, name)
    iterations = session.exec(
        select(Iteration)
        .where(Iteration.project_id == project.id)
        .order_by(Iteration.created_at.desc())
    ).all()
    return [iteration_read(name, iteration) for iteration in iterations]


@router.get(
    "/projects/{name}/iterations/{version}",
    response_model=IterationRead,
)
def get_iteration(
    name: str,
    version: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> IterationRead:
    project = _get_project(session, name)
    iteration = _get_iteration(session, project, version)
    return iteration_read(name, iteration)


@router.post(
    "/projects/{name}/iterations",
    response_model=IterationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_iteration(
    name: str,
    payload: IterationCreate,
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
) -> IterationRead:
    project = _get_project(session, name)
    existing = session.exec(
        select(Iteration).where(
            Iteration.project_id == project.id,
            Iteration.version == payload.version,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="iteration already exists")
    try:
        snapshot_path = create_iteration_snapshot(settings, name, payload.version)
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    iteration = Iteration(
        project_id=project.id,
        version=payload.version,
        title=payload.title,
        notes=payload.notes,
        status="created",
        branch=payload.branch,
        commit_sha=payload.commit_sha,
        modules=list(payload.modules or []),
        snapshot_path=snapshot_path,
        created_at=utcnow(),
    )
    session.add(iteration)
    record_audit(
        session,
        actor=principal.username,
        action="iteration.create",
        target=f"{name}/{payload.version}",
        details={"title": payload.title, "snapshot": snapshot_path},
    )
    session.commit()
    session.refresh(iteration)
    return iteration_read(name, iteration)


@router.post(
    "/projects/{name}/iterations/{version}/restore",
    response_model=IterationRead,
)
def restore_iteration(
    name: str,
    version: str,
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
) -> IterationRead:
    project = _get_project(session, name)
    iteration = _get_iteration(session, project, version)
    try:
        restore_iteration_snapshot(settings, name, iteration.snapshot_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    iteration.status = "restored"
    session.add(iteration)
    record_audit(
        session,
        actor=principal.username,
        action="iteration.restore",
        target=f"{name}/{version}",
        details={"snapshot": iteration.snapshot_path},
    )
    session.commit()
    session.refresh(iteration)
    return iteration_read(name, iteration)


@router.get(
    "/projects/{name}/iterations/{version}/diff",
    response_model=IterationDiff,
)
def iteration_diff(
    name: str,
    version: str,
    session: SessionDep,
    principal: PrincipalDep,
    against: str | None = Query(default=None),
) -> IterationDiff:
    project = _get_project(session, name)
    target = _get_iteration(session, project, version)
    base: Iteration | None = None
    if against:
        base = _get_iteration(session, project, against)
    else:
        base = session.exec(
            select(Iteration)
            .where(
                Iteration.project_id == project.id,
                Iteration.created_at < target.created_at,
            )
            .order_by(Iteration.created_at.desc())
        ).first()
    if base is None:
        added = sorted(snapshot_manifest(target.snapshot_path))
        return IterationDiff(
            project=name,
            to_version=target.version,
            added=added,
            summary={"added": len(added), "modified": 0, "deleted": 0},
        )
    diff = diff_snapshots(Path(base.snapshot_path), Path(target.snapshot_path))
    return IterationDiff(
        project=name,
        from_version=base.version,
        to_version=target.version,
        added=diff["added"],
        modified=diff["modified"],
        deleted=diff["deleted"],
        summary={
            "added": len(diff["added"]),
            "modified": len(diff["modified"]),
            "deleted": len(diff["deleted"]),
        },
    )


@router.get(
    "/projects/{name}/iterations/{version}/backups",
    response_model=list[IterationBackupRead],
)
def list_iteration_backups(
    name: str,
    version: str,
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
) -> list[IterationBackupRead]:
    project = _get_project(session, name)
    iteration = _get_iteration(session, project, version)
    backups = session.exec(
        select(IterationBackup)
        .where(IterationBackup.iteration_id == iteration.id)
        .order_by(IterationBackup.created_at.desc())
    ).all()
    return [
        IterationBackupRead(
            project=name,
            version=version,
            stage=backup.stage,
            path=str(settings.host_path(Path(backup.path))),
            created_at=backup.created_at,
        )
        for backup in backups
    ]


@router.post(
    "/projects/{name}/iterations/{version}/backup",
    response_model=IterationBackupRead,
    status_code=status.HTTP_201_CREATED,
)
def backup_iteration(
    name: str,
    version: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
    stage: str = Query(default="dev"),
) -> IterationBackupRead:
    project = _get_project(session, name)
    iteration = _get_iteration(session, project, version)
    environment = _get_environment(session, project, stage)
    spec = build_spec(settings, project, environment)
    created_at = utcnow()
    destination = (
        settings.backups_dir
        / f"{name}-{stage}"
        / backup_filename(name, stage, created_at).replace(".sql", f"-iteration-{version}.sql")
    )
    try:
        path = provider.backup(spec, destination)
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc
    backup = IterationBackup(
        iteration_id=iteration.id,
        stage=stage,
        path=str(path),
        created_at=created_at,
    )
    session.add(backup)
    record_audit(
        session,
        actor=principal.username,
        action="iteration.backup",
        target=f"{name}/{version}",
        details={"stage": stage, "path": str(path)},
    )
    session.commit()
    session.refresh(backup)
    return IterationBackupRead(
        project=name,
        version=version,
        stage=stage,
        path=str(settings.host_path(Path(backup.path))),
        created_at=backup.created_at,
    )


@router.post(
    "/projects/{name}/iterations/{version}/restore-db",
    response_model=EnvironmentRead,
)
def restore_iteration_database(
    name: str,
    version: str,
    session: SessionDep,
    principal: PrincipalDep,
    provider: ProviderDep,
    settings: SettingsDep,
    payload: RestoreDatabaseRequest | None = None,
) -> EnvironmentRead:
    stage = payload.stage if payload is not None else "dev"
    confirm = payload.confirm if payload is not None else None
    if stage == "prod" and principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="production restores require the admin role",
        )
    if stage == "prod" and confirm != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm must exactly match the project name for production",
        )
    project = _get_project(session, name)
    iteration = _get_iteration(session, project, version)
    environment = _get_environment(session, project, stage)
    backup = session.exec(
        select(IterationBackup)
        .where(
            IterationBackup.iteration_id == iteration.id,
            IterationBackup.stage == stage,
        )
        .order_by(IterationBackup.created_at.desc())
    ).first()
    if backup is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"iteration {version} has no database backup for {stage}",
        )
    dump = Path(backup.path)
    spec = build_spec(settings, project, environment)

    environment.status = "provisioning"
    environment.updated_at = utcnow()
    session.add(environment)
    session.commit()
    session.refresh(environment)

    try:
        provider.restore_database(spec, dump)
        # The dump may predate the code: apply pending module updates and
        # require the same health gate as a normal redeploy.
        result = provider.deploy(spec, update=True)
    except ProviderError as exc:
        environment.status = "error"
        environment.updated_at = utcnow()
        session.add(environment)
        record_deploy(name, stage, "failed")
        record_audit(
            session,
            actor=principal.username,
            action="iteration.restore_db",
            target=f"{name}/{version}",
            status="failed",
            details={"stage": stage, "error": exc.message, "output": exc.details},
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message
        ) from exc

    environment.status = result.status
    environment.services = result.services
    environment.url = spec.url
    environment.updated_at = utcnow()
    session.add(environment)
    record_deploy(name, stage, "success")
    record_audit(
        session,
        actor=principal.username,
        action="iteration.restore_db",
        target=f"{name}/{version}",
        details={"stage": stage, "backup": str(dump), "status": result.status},
    )
    session.commit()
    session.refresh(environment)
    return environment_read(name, environment)
