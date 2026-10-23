"""Docker Compose delegation for the control plane."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from .errors import CliError
from .i18n import t
from .output import verbose
from .settings import RuntimeSettings

COMPOSE_PROJECT = "core-odoo"
LONG_TIMEOUT = 1800


@dataclass(frozen=True)
class DockerInfo:
    version: str
    compose_version: str


def _run(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliError(t("error.docker_missing"), code="docker_missing") from exc
    except subprocess.TimeoutExpired as exc:
        raise CliError(t("error.docker_daemon"), code="docker_daemon") from exc


def detect_docker() -> DockerInfo:
    binary = shutil.which("docker")
    if binary is None:
        raise CliError(t("error.docker_missing"), code="docker_missing")

    version = _run([binary, "--version"])
    if version.returncode != 0:
        raise CliError(t("error.docker_missing"), code="docker_missing")

    compose = _run([binary, "compose", "version"])
    if compose.returncode != 0:
        raise CliError(t("error.compose_missing"), code="compose_missing")

    daemon = _run([binary, "info", "--format", "{{.ServerVersion}}"], timeout=20)
    if daemon.returncode != 0:
        raise CliError(t("error.docker_daemon"), code="docker_daemon")

    return DockerInfo(
        version=(version.stdout or version.stderr or "docker").strip(),
        compose_version=(compose.stdout or compose.stderr or "compose").strip(),
    )


def compose_command(settings: RuntimeSettings, args: list[str]) -> list[str]:
    files = settings.compose_files()
    command = ["docker", "compose", "-p", COMPOSE_PROJECT]
    for path in files:
        command.extend(["-f", str(path)])
    command.extend(args)
    return command


def run_compose(
    settings: RuntimeSettings,
    args: list[str],
    *,
    stream: bool = False,
    timeout: int = LONG_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    command = compose_command(settings, args)
    verbose("$ " + " ".join(shlex.quote(part) for part in command))
    try:
        if stream:
            result = subprocess.run(command, cwd=settings.repo_root, check=False)
        else:
            result = subprocess.run(
                command,
                cwd=settings.repo_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
    except FileNotFoundError as exc:
        raise CliError(t("error.docker_missing"), code="docker_missing") from exc
    except subprocess.TimeoutExpired as exc:
        raise CliError(t("error.command_failed", code="timeout"), code="timeout") from exc

    if result.returncode != 0:
        detail = ""
        if not stream:
            output = (result.stderr or "") + (result.stdout or "")
            lines = [line for line in output.strip().splitlines() if line.strip()]
            if lines:
                detail = f": {lines[-1][:500]}"
        raise CliError(
            t("error.command_failed", code=result.returncode) + detail,
            code="command_failed",
            exit_code=result.returncode or 1,
        )
    return result


def compose_ps(settings: RuntimeSettings) -> list[dict[str, Any]]:
    result = run_compose(settings, ["ps", "--format", "json"], stream=False, timeout=60)
    raw = (result.stdout or "").strip()
    if not raw:
        return []
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
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
