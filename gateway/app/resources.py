"""Dynamic resource routes generated from backend.yaml."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from .config import BackendConfig, ResourceConfig
from .deps import require_auth
from .odoo import OdooClient, OdooError
from .schemas import CreateResponse, DeleteResponse, Record, UpdateResponse

ORDER_DIRECTIONS = {"asc", "desc"}
MAX_LIMIT = 200


def _read_fields(resource: ResourceConfig) -> list[str]:
    return list(dict.fromkeys(["id", *resource.fields]))


def _resolve_order(resource: ResourceConfig, requested: str | None) -> str | None:
    raw = requested or resource.order
    if not raw:
        return None
    parts = raw.split()
    if len(parts) > 2 or not parts:
        raise HTTPException(status_code=400, detail="invalid order expression")
    field = parts[0]
    if field not in resource.fields:
        raise HTTPException(status_code=400, detail=f"order field '{field}' is not allowed")
    direction = parts[1].lower() if len(parts) == 2 else "asc"
    if direction not in ORDER_DIRECTIONS:
        raise HTTPException(status_code=400, detail="order direction must be asc or desc")
    return f"{field} {direction}"


def _search_domain(resource: ResourceConfig, q: str | None) -> list[Any]:
    domain = list(resource.domain)
    if not q:
        return domain
    if not resource.search_fields:
        raise HTTPException(status_code=400, detail="search is not enabled for this resource")
    leaves = [(field, "ilike", f"%{q}%") for field in resource.search_fields]
    domain.extend(["|"] * (len(leaves) - 1))
    domain.extend(leaves)
    return domain


def _write_values(
    resource: ResourceConfig, payload: dict[str, Any], *, partial: bool
) -> dict[str, Any]:
    unknown = sorted(set(payload) - set(resource.fields))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"fields not allowed: {', '.join(unknown)}",
        )
    if not payload and not partial:
        raise HTTPException(status_code=400, detail="at least one field is required")
    if not payload:
        raise HTTPException(status_code=400, detail="no writable fields provided")
    return payload


def _validate_operation(resource: ResourceConfig, operation: str) -> None:
    if operation not in resource.operations:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail=f"operation '{operation}' is not enabled for this resource",
        )


def _record_id(result: Any) -> int:
    if isinstance(result, bool):
        raise OdooError("upstream_error", "Odoo returned an unexpected response")
    if isinstance(result, int):
        return result
    if isinstance(result, list) and result and isinstance(result[0], int):
        return int(result[0])
    if isinstance(result, dict) and isinstance(result.get("id"), int):
        return int(result["id"])
    raise OdooError("upstream_error", "Odoo returned an unexpected response")


def _record_domain(resource: ResourceConfig, record_id: int) -> list[Any]:
    """Constrain by-id operations to the declared resource domain."""
    return [["id", "=", record_id], *resource.domain]


async def _find_record(
    resource: ResourceConfig, client: OdooClient, record_id: int, fields: list[str]
) -> dict[str, Any] | None:
    records = await client.search_read(
        resource.model,
        domain=_record_domain(resource, record_id),
        fields=fields,
        limit=1,
        offset=0,
        order=None,
    )
    return records[0] if records else None


def _list_endpoint(resource: ResourceConfig, client: OdooClient):
    async def endpoint(
        limit: int = Query(default=20, ge=1, le=MAX_LIMIT),
        offset: int = Query(default=0, ge=0),
        order: str | None = Query(default=None, max_length=100),
        q: str | None = Query(default=None, max_length=200),
    ) -> list[Record]:
        _validate_operation(resource, "list")
        return await client.search_read(
            resource.model,
            domain=_search_domain(resource, q),
            fields=_read_fields(resource),
            limit=limit,
            offset=offset,
            order=_resolve_order(resource, order),
        )

    return endpoint


def _read_endpoint(resource: ResourceConfig, client: OdooClient):
    async def endpoint(record_id: int = Path(ge=1)) -> Record:
        _validate_operation(resource, "read")
        record = await _find_record(resource, client, record_id, _read_fields(resource))
        if record is None:
            raise HTTPException(status_code=404, detail="record not found")
        return record

    return endpoint


def _create_endpoint(resource: ResourceConfig, client: OdooClient):
    async def endpoint(payload: dict[str, Any]) -> CreateResponse:
        _validate_operation(resource, "create")
        values = _write_values(resource, payload, partial=False)
        result = await client.create(resource.model, values=values)
        return CreateResponse(id=_record_id(result))

    return endpoint


def _update_endpoint(resource: ResourceConfig, client: OdooClient):
    async def endpoint(payload: dict[str, Any], record_id: int = Path(ge=1)) -> UpdateResponse:
        _validate_operation(resource, "update")
        values = _write_values(resource, payload, partial=True)
        existing = await _find_record(resource, client, record_id, ["id"])
        if existing is None:
            raise HTTPException(status_code=404, detail="record not found")
        result = await client.write(resource.model, ids=[record_id], values=values)
        if result is False:
            raise HTTPException(status_code=400, detail="Odoo rejected the update")
        return UpdateResponse(updated=True, id=record_id)

    return endpoint


def _delete_endpoint(resource: ResourceConfig, client: OdooClient):
    async def endpoint(record_id: int = Path(ge=1)) -> DeleteResponse:
        _validate_operation(resource, "delete")
        existing = await _find_record(resource, client, record_id, ["id"])
        if existing is None:
            raise HTTPException(status_code=404, detail="record not found")
        result = await client.unlink(resource.model, ids=[record_id])
        if result is False:
            raise HTTPException(status_code=400, detail="Odoo rejected the deletion")
        return DeleteResponse(deleted=True, id=record_id)

    return endpoint


def build_resource_router(config: BackendConfig, client: OdooClient) -> APIRouter:
    router = APIRouter(tags=["resources"], dependencies=[Depends(require_auth)])
    for resource in config.resources:
        base = f"/api/{resource.name}"
        if "list" in resource.operations:
            router.add_api_route(
                base,
                _list_endpoint(resource, client),
                methods=["GET"],
                response_model=list[Record],
                name=f"list_{resource.name.replace('-', '_')}",
                summary=f"List {resource.model}",
            )
        if "read" in resource.operations:
            router.add_api_route(
                f"{base}/{{record_id}}",
                _read_endpoint(resource, client),
                methods=["GET"],
                response_model=Record,
                name=f"read_{resource.name.replace('-', '_')}",
                summary=f"Read one {resource.model}",
            )
        if "create" in resource.operations:
            router.add_api_route(
                base,
                _create_endpoint(resource, client),
                methods=["POST"],
                response_model=CreateResponse,
                status_code=201,
                name=f"create_{resource.name.replace('-', '_')}",
                summary=f"Create {resource.model}",
            )
        if "update" in resource.operations:
            router.add_api_route(
                f"{base}/{{record_id}}",
                _update_endpoint(resource, client),
                methods=["PATCH"],
                response_model=UpdateResponse,
                name=f"update_{resource.name.replace('-', '_')}",
                summary=f"Update {resource.model}",
            )
        if "delete" in resource.operations:
            router.add_api_route(
                f"{base}/{{record_id}}",
                _delete_endpoint(resource, client),
                methods=["DELETE"],
                response_model=DeleteResponse,
                name=f"delete_{resource.name.replace('-', '_')}",
                summary=f"Delete {resource.model}",
            )
    return router
