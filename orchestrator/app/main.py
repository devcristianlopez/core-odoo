"""FastAPI application factory for the Core Odoo control plane."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from . import __version__
from .config import Settings, get_settings
from .db import init_db, make_engine
from .metrics import render as render_metrics
from .models import Environment
from .providers.base import EnvironmentProvider, ProviderError
from .providers.docker import DockerProvider
from .routers import audit, auth, health, iterations, observability, projects, status
from .routers.auth import login, me
from .schemas import MeResponse, TokenResponse
from .security import SecurityService

logger = logging.getLogger("core_odoo.orchestrator")

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    provider: EnvironmentProvider | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()

    engine = engine or make_engine(settings.database_url)
    init_db(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    app = FastAPI(
        title="Core Odoo Orchestrator",
        version=__version__,
        description="Control-plane API for Core Odoo environments.",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.security = SecurityService(settings)
    app.state.provider = provider or DockerProvider(settings)
    app.state.proxy_transport = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],
    )

    app.include_router(health.router)
    app.include_router(health.router, prefix=API_PREFIX, include_in_schema=False)
    app.include_router(projects.router, prefix=API_PREFIX)
    app.include_router(iterations.router, prefix=API_PREFIX)
    app.include_router(status.router, prefix=API_PREFIX)
    app.include_router(observability.router, prefix=API_PREFIX)
    app.include_router(audit.router, prefix=API_PREFIX)
    # Router-level auth aliases: the contract lists auth endpoints relative to
    # the base path, so expose them both as /api/v1/auth/* and /auth/*.
    app.include_router(auth.router, prefix=API_PREFIX)
    app.add_api_route(
        "/auth/login",
        login,
        methods=["POST"],
        response_model=TokenResponse,
        include_in_schema=False,
    )
    app.add_api_route(
        "/auth/me", me, methods=["GET"], response_model=MeResponse, include_in_schema=False
    )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> PlainTextResponse:
        with session_factory() as session:
            count = session.exec(select(func.count()).select_from(Environment)).one()
        return PlainTextResponse(
            render_metrics(int(count)), media_type="text/plain; version=0.0.4"
        )

    @app.exception_handler(ProviderError)
    async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
        logger.warning("provider error on %s: %s", request.url.path, exc.message)
        return JSONResponse(status_code=502, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
