"""Versioned project iterations and source snapshots."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..deps import PrincipalDep, SessionDep, SettingsDep
from ..models import Iteration, Project, utcnow
from ..schemas import IterationCreate, IterationRead
from ..services import (
    create_iteration_snapshot,
    iteration_read,
    record_audit,
    restore_iteration_snapshot,
)

router = APIRouter(tags=["iterations"])


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
