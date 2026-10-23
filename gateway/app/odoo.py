"""Minimal Odoo JSON-2 client.

Contract: ``POST /json/2/<model>/<method>`` with
``Authorization: bearer <api_key>`` and ``X-Odoo-Database: <db>``.
Only the methods the gateway needs are implemented.
"""

from __future__ import annotations

from typing import Any

import httpx

_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "bad_request",
    429: "rate_limited",
}


class OdooError(Exception):
    """Normalised Odoo failure (never carries tracebacks or secrets)."""

    def __init__(self, code: str, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _error_code(status: int) -> str:
    if status >= 500:
        return "upstream_error"
    return _STATUS_CODES.get(status, "upstream_error")


def _sanitise_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            data = error.get("data")
            if isinstance(data, dict) and isinstance(data.get("message"), str):
                return data["message"]
            if isinstance(error.get("message"), str):
                return error["message"]
        for key in ("detail", "message", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().splitlines()[0][:500]
    return fallback


class OdooClient:
    def __init__(
        self,
        *,
        base_url: str,
        db: str,
        api_key: str,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._db = db
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"bearer {self._api_key}",
            "X-Odoo-Database": self._db,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout or self._timeout,
                transport=self._transport,
            ) as client:
                return await client.post(path, json=payload, headers=headers or self._headers())
        except httpx.TimeoutException as exc:
            raise OdooError("upstream_unavailable", "Odoo request timed out") from exc
        except httpx.HTTPError as exc:
            raise OdooError("upstream_unavailable", "Odoo is unreachable") from exc

    async def call(self, model: str, method: str, params: dict[str, Any]) -> Any:
        response = await self._post(f"/json/2/{model}/{method}", params)
        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code >= 400:
            raise OdooError(
                _error_code(response.status_code),
                _sanitise_message(payload, f"Odoo returned HTTP {response.status_code}"),
                status_code=response.status_code if response.status_code in _STATUS_CODES else 502,
            )
        if isinstance(payload, dict) and "error" in payload:
            raise OdooError(
                "upstream_error",
                _sanitise_message(payload, "Odoo returned an error"),
                status_code=502,
            )
        return payload

    # --------------------------------------------------------------- operations

    async def search_read(
        self,
        model: str,
        *,
        domain: list[Any],
        fields: list[str],
        limit: int,
        offset: int,
        order: str | None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "domain": domain,
            "fields": fields,
            "limit": limit,
            "offset": offset,
        }
        if order:
            params["order"] = order
        result = await self.call(model, "search_read", params)
        if not isinstance(result, list):
            raise OdooError("upstream_error", "Odoo returned an unexpected response")
        return [item for item in result if isinstance(item, dict)]

    async def read(self, model: str, *, ids: list[int], fields: list[str]) -> list[dict[str, Any]]:
        result = await self.call(model, "read", {"ids": ids, "fields": fields})
        if not isinstance(result, list):
            raise OdooError("upstream_error", "Odoo returned an unexpected response")
        return [item for item in result if isinstance(item, dict)]

    async def create(self, model: str, *, values: dict[str, Any]) -> Any:
        # Odoo 19/20 changed ``create`` to accept ``vals_list``; JSON-2 passes
        # method kwargs verbatim. Post a single-element list and normalise the
        # returned list of ids in ``_record_id``.
        result = await self.call(model, "create", {"vals_list": [values]})
        if isinstance(result, list) and len(result) == 1:
            return result[0]
        return result

    async def write(self, model: str, *, ids: list[int], values: dict[str, Any]) -> Any:
        return await self.call(model, "write", {"ids": ids, "vals": values})

    async def unlink(self, model: str, *, ids: list[int]) -> Any:
        return await self.call(model, "unlink", {"ids": ids})

    async def authenticate(self, login: str, password: str) -> bool:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"db": self._db, "login": login, "password": password},
        }
        response = await self._post(
            "/web/session/authenticate", payload, headers={"Content-Type": "application/json"}
        )
        try:
            body = response.json()
        except ValueError:
            return False
        if response.status_code >= 400 or not isinstance(body, dict):
            return False
        if "error" in body:
            return False
        result = body.get("result")
        return isinstance(result, dict) and bool(result.get("uid"))

    async def version(self) -> dict[str, Any] | None:
        payload = {"jsonrpc": "2.0", "method": "call", "params": {}}
        try:
            response = await self._post(
                "/web/webclient/version_info",
                payload,
                headers={"Content-Type": "application/json"},
                timeout=3.0,
            )
        except OdooError:
            return None
        if response.status_code >= 400:
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        result = body.get("result") if isinstance(body, dict) else None
        return result if isinstance(result, dict) else None
