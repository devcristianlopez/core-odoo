"""HTTP client for the orchestrator API."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from .errors import CliError
from .i18n import t
from .settings import RuntimeSettings

DEFAULT_TIMEOUT = 30
DEPLOY_TIMEOUT = 1800
BACKUP_TIMEOUT = 600
LOGS_TIMEOUT = 60


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = (response.text or "").strip().replace("\n", " ")
        return text[:300] or response.reason_phrase
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:500]
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail[:500]
        if isinstance(detail, list):
            parts = []
            for item in detail:
                if isinstance(item, dict):
                    location = ".".join(str(part) for part in item.get("loc", ()))
                    message = item.get("msg", "invalid value")
                    parts.append(f"{location}: {message}" if location else str(message))
                else:
                    parts.append(str(item))
            if parts:
                return "; ".join(parts)[:500]
    return response.reason_phrase


class OrchestratorClient:
    def __init__(self, settings: RuntimeSettings) -> None:
        self._settings = settings
        self._validate()

    def _validate(self) -> None:
        parsed = urlparse(self._settings.api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise CliError(t("error.api_url", url=self._settings.api_url), code="api_url")
        if not self._settings.api_token:
            raise CliError(t("error.api_token_missing"), code="api_token_missing")

    @property
    def _api_base(self) -> str:
        base = self._settings.api_url.rstrip("/")
        if base.endswith("/api/v1"):
            return base
        return f"{base}/api/v1"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {self._settings.api_token}",
            "Accept": "application/json",
        }
        try:
            with httpx.Client(
                base_url=self._api_base,
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = client.request(method, path, json=json, params=params)
        except httpx.TimeoutException as exc:
            raise CliError(
                t("error.api_timeout", url=self._settings.api_url), code="api_timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise CliError(
                t("error.api_unreachable", url=self._settings.api_url),
                code="api_unreachable",
            ) from exc

        if response.status_code >= 400:
            raise CliError(
                t(
                    "error.http",
                    status=response.status_code,
                    detail=_detail(response),
                ),
                code="http_error",
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise CliError(
                t("error.unknown", detail="invalid JSON from orchestrator"),
                code="invalid_response",
            ) from exc

    # ------------------------------------------------------------------ projects

    def create_project(self, name: str, template: str) -> dict[str, Any]:
        return self._request("POST", "/projects", json={"name": name, "template": template})

    def list_projects(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/projects")
        return payload if isinstance(payload, list) else []

    def delete_project(self, name: str, confirm: str, purge: bool = False) -> dict[str, Any]:
        params = {"confirm": confirm}
        if purge:
            params["purge"] = "true"
        return self._request("DELETE", f"/projects/{name}", params=params)

    # ---------------------------------------------------------- deploy requests

    def list_deploy_requests(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {"status": status} if status else None
        payload = self._request("GET", "/deploy-requests", params=params)
        return payload if isinstance(payload, list) else []

    def create_deploy_request(self, name: str, iteration: str, reason: str = "") -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{name}/deploy-requests",
            json={"iteration": iteration, "reason": reason},
        )

    def approve_deploy_request(self, request_id: int) -> dict[str, Any]:
        return self._request("POST", f"/deploy-requests/{request_id}/approve")

    def reject_deploy_request(self, request_id: int) -> dict[str, Any]:
        return self._request("POST", f"/deploy-requests/{request_id}/reject")

    # ---------------------------------------------------------------- iterations

    def list_iterations(self, name: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/projects/{name}/iterations")
        return payload if isinstance(payload, list) else []

    def create_iteration(
        self,
        name: str,
        *,
        version: str,
        title: str,
        notes: str = "",
        branch: str | None = None,
        commit_sha: str | None = None,
        modules: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"version": version, "title": title, "notes": notes}
        if branch:
            body["branch"] = branch
        if commit_sha:
            body["commit_sha"] = commit_sha
        if modules:
            body["modules"] = modules
        return self._request("POST", f"/projects/{name}/iterations", json=body)

    def restore_iteration(self, name: str, version: str) -> dict[str, Any]:
        return self._request("POST", f"/projects/{name}/iterations/{version}/restore")

    def iteration_diff(self, name: str, version: str, against: str | None = None) -> dict[str, Any]:
        params = {"against": against} if against else None
        return self._request("GET", f"/projects/{name}/iterations/{version}/diff", params=params)

    def backup_iteration(self, name: str, version: str, stage: str = "dev") -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{name}/iterations/{version}/backup",
            params={"stage": stage},
        )

    def iteration_backups(self, name: str, version: str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/projects/{name}/iterations/{version}/backups")
        return payload if isinstance(payload, list) else []

    # -------------------------------------------------------------- environments

    def deploy(
        self,
        name: str,
        stage: str,
        branch: str | None = None,
        iteration: str | None = None,
        confirm: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"stage": stage}
        if branch:
            body["branch"] = branch
        if iteration:
            body["iteration"] = iteration
        if confirm:
            body["confirm"] = confirm
        return self._request(
            "POST",
            f"/projects/{name}/deploy",
            json=body,
            timeout=DEPLOY_TIMEOUT,
        )

    def environment_action(self, name: str, stage: str, action: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{name}/environments/{stage}/{action}",
            timeout=DEPLOY_TIMEOUT,
        )

    def delete_environment(self, name: str, stage: str, confirm: str) -> dict[str, Any]:
        return self._request(
            "DELETE",
            f"/projects/{name}/environments/{stage}",
            params={"confirm": confirm},
            timeout=DEPLOY_TIMEOUT,
        )

    def logs(self, name: str, stage: str, tail: int) -> str:
        payload = self._request(
            "GET",
            f"/projects/{name}/environments/{stage}/logs",
            params={"tail": tail},
            timeout=LOGS_TIMEOUT,
        )
        if isinstance(payload, dict) and isinstance(payload.get("logs"), str):
            return payload["logs"]
        return ""

    def backup(self, name: str, stage: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{name}/environments/{stage}/backup",
            timeout=BACKUP_TIMEOUT,
        )
