"""Docker Compose implementation of the environment provider."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
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
HEALTH_PROBE_TIMEOUT_SECONDS = 15
DATABASE_PROBE_TIMEOUT_SECONDS = 30
DATABASE_READY_TIMEOUT_SECONDS = 60
DATABASE_READY_INTERVAL_SECONDS = 1.0
DATABASE_READY_PROBE_TIMEOUT_SECONDS = 10
FRONTEND_READY_TIMEOUT_SECONDS = 90
FRONTEND_READY_INTERVAL_SECONDS = 2.0

# Runs inside the gateway container. urllib is part of the standard library, so
# the probe needs no extra dependency in the gateway image.
HEALTH_PROBE_SCRIPT = """\
import json
import sys
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10) as response:
    data = json.load(response)
print(json.dumps(data))
sys.exit(0 if data.get("odoo") is True else 1)
"""


# Runs against a cloned staging database before it becomes production. It is
# additive and idempotent: no outgoing mail, no cron firing at real data, only
# the admin and the gateway service user stay active, and the public URL points
# at the new environment.
NEUTRALIZE_SQL = """\
UPDATE ir_cron SET active = false WHERE active;
UPDATE ir_mail_server SET active = false WHERE active;
UPDATE res_users SET active = false
 WHERE active AND login NOT IN ('admin', 'core_gateway');
UPDATE ir_config_parameter SET value = '{base_url}'
 WHERE key = 'web.base.url';
"""


# Transactional data cloned from staging must not reach production. The table
# list is truncated only when the module that owns it is installed; CASCADE
# removes the lines, and the document sequences restart from one.
NEUTRALIZE_DATA_SQL = """\
DO $$
DECLARE t text;
BEGIN
  -- Ordered deletes, never TRUNCATE ... CASCADE: res_company keeps a foreign
  -- key to account_move, so a cascade would wipe the company, its users and
  -- every contact with it.
  FOREACH t IN ARRAY ARRAY[
    'stock_move_line', 'stock_valuation_layer', 'stock_move', 'stock_quant',
    'account_move_line', 'account_partial_reconcile', 'account_full_reconcile',
    'account_payment', 'account_bank_statement_line', 'account_bank_statement',
    'account_move', 'sale_order_line', 'sale_order', 'purchase_order_line',
    'purchase_order'
  ] LOOP
    IF to_regclass(t) IS NOT NULL THEN
      EXECUTE format('DELETE FROM %I', t);
    END IF;
  END LOOP;
END $$;
DELETE FROM ir_sequence WHERE code LIKE 'account.move%%'
   OR code IN ('sale.order', 'purchase.order', 'stock.picking', 'stock.move');
"""


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

    def prepare(self, spec: EnvironmentSpec) -> None:
        """Write the project layout, runtime files and compose file."""
        ensure_project_layout(self._settings, spec.project, template=spec.template)
        spec.env_dir.mkdir(parents=True, exist_ok=True)
        self._write_odoo_conf(spec)
        self._write_backend_config(spec)
        self._write_runtime_files(spec)
        self._render_compose(spec)

    def deploy(self, spec: EnvironmentSpec, *, update: bool = False) -> ProviderStatus:
        self.prepare(spec)
        if update:
            self._update_modules(spec)
        self._run(spec, "up", "-d", "--build", timeout=COMPOSE_TIMEOUT_SECONDS)
        self._wait_for_health(spec)
        self._wait_for_frontend(spec)
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

    def restore_database(self, spec: EnvironmentSpec, dump: Path) -> None:
        """Replace the environment database with a plain SQL dump.

        ``backup`` writes ``pg_dump --clean --if-exists`` output, so the dump
        drops and recreates its own objects. The database is recreated first to
        drop anything the dump does not know about, and connections are
        terminated because Odoo keeps sessions open.
        """
        self._require_rendered(spec)
        if not dump.is_file():
            raise ProviderError(f"database dump not found: {dump}")
        self._ensure_database_ready(spec)
        self._run(
            spec,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "odoo",
            "-d",
            "postgres",
            "-tAc",
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{spec.db_name}' AND pid <> pg_backend_pid()",
            timeout=DATABASE_PROBE_TIMEOUT_SECONDS,
        )
        for statement in (
            f'DROP DATABASE IF EXISTS "{spec.db_name}"',
            f'CREATE DATABASE "{spec.db_name}" OWNER "odoo"',
        ):
            self._run(
                spec,
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "odoo",
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                statement,
                timeout=DATABASE_READY_TIMEOUT_SECONDS,
            )
        self._run(
            spec,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "odoo",
            "-d",
            spec.db_name,
            "-v",
            "ON_ERROR_STOP=1",
            timeout=COMPOSE_TIMEOUT_SECONDS,
            input=dump.read_text(encoding="utf-8"),
        )

    def neutralize_database(self, spec: EnvironmentSpec, base_url: str) -> None:
        """Prepare a cloned database to receive real traffic as production."""
        self._require_rendered(spec)
        self._ensure_database_ready(spec)
        sql = NEUTRALIZE_SQL.replace("{base_url}", base_url.replace("'", "''"))
        self._run(
            spec,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "odoo",
            "-d",
            spec.db_name,
            "-v",
            "ON_ERROR_STOP=1",
            timeout=DATABASE_PROBE_TIMEOUT_SECONDS,
            input=sql,
        )

    def copy_filestore(self, source: EnvironmentSpec, target: EnvironmentSpec) -> None:
        """Copy the Odoo attachments volume, renaming it to the target database.

        Odoo stores attachments in ``<data_dir>/filestore/<db_name>``, so a
        promotion that only restores the SQL dump leaves every attachment
        pointing at a missing file.
        """
        source_volume = f"{source.compose_project}_odoo_data"
        target_volume = f"{target.compose_project}_odoo_data"
        script = (
            "set -e; mkdir -p /dst/filestore; "
            f"rm -rf /dst/filestore/{target.db_name}; "
            f"if [ -d /src/filestore/{source.db_name} ]; then "
            f"cp -a /src/filestore/{source.db_name} /dst/filestore/{target.db_name}; fi"
        )
        result = self._runner(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{source_volume}:/src:ro",
                "-v",
                f"{target_volume}:/dst",
                "alpine:3",
                "sh",
                "-c",
                script,
            ],
            timeout=COMPOSE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            detail = ((result.stderr or "") + (result.stdout or "")).strip()
            raise ProviderError(
                "could not copy the Odoo filestore", details=detail[-2000:] or None
            )

    def neutralize_business_data(self, spec: EnvironmentSpec) -> None:
        """Drop documents cloned from the source: invoices, orders and stock."""
        self._require_rendered(spec)
        self._ensure_database_ready(spec)
        self._run(
            spec,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "odoo",
            "-d",
            spec.db_name,
            "-v",
            "ON_ERROR_STOP=1",
            timeout=COMPOSE_TIMEOUT_SECONDS,
            input=NEUTRALIZE_DATA_SQL,
        )

    def smoke(self, spec: EnvironmentSpec) -> tuple[bool, str]:
        """Read-only gate: services running and the gateway reports odoo=true."""
        self._require_rendered(spec)
        return self._probe_health(spec)

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
        odoo_host = f"{spec.project}-{spec.stage}-odoo.core-odoo.{spec.domain_suffix}"
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
            "odoo_host": odoo_host,
            "odoo_ui_cidrs": self._settings.core_odoo_ui_allowed_cidrs,
            "public_url": f"http://{odoo_host}",
            "admin_password": spec.admin_password,
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

    # --------------------------------------------------------------- health/update

    def _ensure_database_ready(self, spec: EnvironmentSpec) -> None:
        """Make sure the Postgres service accepts connections.

        ``docker compose stop`` leaves the database container stopped, and
        ``docker compose exec db ...`` then fails without a live server. Probing
        in that state would report "no database" and silently skip ``-u`` on an
        already initialized environment. Starting only the ``db`` service is
        idempotent and keeps the rest of the environment down until the module
        update has finished.
        """
        self._run(spec, "up", "-d", "db", timeout=DEFAULT_TIMEOUT_SECONDS)
        deadline = time.monotonic() + DATABASE_READY_TIMEOUT_SECONDS
        last_output = ""
        while True:
            ready, last_output = self._probe_database(spec)
            if ready:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(DATABASE_READY_INTERVAL_SECONDS, remaining))
        raise ProviderError(
            "database did not become ready before module update",
            details=last_output or None,
        )

    def _probe_database(self, spec: EnvironmentSpec) -> tuple[bool, str]:
        """Return readiness plus the last ``pg_isready`` output for diagnostics."""
        try:
            result = self._execute(
                spec,
                "exec",
                "-T",
                "db",
                "pg_isready",
                "-U",
                "odoo",
                "-q",
                timeout=DATABASE_READY_PROBE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False, (f"pg_isready timed out after {DATABASE_READY_PROBE_TIMEOUT_SECONDS}s")
        except FileNotFoundError as exc:
            raise ProviderError("docker CLI is not available") from exc
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        return result.returncode == 0, output

    def _database_exists(self, spec: EnvironmentSpec) -> bool:
        """Return whether the Postgres volume already holds this database.

        The environment status is not a reliable signal: a deploy that failed
        after the first boot still has a database, while a first deploy that
        never started Postgres does not. Only an actual query can tell them
        apart. This probe is diagnostic input for :meth:`_update_modules`, so
        every failure means "no database" instead of aborting the deploy.
        """
        try:
            result = self._execute(
                spec,
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "odoo",
                "-d",
                "postgres",
                "-tAc",
                f"SELECT 1 FROM pg_database WHERE datname='{spec.db_name}'",
                timeout=DATABASE_PROBE_TIMEOUT_SECONDS,
            )
        except Exception:  # a failed probe must never block a deploy
            return False
        return (result.stdout or "").strip() == "1"

    def _update_modules(self, spec: EnvironmentSpec) -> None:
        """Apply module upgrades before the environment is started again.

        Mirrors ``scripts/e2e.sh::ensure_modules``: a one-shot container with
        ``--stop-after-init`` updates the installed modules in the existing
        database. Unlike the first boot, this never installs new modules with
        demo data.

        ``-u`` only makes sense on an initialized database, so a first deploy
        (or a deploy that never created the database) silently falls back to
        the install path. The database service is therefore started and probed
        for readiness first: a stopped environment must not be mistaken for a
        fresh one.
        """
        self._ensure_database_ready(spec)
        if not self._database_exists(spec):
            return
        # Use the same discovery as the first boot: an explicit module list wins,
        # otherwise every addon under the project mount that has a manifest.
        modules = self._init_modules(spec)
        if not modules:
            return
        args = (
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "odoo",
            "odoo",
            "--stop-after-init",
            "-c",
            "/etc/odoo/odoo.conf",
            "-d",
            spec.db_name,
            "-u",
            ",".join(modules),
            "--without-demo=True",
        )
        try:
            result = self._execute(spec, *args, timeout=COMPOSE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                "odoo module update failed",
                details=f"timeout after {COMPOSE_TIMEOUT_SECONDS}s",
            ) from exc
        except FileNotFoundError as exc:
            raise ProviderError(
                "odoo module update failed",
                details="docker CLI is not available",
            ) from exc
        if result.returncode != 0:
            output = ((result.stderr or "") + (result.stdout or "")).strip()
            raise ProviderError("odoo module update failed", details=output[-4000:] or None)

    def _wait_for_frontend(self, spec: EnvironmentSpec) -> None:
        """Wait until the frontend reports healthy.

        Traefik only publishes a container's router once Docker marks it healthy,
        so returning before that leaves the URL answering 404 right after a
        deploy. Best effort: a missing container or a missing healthcheck is not
        an error.
        """
        container = f"{spec.compose_project}-frontend"
        deadline = time.monotonic() + FRONTEND_READY_TIMEOUT_SECONDS
        while True:
            try:
                result = self._runner(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{.State.Health.Status}}",
                        container,
                    ],
                    timeout=10,
                )
            except Exception:  # noqa: BLE001 - readiness must never fail a deploy
                return
            status = (result.stdout or "").strip()
            if result.returncode != 0 or status not in {"starting", "unhealthy"}:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(FRONTEND_READY_INTERVAL_SECONDS, remaining))

    def _wait_for_health(self, spec: EnvironmentSpec) -> None:
        timeout = self._settings.core_deploy_health_timeout
        interval = self._settings.core_deploy_health_interval
        deadline = time.monotonic() + timeout
        last_output = ""
        while True:
            ready, last_output = self._probe_health(spec)
            if ready:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))

        log_tail = self._logs_tail(spec, 80)
        details = "\n".join(part for part in (last_output, log_tail) if part) or None
        raise ProviderError(
            f"environment {spec.project}/{spec.stage} did not become healthy within {timeout}s",
            details=details,
        )

    def _probe_health(self, spec: EnvironmentSpec) -> tuple[bool, str]:
        """Return readiness plus the last probe/gateway output for diagnostics."""
        status = self.inspect(spec)
        if not status.services or any(
            service.get("state") != "running" for service in status.services
        ):
            return False, _describe_services(status.services)
        try:
            result = self._execute(
                spec,
                "exec",
                "-T",
                "gateway",
                "python",
                "-c",
                HEALTH_PROBE_SCRIPT,
                timeout=HEALTH_PROBE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False, f"health probe timed out after {HEALTH_PROBE_TIMEOUT_SECONDS}s"
        except FileNotFoundError:
            return False, "docker CLI is not available"
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        return result.returncode == 0, output

    def _logs_tail(self, spec: EnvironmentSpec, tail: int) -> str:
        # Diagnostics must never replace the real health failure: swallow every
        # error raised while collecting the log tail.
        try:
            return self.logs(spec, tail)
        except Exception:
            return ""

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
        input: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._runner(self._compose(spec, *args), input=input, timeout=timeout)

    def _run(
        self,
        spec: EnvironmentSpec,
        *args: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        input: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self._execute(spec, *args, input=input, timeout=timeout)
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


def _describe_services(services: list[dict[str, Any]]) -> str:
    if not services:
        return "no services reported by docker compose ps"
    return ", ".join(
        f"{service.get('name', 'unknown')}={service.get('state', 'unknown')}"
        for service in services
    )


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
