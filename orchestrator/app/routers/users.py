"""Panel user management (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..deps import AdminDep, SecurityDep, SessionDep
from ..models import User
from ..schemas import UserCreate, UserRead, UserUpdate
from ..services import record_audit

router = APIRouter(prefix="/users", tags=["users"])


def _read(user: User) -> UserRead:
    return UserRead(
        username=user.username,
        role=user.role,  # type: ignore[arg-type]
        active=user.active,
        created_at=user.created_at,
    )


def _active_admins(session: SessionDep) -> int:
    return len(
        session.exec(
            select(User).where(User.role == "admin", User.active == True)  # noqa: E712
        ).all()
    )


@router.get("", response_model=list[UserRead])
def list_users(session: SessionDep, principal: AdminDep) -> list[UserRead]:
    users = session.exec(select(User).order_by(User.username)).all()
    return [_read(user) for user in users]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    session: SessionDep,
    principal: AdminDep,
    security: SecurityDep,
) -> UserRead:
    if session.exec(select(User).where(User.username == payload.username)).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")
    user = User(
        username=payload.username,
        password_hash=security.hash_password(payload.password),
        role=payload.role,
        active=True,
    )
    session.add(user)
    record_audit(
        session,
        actor=principal.username,
        action="user.create",
        target=payload.username,
        details={"role": payload.role},
    )
    session.commit()
    session.refresh(user)
    return _read(user)


@router.patch("/{username}", response_model=UserRead)
def update_user(
    username: str,
    payload: UserUpdate,
    session: SessionDep,
    principal: AdminDep,
    security: SecurityDep,
) -> UserRead:
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if (
        user.role == "admin"
        and user.active
        and (payload.role not in (None, "admin") or payload.active is False)
        and _active_admins(session) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot demote or deactivate the last active admin",
        )
    if payload.password is not None:
        user.password_hash = security.hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.active is not None:
        user.active = payload.active
    session.add(user)
    record_audit(
        session,
        actor=principal.username,
        action="user.update",
        target=username,
        details={
            "role": payload.role,
            "active": payload.active,
            "password_changed": payload.password is not None,
        },
    )
    session.commit()
    session.refresh(user)
    return _read(user)
