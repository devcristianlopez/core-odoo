"""Thin async proxies for Prometheus and Loki (Mission Control never talks to them)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .config import Settings


class ProxyError(Exception):
    """Upstream observability service failed."""

    def __init__(self, service: str, message: str) -> None:
        super().__init__(message)
        self.service = service
        self.message = message


async def query_prometheus(
    settings: Settings,
    query: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            base_url=settings.prometheus_url,
            timeout=10.0,
            transport=transport,
        ) as client:
            response = await client.get("/api/v1/query", params={"query": query})
    except httpx.HTTPError as exc:
        raise ProxyError("prometheus", "metrics backend unreachable") from exc
    if response.status_code >= 400:
        raise ProxyError("prometheus", f"metrics backend returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProxyError("prometheus", "metrics backend returned an invalid response") from exc
    if not isinstance(payload, dict):
        raise ProxyError("prometheus", "metrics backend returned an invalid response")
    return payload


async def query_loki(
    settings: Settings,
    query: str,
    *,
    limit: int = 200,
    start: str | None = None,
    end: str | None = None,
    direction: str = "backward",
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    now_ns = int(time.time() * 1_000_000_000)
    params: dict[str, str] = {
        "query": query,
        "limit": str(limit),
        "direction": direction if direction in {"backward", "forward"} else "backward",
        "start": start or str(now_ns - 3_600_000_000_000),
        "end": end or str(now_ns),
    }
    try:
        async with httpx.AsyncClient(
            base_url=settings.loki_url,
            timeout=10.0,
            transport=transport,
        ) as client:
            response = await client.get("/loki/api/v1/query_range", params=params)
    except httpx.HTTPError as exc:
        raise ProxyError("loki", "logs backend unreachable") from exc
    if response.status_code >= 400:
        raise ProxyError("loki", f"logs backend returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProxyError("loki", "logs backend returned an invalid response") from exc
    if not isinstance(payload, dict):
        raise ProxyError("loki", "logs backend returned an invalid response")
    return payload
