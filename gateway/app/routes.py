"""Gateway meta routes: health and login."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from . import __version__
from .schemas import HealthResponse, LoginRequest, TokenResponse

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    client = request.app.state.odoo
    version = await client.version()
    odoo_version = None
    if version:
        raw = version.get("server_version") or version.get("version")
        odoo_version = str(raw) if raw else None
    return HealthResponse(
        status="ok" if version else "degraded",
        odoo=version is not None,
        odoo_version=odoo_version,
        version=__version__,
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request) -> TokenResponse:
    config = request.app.state.config
    if config.auth.mode != "none":
        authenticated = await request.app.state.odoo.authenticate(payload.login, payload.password)
        if not authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return TokenResponse(access_token=request.app.state.tokens.issue(payload.login))
