"""MCP server exposing Core Odoo agent tools over stdio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .api import OrchestratorClient
from .checker import check_project as run_check
from .commands.catalog import read_catalog
from .commands.projects import perform_rollback
from .frontend_generator import generate_frontend as run_frontend
from .generator import generate_module as run_module
from .generator import generate_resource as run_resource
from .project_paths import project_dir
from .sdk import generate_sdk as run_sdk
from .settings import RuntimeSettings


def _settings() -> RuntimeSettings:
    return RuntimeSettings.load()


def _project(name: str) -> Path:
    return project_dir(_settings(), name)


def _fail(exc: Exception) -> dict[str, Any]:
    return {"ok": False, "error": str(exc)}


def build_server() -> FastMCP:
    server = FastMCP(
        "core-odoo",
        instructions=(
            "Core Odoo is an Odoo 20 software factory. Inspect the catalogue "
            "before modelling, use generators instead of writing auth/CRUD "
            "boilerplate, check before deploying, and never expose Odoo to the "
            "browser."
        ),
    )

    @server.tool()
    def project_list() -> dict[str, Any]:
        """List projects registered in the control plane."""
        try:
            return {"ok": True, "projects": OrchestratorClient(_settings()).list_projects()}
        except Exception as exc:  # noqa: BLE001 - returned to the agent
            return _fail(exc)

    @server.tool()
    def list_deploy_requests(status: str | None = None) -> dict[str, Any]:
        """List production deployment requests."""
        try:
            return {
                "ok": True,
                "requests": OrchestratorClient(_settings()).list_deploy_requests(status),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def request_deploy(project: str, iteration: str, reason: str = "") -> dict[str, Any]:
        """Request admin approval for a production deploy."""
        try:
            return {
                "ok": True,
                "request": OrchestratorClient(_settings()).create_deploy_request(
                    project, iteration, reason
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def approve_deploy(request_id: int) -> dict[str, Any]:
        """Approve and execute a production deployment request (admin)."""
        try:
            return {
                "ok": True,
                "request": OrchestratorClient(_settings()).approve_deploy_request(request_id),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def reject_deploy(request_id: int) -> dict[str, Any]:
        """Reject a production deployment request (admin)."""
        try:
            return {
                "ok": True,
                "request": OrchestratorClient(_settings()).reject_deploy_request(request_id),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def list_iterations(project: str) -> dict[str, Any]:
        """List versioned iterations for a project."""
        try:
            return {
                "ok": True,
                "iterations": OrchestratorClient(_settings()).list_iterations(project),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def create_iteration(
        project: str,
        version: str,
        title: str,
        notes: str = "",
        branch: str | None = None,
        commit_sha: str | None = None,
        modules: str = "",
    ) -> dict[str, Any]:
        """Snapshot the current project source as a versioned iteration."""
        try:
            module_list = [item.strip() for item in modules.split(",") if item.strip()]
            return {
                "ok": True,
                "iteration": OrchestratorClient(_settings()).create_iteration(
                    project,
                    version=version,
                    title=title,
                    notes=notes,
                    branch=branch,
                    commit_sha=commit_sha,
                    modules=module_list or None,
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def restore_iteration(project: str, version: str) -> dict[str, Any]:
        """Restore project source code from an iteration snapshot."""
        try:
            return {
                "ok": True,
                "iteration": OrchestratorClient(_settings()).restore_iteration(project, version),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def iteration_diff(
        project: str,
        version: str,
        against: str | None = None,
    ) -> dict[str, Any]:
        """Compare an iteration against the previous one or an explicit base."""
        try:
            return {
                "ok": True,
                "diff": OrchestratorClient(_settings()).iteration_diff(project, version, against),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def backup_iteration(
        project: str,
        version: str,
        stage: str = "dev",
    ) -> dict[str, Any]:
        """Create a database dump linked to an iteration."""
        try:
            return {
                "ok": True,
                "backup": OrchestratorClient(_settings()).backup_iteration(project, version, stage),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def catalog_models(
        project: str,
        stage: str = "dev",
        model: str | None = None,
    ) -> dict[str, Any]:
        """Read installed Odoo models, fields and access rules from an environment."""
        try:
            payload = read_catalog(project, stage, model)
            return {"ok": True, **payload}
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def generate_module(
        project: str,
        module: str,
        model: str = "record",
        fields: str = "name:char",
        title: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Generate an Odoo 20 module (model, ir.access, views, tests)."""
        try:
            module_title = title or module.replace("_", " ").title()
            result = run_module(
                _project(project),
                module,
                module_title,
                model,
                fields,
                force=force,
            )
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def generate_resource(
        project: str,
        resource: str,
        model: str,
        fields: str,
        operations: str = "list,read,create,update,delete",
        search_fields: str = "name",
        order: str | None = None,
    ) -> dict[str, Any]:
        """Add or replace a resource in the project's backend.yaml."""
        try:
            result = run_resource(
                _project(project),
                resource,
                model,
                fields,
                operations=operations,
                search_fields=search_fields,
                order=order,
            )
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def generate_sdk(
        project: str,
        stage: str = "dev",
        output: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Generate a typed TypeScript SDK from backend.yaml."""
        try:
            target = Path(output).expanduser() if output else None
            if target is not None and not target.is_absolute():
                target = _project(project) / target
            result = run_sdk(
                _project(project),
                project,
                stage=stage,
                output=target,
                force=force,
            )
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def generate_frontend(
        project: str,
        stage: str = "dev",
        template: str = "templates/agent-frontend",
        force: bool = False,
    ) -> dict[str, Any]:
        """Generate a login + generic CRUD frontend from backend.yaml."""
        try:
            settings = _settings()
            template_path = Path(template).expanduser()
            if not template_path.is_absolute():
                template_path = settings.repo_root / template_path
            result = run_frontend(
                _project(project),
                project,
                template_dir=template_path,
                stage=stage,
                force=force,
            )
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def check_project(
        project: str,
        stage: str = "dev",
        catalog: bool = False,
        frontend: bool = False,
    ) -> dict[str, Any]:
        """Validate backend.yaml, Odoo modules, ACL, syntax and optionally the frontend."""
        try:
            return run_check(
                _project(project),
                project,
                stage=stage,
                catalog=catalog,
                frontend=frontend,
            )
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def deploy_project(
        project: str,
        stage: str = "dev",
        branch: str | None = None,
        iteration: str | None = None,
        confirm: str | None = None,
    ) -> dict[str, Any]:
        """Deploy a project environment through the orchestrator."""
        try:
            return {
                "ok": True,
                "environment": OrchestratorClient(_settings()).deploy(
                    project, stage, branch, iteration, confirm
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def rollback_environment(
        project: str,
        stage: str = "dev",
        confirm: str | None = None,
    ) -> dict[str, Any]:
        """Roll an environment back to its last successful iteration."""
        try:
            return {
                "ok": True,
                "environment": perform_rollback(
                    OrchestratorClient(_settings()), project, stage, confirm
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    @server.tool()
    def environment_logs(project: str, stage: str = "dev", tail: int = 200) -> dict[str, Any]:
        """Read recent logs from a deployed environment."""
        try:
            return {
                "ok": True,
                "logs": OrchestratorClient(_settings()).logs(project, stage, tail),
            }
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)

    return server
