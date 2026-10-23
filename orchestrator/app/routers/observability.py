"""Observability proxies used by Mission Control."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from ..deps import PrincipalDep, SettingsDep
from ..proxies import ProxyError, query_loki, query_prometheus

router = APIRouter(tags=["observability"])


def _transport(request: Request) -> Any:
    return getattr(request.app.state, "proxy_transport", None)


@router.get("/metrics/query")
async def metrics_query(
    request: Request,
    principal: PrincipalDep,
    settings: SettingsDep,
    query: str = Query(min_length=1, max_length=4096),
) -> dict[str, Any]:
    try:
        return await query_prometheus(settings, query, transport=_transport(request))
    except ProxyError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc


@router.get("/logs/query")
async def logs_query(
    request: Request,
    principal: PrincipalDep,
    settings: SettingsDep,
    query: str = Query(min_length=1, max_length=4096),
    limit: int = Query(default=200, ge=1, le=5000),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    direction: str = Query(default="backward"),
) -> dict[str, Any]:
    try:
        return await query_loki(
            settings,
            query,
            limit=limit,
            start=start,
            end=end,
            direction=direction,
            transport=_transport(request),
        )
    except ProxyError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc
