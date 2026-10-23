"""Audit trail endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlmodel import select

from ..deps import PrincipalDep, SessionDep
from ..models import AuditEvent
from ..schemas import AuditEventRead

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=list[AuditEventRead])
def audit(
    session: SessionDep,
    principal: PrincipalDep,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AuditEventRead]:
    events = session.exec(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    ).all()
    return [
        AuditEventRead(
            id=event.id or 0,
            actor=event.actor,
            action=event.action,
            target=event.target,
            status=event.status,
            details=event.details,
            created_at=event.created_at,
        )
        for event in events
    ]
