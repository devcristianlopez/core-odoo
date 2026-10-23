"""Application factory for the declarative gateway."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import BackendConfig, load_config
from .errors import (
    http_error_handler,
    odoo_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from .odoo import OdooClient, OdooError
from .resources import build_resource_router
from .routes import router as meta_router
from .security import TokenService

logger = logging.getLogger("core_odoo.gateway")


def create_app(
    config: BackendConfig | None = None,
    *,
    config_path: str | None = None,
    odoo_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    if config is None:
        path = config_path or os.environ.get("BACKEND_CONFIG", "/app/backend.yaml")
        config = load_config(path)

    client = OdooClient(
        base_url=config.odoo.url,
        db=config.odoo.db,
        api_key=config.odoo.api_key,
        transport=odoo_transport,
    )
    app = FastAPI(
        title=f"{config.app} API",
        version=__version__,
        description=(
            "Declarative Odoo BFF. Only resources declared in backend.yaml are reachable."
        ),
    )
    app.state.config = config
    app.state.odoo = client
    app.state.tokens = TokenService(config.auth)

    app.include_router(meta_router)
    app.include_router(build_resource_router(config, client))

    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(OdooError, odoo_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    return app
