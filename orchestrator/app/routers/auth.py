"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..deps import PrincipalDep, SecurityDep, SessionDep
from ..models import User
from ..schemas import (
    LoginRequest,
    MeResponse,
    PasswordChangeRequest,
    PasswordChangeResponse,
    TokenResponse,
)
from ..services import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])


def login(payload: LoginRequest, security: SecurityDep, session: SessionDep) -> TokenResponse:
    user = security.authenticate(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=security.issue_token(user.username, user.role))


def me(principal: PrincipalDep) -> MeResponse:
    return MeResponse(username=principal.username, role=principal.role)


def change_password(
    payload: PasswordChangeRequest,
    principal: PrincipalDep,
    security: SecurityDep,
    session: SessionDep,
) -> PasswordChangeResponse:
    """Let an authenticated user rotate their own panel password."""
    if principal.method != "jwt":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="the API token has no password to change",
        )
    user = session.exec(select(User).where(User.username == principal.username)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if not security.verify_password(user.password_hash, payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="current password is incorrect",
        )
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new password must differ from the current one",
        )
    user.password_hash = security.hash_password(payload.new_password)
    session.add(user)
    record_audit(
        session,
        actor=principal.username,
        action="user.password_change",
        target=principal.username,
        details={"self": True},
    )
    session.commit()
    return PasswordChangeResponse()


router.add_api_route("/login", login, methods=["POST"], response_model=TokenResponse)
router.add_api_route("/me", me, methods=["GET"], response_model=MeResponse)
router.add_api_route(
    "/password", change_password, methods=["POST"], response_model=PasswordChangeResponse
)
