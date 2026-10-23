"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..deps import PrincipalDep, SecurityDep, SessionDep
from ..schemas import LoginRequest, MeResponse, TokenResponse

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


router.add_api_route("/login", login, methods=["POST"], response_model=TokenResponse)
router.add_api_route("/me", me, methods=["GET"], response_model=MeResponse)
