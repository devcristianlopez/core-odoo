"""ASGI entrypoint. Requires BACKEND_CONFIG to exist at startup."""

from __future__ import annotations

from .factory import create_app

app = create_app()
