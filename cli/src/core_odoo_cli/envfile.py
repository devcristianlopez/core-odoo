"""Locating the repository and reading ``.env`` files."""

from __future__ import annotations

import os
from pathlib import Path

SECRET_KEYS: tuple[str, ...] = (
    "CORE_API_TOKEN",
    "CORE_JWT_SECRET",
    "CORE_ADMIN_PASSWORD",
    "CORE_ODOO_MASTER_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
)

_MARKERS = (".env.example", "docker-compose.yml", "docs/CONTRACT.md")


def find_repo_root(start: Path | None = None) -> Path:
    override = os.environ.get("CORE_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in _MARKERS):
            return candidate

    # Editable install: <repo>/cli/src/core_odoo_cli/envfile.py
    package_root = Path(__file__).resolve().parents[3]
    if (package_root / "cli").is_dir() or (package_root / "docker-compose.yml").exists():
        return package_root
    return current


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def merged_environment(path: Path) -> dict[str, str]:
    """``.env`` values overlaid with process environment variables."""
    values = parse_env_file(path)
    for key, value in os.environ.items():
        if key.startswith(("CORE_", "GRAFANA_")):
            values[key] = value
    return values
