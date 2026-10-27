"""System commands: init, up, down, restart, status, upgrade."""

from __future__ import annotations

import os
import re
import secrets
import socket
import tempfile
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from ..compose import compose_ps, detect_docker, run_compose
from ..envfile import SECRET_KEYS, parse_env_file
from ..errors import CliError
from ..i18n import get_language, normalize_language, set_language, t
from ..options import option
from ..output import emit, info, machine_output, state, success, warn
from ..settings import RuntimeSettings

console = Console()

_ENV_ORDER = (
    "CORE_LANG",
    "CORE_DOMAIN_SUFFIX",
    "CORE_API_URL",
    "CORE_ADMIN_USER",
    "CORE_ADMIN_PASSWORD",
    "CORE_API_TOKEN",
    "CORE_JWT_SECRET",
    "CORE_ODOO_MASTER_PASSWORD",
    "CORE_DATA_DIR",
    "CORE_PROJECTS_DIR",
    "CORE_TEMPLATES_DIR",
    "CORE_HOST_DATA_DIR",
    "CORE_HOST_PROJECTS_DIR",
    "CORE_HOST_GATEWAY_DIR",
    "CORE_LOG_LEVEL",
    "CORE_DOCKER_SOCKET",
    "CORE_DEPLOY_HEALTH_TIMEOUT",
    "CORE_DEPLOY_HEALTH_INTERVAL",
    "GRAFANA_ADMIN_USER",
    "GRAFANA_ADMIN_PASSWORD",
    "PROMETHEUS_RETENTION",
    "LOKI_RETENTION",
)

_ENV_COMMENTS = {
    "CORE_DEPLOY_HEALTH_TIMEOUT": (
        "# Deploy health gate: the gateway must report odoo=true within this timeout (s)."
    ),
}

_DOMAIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")


def _secret() -> str:
    return secrets.token_urlsafe(32)


def _password() -> str:
    return secrets.token_urlsafe(18)


def _validate_domain(value: str) -> str:
    candidate = value.strip().strip(".")
    if not candidate or not _DOMAIN_RE.match(candidate):
        raise CliError(t("error.invalid_domain", value=value), code="invalid_domain")
    return candidate


def detect_domain_suffix() -> str:
    """Best-effort host IP -> nip.io suffix (offline friendly)."""
    address = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
    except OSError:
        address = ""
    if not address or address.startswith("127."):
        try:
            address = socket.gethostbyname(socket.gethostname())
        except OSError:
            address = ""
    if address and not address.startswith("127."):
        return f"{address}.nip.io"
    return "localhost"


def _format_value(value: str) -> str:
    if not value or re.search(r"[\s#\"']", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".env-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _render_env(values: dict[str, str]) -> str:
    lines = [f"# {t('init.env_header')}"]
    keys = list(_ENV_ORDER) + [key for key in values if key not in _ENV_ORDER]
    for key in keys:
        if key in values:
            comment = _ENV_COMMENTS.get(key)
            if comment:
                lines.append(comment)
            lines.append(f"{key}={_format_value(values[key])}")
    return "\n".join(lines) + "\n"


def _host_path(value: str, root: Path) -> str:
    """Resolve a (possibly relative) data directory to an absolute host path."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    return str(path)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CliError(f"{path}: {exc}", code="invalid_config", exit_code=1) from exc
    return data if isinstance(data, dict) else {}


def _build_values(
    existing: dict[str, str],
    *,
    language: str,
    domain_suffix: str,
    regenerate: bool,
) -> dict[str, str]:
    values: dict[str, str] = {
        "CORE_LANG": language,
        "CORE_DOMAIN_SUFFIX": domain_suffix,
        "CORE_API_URL": existing.get("CORE_API_URL")
        or f"http://api.core-odoo.{domain_suffix}",
        "CORE_ADMIN_USER": existing.get("CORE_ADMIN_USER") or "admin",
        "CORE_ADMIN_PASSWORD": _password(),
        "CORE_API_TOKEN": _secret(),
        "CORE_JWT_SECRET": _secret(),
        "CORE_ODOO_MASTER_PASSWORD": _secret(),
        "CORE_DATA_DIR": existing.get("CORE_DATA_DIR") or "./data",
        "CORE_PROJECTS_DIR": existing.get("CORE_PROJECTS_DIR") or "./projects",
        "CORE_TEMPLATES_DIR": existing.get("CORE_TEMPLATES_DIR") or "./templates",
        "CORE_LOG_LEVEL": existing.get("CORE_LOG_LEVEL") or "INFO",
        "CORE_DOCKER_SOCKET": existing.get("CORE_DOCKER_SOCKET") or "/var/run/docker.sock",
        "CORE_DEPLOY_HEALTH_TIMEOUT": existing.get("CORE_DEPLOY_HEALTH_TIMEOUT") or "300",
        "CORE_DEPLOY_HEALTH_INTERVAL": existing.get("CORE_DEPLOY_HEALTH_INTERVAL") or "5",
        "GRAFANA_ADMIN_USER": existing.get("GRAFANA_ADMIN_USER") or "admin",
        "GRAFANA_ADMIN_PASSWORD": _password(),
        "PROMETHEUS_RETENTION": existing.get("PROMETHEUS_RETENTION") or "15d",
        "LOKI_RETENTION": existing.get("LOKI_RETENTION") or "336h",
    }
    for key in SECRET_KEYS:
        if not regenerate and existing.get(key):
            values[key] = existing[key]
    for key, value in existing.items():
        if key not in values:
            values[key] = value
    return values


def _write_config(
    settings: RuntimeSettings,
    *,
    language: str,
    domain_suffix: str,
    values: dict[str, str],
) -> Path:
    existing = _load_yaml(settings.config_file)
    config: dict[str, Any] = {
        "version": 1,
        "lang": language,
        "domain_suffix": domain_suffix,
        "admin_user": values["CORE_ADMIN_USER"],
        "api_url": values["CORE_API_URL"],
        "data_dir": values["CORE_DATA_DIR"],
        "projects_dir": values["CORE_PROJECTS_DIR"],
        "templates_dir": values["CORE_TEMPLATES_DIR"],
        "compose_files": ["docker-compose.yml", "docker-compose.observability.yml"],
    }
    for key, value in existing.items():
        config.setdefault(key, value)
    settings.config_file.parent.mkdir(parents=True, exist_ok=True)
    settings.config_file.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return settings.config_file


def init_command(
    ctx: typer.Context,
    lang: str | None = option("opt.lang", None, "--lang"),
    domain_suffix: str | None = option("opt.domain_suffix", None, "--domain-suffix"),
    non_interactive: bool = option("opt.non_interactive", False, "--non-interactive"),
    force: bool = option("opt.force", False, "--force"),
) -> None:
    """Prepare local configuration and secrets."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()

    if lang:
        normalized = normalize_language(lang)
        if normalized is None:
            raise CliError(t("error.lang_invalid", lang=lang), code="lang_invalid")
        set_language(normalized)
        state.language = normalized

    docker = detect_docker()
    existing = parse_env_file(settings.env_file)
    existing_secrets = any(existing.get(key) for key in SECRET_KEYS)

    if domain_suffix:
        suffix = _validate_domain(domain_suffix)
    elif existing.get("CORE_DOMAIN_SUFFIX"):
        suffix = _validate_domain(existing["CORE_DOMAIN_SUFFIX"])
    else:
        detected = detect_domain_suffix()
        if non_interactive or machine_output():
            suffix = detected
        else:
            answer = typer.prompt(t("prompt.domain_suffix"), default=detected)
            suffix = _validate_domain(answer)

    regenerate = force
    interactive = not non_interactive and not machine_output()
    if existing_secrets and not force and interactive:
        regenerate = Confirm.ask(t("prompt.regenerate_secrets"), default=False)
        if not regenerate:
            info(t("init.secrets_kept"))
    elif existing_secrets and not force:
        info(t("init.secrets_kept"))

    values = _build_values(
        existing, language=get_language(), domain_suffix=suffix, regenerate=regenerate
    )
    for host_key, dir_key in (
        ("CORE_HOST_DATA_DIR", "CORE_DATA_DIR"),
        ("CORE_HOST_PROJECTS_DIR", "CORE_PROJECTS_DIR"),
        ("CORE_HOST_GATEWAY_DIR", "CORE_TEMPLATES_DIR"),
    ):
        if not values.get(host_key):
            values[host_key] = _host_path(values[dir_key], settings.repo_root)
    values["CORE_HOST_GATEWAY_DIR"] = str(settings.repo_root / "gateway")
    _write_private(settings.env_file, _render_env(values))
    config_path = _write_config(
        settings, language=get_language(), domain_suffix=suffix, values=values
    )

    for key in ("CORE_DATA_DIR", "CORE_PROJECTS_DIR"):
        directory = Path(values[key]).expanduser()
        if not directory.is_absolute():
            directory = settings.repo_root / directory
        directory.mkdir(parents=True, exist_ok=True)

    if regenerate:
        info(t("init.secrets_regenerated"))
    elif not existing_secrets:
        info(t("init.secrets_generated"))

    if machine_output():
        emit(
            {
                "env_file": str(settings.env_file),
                "config_file": str(config_path),
                "lang": get_language(),
                "domain_suffix": suffix,
                "secrets_regenerated": regenerate,
                "docker": docker.version,
                "compose": docker.compose_version,
            }
        )
        return

    console.print(f"[bold]{t('init.title')}[/bold]")
    info(t("init.detected", version=docker.version, compose=docker.compose_version))
    info(t("init.env_written", path=settings.env_file))
    info(t("init.config_written", path=config_path))
    success(t("init.done"))


def up_command(ctx: typer.Context) -> None:
    """Start the control plane."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    settings.require_initialized()
    run_compose(settings, ["up", "-d", "--build"], stream=not machine_output())
    if machine_output():
        emit({"command": "up", "status": "ok"})
    else:
        success(t("msg.up_done"))


def down_command(ctx: typer.Context) -> None:
    """Stop the control plane."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    run_compose(settings, ["down"], stream=not machine_output())
    if machine_output():
        emit({"command": "down", "status": "ok"})
    else:
        success(t("msg.down_done"))


def restart_command(ctx: typer.Context) -> None:
    """Restart the control plane."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    run_compose(settings, ["down"], stream=not machine_output())
    run_compose(settings, ["up", "-d", "--build"], stream=not machine_output())
    if machine_output():
        emit({"command": "restart", "status": "ok"})
    else:
        success(t("msg.restart_done"))


def upgrade_command(ctx: typer.Context) -> None:
    """Pull images and recreate the control plane."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    settings.require_initialized()
    try:
        run_compose(settings, ["pull"], stream=not machine_output(), timeout=1800)
    except CliError as exc:
        warn(exc.message)
    run_compose(settings, ["up", "-d", "--build"], stream=not machine_output())
    if machine_output():
        emit({"command": "upgrade", "status": "ok"})
    else:
        success(t("msg.upgrade_done"))


def status_command(ctx: typer.Context) -> None:
    """Show control-plane container status."""
    settings: RuntimeSettings = ctx.obj or RuntimeSettings.load()
    containers = compose_ps(settings)

    if machine_output():
        emit(containers)
        return

    if not containers:
        info(t("status.empty"))
        return

    table = Table(title=t("status.title"))
    table.add_column(t("header.name"))
    table.add_column(t("header.service"))
    table.add_column(t("header.state"))
    table.add_column(t("header.status"))
    for container in containers:
        table.add_row(
            str(container.get("Name") or container.get("Container") or "-"),
            str(container.get("Service") or "-"),
            str(container.get("State") or "-"),
            str(container.get("Status") or "-"),
        )
    console.print(table)
