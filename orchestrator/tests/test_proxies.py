from __future__ import annotations

import httpx

from .conftest import AppHarness


def test_metrics_proxy_passthrough(harness: AppHarness, auth_headers: dict[str, str]) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = request.url.params.get("query", "")
        return httpx.Response(
            200, json={"status": "success", "data": {"resultType": "vector", "result": []}}
        )

    harness.app.state.proxy_transport = httpx.MockTransport(handler)
    response = harness.client.get(
        "/api/v1/metrics/query", params={"query": "up"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert seen == {"path": "/api/v1/query", "query": "up"}
    assert response.json()["status"] == "success"


def test_logs_proxy_passthrough(harness: AppHarness, auth_headers: dict[str, str]) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["limit"] = request.url.params.get("limit", "")
        return httpx.Response(200, json={"status": "success", "data": {"result": []}})

    harness.app.state.proxy_transport = httpx.MockTransport(handler)
    response = harness.client.get(
        "/api/v1/logs/query",
        params={"query": '{container="core-smoke-test-dev-odoo"}', "limit": 25},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert seen["path"] == "/loki/api/v1/query_range"
    assert seen["limit"] == "25"


def test_metrics_proxy_upstream_error(harness: AppHarness, auth_headers: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "bad"})

    harness.app.state.proxy_transport = httpx.MockTransport(handler)
    response = harness.client.get(
        "/api/v1/metrics/query", params={"query": "up"}, headers=auth_headers
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "metrics backend returned HTTP 500"


def test_metrics_query_requires_query_param(
    harness: AppHarness, auth_headers: dict[str, str]
) -> None:
    response = harness.client.get("/api/v1/metrics/query", headers=auth_headers)
    assert response.status_code == 422
