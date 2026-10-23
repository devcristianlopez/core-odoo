"""Runtime paths and configuration for the CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .envfile import find_repo_root, merged_environment
from .errors import CliError
from .i18n import normalize_language, t


@dataclass(frozen=True)
class RuntimeSettings:
    repo_root: Path
    env_file: Path
    config_file: Path
    values: dict[str, str]

    @classmethod
    def load(cls) -> RuntimeSettings:
        root = find_repo_root()
        env_file = Path(os.environ.get("CORE_ENV_FILE", root / ".env")).expanduser()
        config_file = Path(os.environ.get("CORE_CONFIG_FILE", root / "core-odoo.yaml")).expanduser()
        return cls(
            repo_root=root,
            env_file=env_file,
            config_file=config_file,
            values=merged_environment(env_file),
        )

    @property
    def api_url(self) -> str:
        return self.values.get("CORE_API_URL", "http://localhost:8080").rstrip("/")

    @property
    def api_token(self) -> str:
        return self.values.get("CORE_API_TOKEN", "").strip()

    @property
    def language(self) -> str:
        return normalize_language(self.values.get("CORE_LANG")) or "es"

    def compose_files(self) -> list[Path]:
        candidates = (
            self.repo_root / "docker-compose.yml",
            self.repo_root / "docker-compose.observability.yml",
        )
        existing = [path for path in candidates if path.is_file()]
        if not existing:
            raise CliError(
                t("error.compose_files_missing", root=self.repo_root),
                code="compose_files_missing",
            )
        return existing

    def require_initialized(self) -> None:
        if not self.env_file.is_file():
            raise CliError(t("error.not_initialized"), code="not_initialized")
