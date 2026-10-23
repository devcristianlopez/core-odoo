"""Docker Compose implementation of the environment provider."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateError

from ..config import Settings
from ..scaffold import ensure_project_layout
from .base import (
    DiskInfo,
    DockerInfo,
    EnvironmentSpec,
    ProviderError,
    ProviderStatus,
)

STAGE_LIMITS: dict[str, tuple[str, str]] = {
    "dev": ("2.0", "2g"),
    "staging": ("2.0", "3g"),
    "prod": ("4.0", "4g"),
}

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
COMPOSE_TIMEOUT_SECONDS = 1800
DEFAULT_TIMEOUT_SECONDS = 600


def run_command(
    args: Sequence[str],
    *,
    input: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        input=input,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class DockerProvider:
    """Manages one Compose project per environment using the docker CLI."""

    def __init__(
        self,
        settings: Settings,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = run_command,
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._jinja = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=False,
            keep_trailing_newline=True,
        )

    # ----------------------------------------------------------------- public API

    def deploy(self, spec: EnvironmentSpec) -> ProviderStatus:
        ensure_project_layout(self._settings, spec.project, template=spec.template)
        spec.env_dir.mkdir(parents=True, exist_ok=True)
        self._write_odoo_conf(spec)
        self._write_backend_config(spec)
        self._write_runtime_files(spec)
        self._render_compose(spec)
        self._run(spec, "up", "-d", "--build", timeout=COMPOSE_TIMEOUT_SECONDS)
        return self.inspect(spec)

    def start(self, spec: EnvironmentSpec) -> ProviderStatus:
        self._require_rendered(spec)
        self._run(spec, "up", "-d", timeout=COMPOSE_TIMEOUT_SECONDS)
        return self.inspect(spec)

    def stop(self, spec: EnvironmentSpec) -> ProviderStatus:
        self._require_rendered(spec)
        self._run(spec, "stop", timeout=COMPOSE_TIMEOUT_SECONDS)
        return self.inspect(spec)

    def restart(self, spec: EnvironmentSpec) -> ProviderStatus:
        self._require_rendered(spec)
        self._run(spec, "restart", timeout=COMPOSE_TIMEOUT_SECONDS)
        return self.inspect(spec)

    def delete(self, spec: EnvironmentSpec) -> None:
        if spec.compose_file.is_file():
            self._run(
                spec,
                "down",
                "-v",
                "--remove-orphans",
                timeout=COMPOSE_TIMEOUT_SECONDS,
            )
        else:
            self._cleanup_orphans(spec)

        if spec.env_dir.exists():
            shutil.rmtree(spec.env_dir)

    def logs(self, spec: EnvironmentSpec, tail: int) -> str:
        self._require_rendered(spec)
        result = self._execute(spec, "logs", "--no-color", "--tail", str(tail))
        return (result.stdout or "") + (result.stderr or "")

    def inspect(self, spec: EnvironmentSpec) -> ProviderStatus:
        if not spec.compose_file.is_file():
            return ProviderStatus(status="not_deployed", services=[])
        result = self._execute(spec, "ps", "--format", "json")
        services = _parse_compose_ps(result.stdout)
        return ProviderStatus(status=_aggregate_state(services), services=services)

    def backup(self, spec: EnvironmentSpec, destination: Path) -> Path:
        self._require_rendered(spec)
        result = self._run(
            spec,
            "exec",
            "-T",
            "db",
            "pg_dump",
            "-U",
            "odoo",
            "--no-owner",
            "--clean",
            "--if-exists",
            spec.db_name,
            timeout=COMPOSE_TIMEOUT_SECONDS,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(result.stdout or "", encoding="utf-8")
        return destination

    def docker_info(self) -> DockerInfo:
        try:
            result = self._runner(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return DockerInfo(available=False, error=str(exc))
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()
            return DockerInfo(available=False, error=detail[0] if detail else "docker unavailable")
        return DockerInfo(available=True, version=(result.stdout or "").strip() or None)

    def disk_info(self) -> DiskInfo:
        usage = shutil.disk_usage(self._settings.core_data_dir)
        total = usage.total / 1024**3
        used = usage.used / 1024**3
        free = usage.free / 1024**3
        percent = (usage.used / usage.total * 100) if usage.total else 0.0
        return DiskInfo(
            total_gb=round(total, 2),
            used_gb=round(used, 2),
            free_gb=round(free, 2),
            percent=round(percent, 2),
        )

    # ------------------------------------------------------------------ rendering

    def _render_compose(self, spec: EnvironmentSpec) -> None:
        cpu_limit, memory_limit = STAGE_LIMITS.get(spec.stage, STAGE_LIMITS["dev"])
        router_name = f"{spec.project}-{spec.stage}-frontend"
        modules = self._init_modules(spec)
        context: dict[str, Any] = {
            "project": spec.project,
            "stage": spec.stage,
            "compose_project": spec.compose_project,
            "db_name": spec.db_name,
            "db_password": spec.db_password,
            "master_password": spec.master_password,
            "odoo_api_key": spec.odoo_api_key,
            "gateway_jwt_secret": spec.gateway_jwt_secret,
            "domain_suffix": spec.domain_suffix,
            "gateway_dir": str(spec.gateway_dir),
            "frontend_dir": str(spec.frontend_dir),
            "addons_dir": self._host_path(spec.addons_dir),
            "backend_config": self._host_path(spec.backend_config),
            "odoo_conf": self._host_path(spec.odoo_conf),
            "entrypoint": self._host_path(spec.env_dir / "entrypoint.sh"),
            "bootstrap_sh": self._host_path(spec.env_dir / "bootstrap.sh"),
            "bootstrap_py": self._host_path(spec.env_dir / "bootstrap.py"),
            "init_modules": ",".join(["base", "web", *modules]),
            "workers": 2 if spec.stage == "prod" else 0,
            "host": f"{spec.project}-{spec.stage}.core-odoo.{spec.domain_suffix}",
            "router_name": router_name,
            "cpu_limit": cpu_limit,
            "memory_limit": memory_limit,
            "smtp_enabled": spec.stage != "prod",
        }
        try:
            rendered = self._jinja.get_template("env-compose.yml.j2").render(**context)
        except TemplateError as exc:  # pragma: no cover - template is static
            raise ProviderError("failed to render environment compose file") from exc
        spec.compose_file.write_text(rendered, encoding="utf-8")

    def _write_odoo_conf(self, spec: EnvironmentSpec) -> None:
        workers = 2 if spec.stage == "prod" else 0
        lines = [
            "[options]",
            f"admin_passwd = {spec.master_password}",
            "db_host = db",
            "db_port = 5432",
            "db_user = odoo",
            f"db_password = {spec.db_password}",
            f"db_name = {spec.db_name}",
            f"dbfilter = ^{spec.db_name}$",
            "http_interface = 0.0.0.0",
            "http_port = 8069",
            "addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons",
            "data_dir = /var/lib/odoo",
            "proxy_mode = True",
            "list_db = False",
            "without_demo = True",
            f"workers = {workers}",
            "max_cron_threads = 1",
            f"email_from = odoo@{spec.project}.local",
        ]
        if spec.stage != "prod":
            lines.extend(
                [
                    "smtp_server = mailpit",
                    "smtp_port = 1025",
                    "smtp_user = False",
                    "smtp_password = False",
                    "smtp_ssl = False",
                ]
            )
        spec.odoo_conf.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_backend_config(self, spec: EnvironmentSpec) -> None:
        project_backend = spec.project_dir / "backend.yaml"
        if project_backend.is_file():
            content = project_backend.read_text(encoding="utf-8")
        else:
            content = _default_backend_yaml(spec)
        spec.backend_config.write_text(content, encoding="utf-8")

    def _host_path(self, path: Path) -> str:
        """Translate a container path to the equivalent host bind-mount path.

        The Docker daemon resolves bind-mount sources on the host, while the
        orchestrator writes files inside its own container. When the host
        directories are configured, map the container roots onto them.
        """
        resolved = path.resolve()
        mappings = (
            (self._settings.core_data_dir, self._settings.core_host_data_dir),
            (self._settings.core_projects_dir, self._settings.core_host_projects_dir),
            (self._settings.core_gateway_dir, self._settings.core_host_gateway_dir),
        )
        for container_root, host_root in mappings:
            if host_root is None:
                continue
            try:
                relative = resolved.relative_to(container_root.resolve())
            except ValueError:
                continue
            return str(host_root / relative)
        return str(resolved)

    def _init_modules(self, spec: EnvironmentSpec) -> list[str]:
        """Modules to install on the first boot.

        Explicit deploy modules win; otherwise every addon in the project mount
        that has a manifest is installed. ``base`` is always added by the caller.
        """
        if spec.modules:
            return [name.strip() for name in spec.modules if name.strip()]
        if not spec.addons_dir.is_dir():
            return []
        return sorted(
            path.name
            for path in spec.addons_dir.iterdir()
            if path.is_dir() and (path / "__manifest__.py").is_file()
        )

    def _write_runtime_files(self, spec: EnvironmentSpec) -> None:
        for name, destination, mode in (
            ("env-entrypoint.sh", spec.env_dir / "entrypoint.sh", 0o755),
            ("env-bootstrap.sh", spec.env_dir / "bootstrap.sh", 0o755),
            ("env-bootstrap.py", spec.env_dir / "bootstrap.py", 0o644),
        ):
            target = destination
            target.write_text((TEMPLATE_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
            target.chmod(mode)

    # -------------------------------------------------------------------- commands

    def _compose(self, spec: EnvironmentSpec, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "-p",
            spec.compose_project,
            "-f",
            str(spec.compose_file),
            *args,
        ]

    def _execute(
        self,
        spec: EnvironmentSpec,
        *args: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        return self._runner(self._compose(spec, *args), timeout=timeout)

    def _run(
        self,
        spec: EnvironmentSpec,
        *args: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self._execute(spec, *args, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"docker compose {args[0]} timed out",
                details=f"timeout after {timeout}s",
            ) from exc
        except FileNotFoundError as exc:
            raise ProviderError("docker CLI is not available") from exc
        if result.returncode != 0:
            detail = ((result.stderr or "") + (result.stdout or "")).strip()
            raise ProviderError(
                f"docker compose {args[0]} failed",
                details=detail[-4000:] or None,
            )
        return result

    def _require_rendered(self, spec: EnvironmentSpec) -> None:
        if not spec.compose_file.is_file():
            raise ProviderError(f"environment {spec.project}/{spec.stage} has not been deployed")

    def _cleanup_orphans(self, spec: EnvironmentSpec) -> None:
        volumes = [
            f"{spec.compose_project}_pgdata",
            f"{spec.compose_project}_odoo_data",
            f"{spec.compose_project}_filestore",
            f"{spec.compose_project}_backups",
        ]
        for volume in volumes:
            self._ignore_failure(["docker", "volume", "rm", "-f", volume])
        self._ignore_failure(["docker", "network", "rm", f"{spec.compose_project}_default"])

    def _ignore_failure(self, args: Sequence[str]) -> None:
        try:
            self._runner(args, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return


def _default_backend_yaml(spec: EnvironmentSpec) -> str:
    return f"""app: {spec.project}
odoo:
  url: http://odoo:8069
  db: {spec.db_name}
  api_key: ${{ODOO_API_KEY}}
  user: bot
auth:
  mode: jwt
  jwt_secret: ${{GATEWAY_JWT_SECRET}}
  issuer: core-odoo
resources:
  - name: contacts
    model: res.partner
    fields: [name, email, phone, city]
    operations: [list, read, create, update, delete]
    domain: []
    search_fields: [name, email]
    order: name asc
"""


def _parse_compose_ps(stdout: str | None) -> list[dict[str, Any]]:
    raw = (stdout or "").strip()
    if not raw:
        return []
    payload: Any
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = []
        for line in raw.splitlines():
            try:
                payload.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []

    services: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = item.get("Service") or item.get("Name") or "unknown"
        services.append(
            {
                "name": str(name),
                "state": str(item.get("State") or "unknown"),
                "health": str(item.get("Health") or ""),
                "status": str(item.get("Status") or ""),
            }
        )
    return services


def _aggregate_state(services: list[dict[str, Any]]) -> str:
    if not services:
        return "stopped"
    states = {service.get("state", "") for service in services}
    if "running" in states:
        return "running"
    if states & {"restarting", "created", "starting"}:
        return "starting"
    return "stopped"


def backup_filename(project: str, stage: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{project}-{stage}-{stamp}.sql"
