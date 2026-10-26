"""Drift guard for the nginx configs that front the gateway.

Every copy of the reverse-proxy config — templates, project sources and the
orchestrator fallback — must expose the same gateway routes. A divergent copy
breaks login, health checks or SDK bootstrap for one deployment only, which is
easy to miss in review.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.scaffold import _FALLBACK_NGINX

REPO_ROOT = Path(__file__).resolve().parents[2]

CONCRETE_CONFIGS = (
    "templates/agent-frontend/nginx.conf",
    "templates/frontend-starter/nginx.conf",
    "projects/smoke-test/frontend/nginx.conf",
    "projects/crm-demo/frontend/nginx.conf",
)
FALLBACK_CONFIG = "app/scaffold.py::_FALLBACK_NGINX"
CONFIG_SOURCES = (*CONCRETE_CONFIGS, FALLBACK_CONFIG)

GATEWAY_PROXY = "proxy_pass http://gateway:8000;"


def _load(source: str) -> str:
    if source == FALLBACK_CONFIG:
        return _FALLBACK_NGINX
    path = REPO_ROOT / source
    assert path.is_file(), f"{source} is missing from {REPO_ROOT}"
    return path.read_text(encoding="utf-8")


def _block(config: str, header: str) -> str:
    """Return the body of the nginx block that starts with ``header``."""
    start = config.find(header)
    assert start != -1, f"missing block: {header!r}"
    end = config.find("}", start)
    assert end != -1, f"unterminated block: {header!r}"
    return config[start:end]


@pytest.mark.parametrize("source", CONFIG_SOURCES)
def test_proxies_gateway_health_and_schema(source: str) -> None:
    config = _load(source)
    for header in ("location = /health {", "location = /openapi.json {"):
        assert header in config, f"{source} must serve the gateway at {header!r}"


@pytest.mark.parametrize("source", CONFIG_SOURCES)
def test_proxy_pass_has_no_trailing_path(source: str) -> None:
    config = _load(source)
    proxies = [
        line.strip() for line in config.splitlines() if line.strip().startswith("proxy_pass")
    ]
    assert proxies, f"{source} must proxy at least one location"
    for proxy in proxies:
        assert proxy == GATEWAY_PROXY, (
            f"{source} proxies to {proxy!r}; the gateway expects the root path"
        )


@pytest.mark.parametrize("source", CONFIG_SOURCES)
def test_serves_local_healthz(source: str) -> None:
    config = _load(source)
    assert "location = /healthz {" in config, f"{source} must answer container health checks"


@pytest.mark.parametrize("source", CONFIG_SOURCES)
def test_auth_block_forwards_client_metadata(source: str) -> None:
    config = _load(source)
    assert "location /auth/ {" in config, f"{source} has no /auth/ block"
    auth = _block(config, "location /auth/ {")
    for directive in (
        "proxy_http_version 1.1;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "proxy_set_header X-Forwarded-Proto $scheme;",
        "proxy_read_timeout 60s;",
    ):
        assert directive in auth, f"{source} /auth/ block is missing {directive!r}"
