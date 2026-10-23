"""Production deployment approvals."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from ..deps import AdminDep, PrincipalDep, ProviderDep, SessionDep, SettingsDep
from ..models import DeploymentRequest, Project, utcnow
from ..schemas import DeploymentRequestRead, DeployRequest
from ..services import record_audit
from .projects import deploy

router = APIRouter(tags=["approvals"])


def _read(session: SessionDep, request: DeploymentRequest) -> DeploymentRequestRead:
    project = session.get(Project, request.project_id)
    return DeploymentRequestRead(
        id=request.id or 0,
        project=project.name if project else "?",
        stage=request.stage,
        iteration=request.iteration,
        reason=request.reason,
        status=request.status,
        requested_by=request.requested_by,
        decided_by=request.decided_by,
        created_at=request.created_at,
        decided_at=request.decided_at,
        deployed_at=request.deployed_at,
    )


@router.get("/deploy-requests", response_model=list[DeploymentRequestRead])
def list_deployment_requests(
    session: SessionDep,
    principal: PrincipalDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[DeploymentRequestRead]:
    query = select(DeploymentRequest)
    if principal.role != "admin":
        query = query.where(DeploymentRequest.requested_by == principal.username)
    if status_filter:
        query = query.where(DeploymentRequest.status == status_filter)
    requests = session.exec(query.order_by(DeploymentRequest.created_at.desc())).all()
    return [_read(session, request) for request in requests]


@router.post(
    "/deploy-requests/{request_id}/approve",
    response_model=DeploymentRequestRead,
)
def approve_deployment_request(
    request_id: int,
    session: SessionDep,
    principal: AdminDep,
    provider: ProviderDep,
    settings: SettingsDep,
) -> DeploymentRequestRead:
    request = session.get(DeploymentRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request not found")
    if request.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="request is not pending")
    project = session.get(Project, request.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    request.decided_by = principal.username
    request.decided_at = utcnow()
    request.status = "approved"
    session.add(request)
    session.commit()
    try:
        deploy(
            project.name,
            DeployRequest(
                stage="prod",
                iteration=request.iteration,
                confirm=project.name,
            ),
            session,
            principal,
            provider,
            settings,
        )
    except HTTPException as exc:
        request.status = "failed"
        session.add(request)
        record_audit(
            session,
            actor=principal.username,
            action="deploy_request.failed",
            target=f"{project.name}/{request.iteration}",
            status="failed",
            details={"error": exc.detail},
        )
        session.commit()
        raise
    request.status = "deployed"
    request.deployed_at = utcnow()
    session.add(request)
    record_audit(
        session,
        actor=principal.username,
        action="deploy_request.approve",
        target=f"{project.name}/{request.iteration}",
        details={"request_id": request.id, "requested_by": request.requested_by},
    )
    session.commit()
    session.refresh(request)
    return _read(session, request)


@router.post(
    "/deploy-requests/{request_id}/reject",
    response_model=DeploymentRequestRead,
)
def reject_deployment_request(
    request_id: int,
    session: SessionDep,
    principal: AdminDep,
) -> DeploymentRequestRead:
    request = session.get(DeploymentRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request not found")
    if request.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="request is not pending")
    request.status = "rejected"
    request.decided_by = principal.username
    request.decided_at = utcnow()
    session.add(request)
    record_audit(
        session,
        actor=principal.username,
        action="deploy_request.reject",
        target=f"{request.project_id}/{request.iteration}",
    )
    session.commit()
    session.refresh(request)
    return _read(session, request)
