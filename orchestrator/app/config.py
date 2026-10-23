"""Runtime configuration for the orchestrator.

All values come from the control-plane ``.env``. Paths are resolved eagerly so
the rest of the application never has to reason about the current directory.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repository_root() -> Path:
    """Locate the repository root used to resolve the gateway build context.

    ``CORE_REPO_ROOT`` wins when the control plane is containerised; otherwise
    fall back to the checkout that contains this package (development), and
    finally to the conventional container path.
    """
    override = os.environ.get("CORE_REPO_ROOT")
    if override:
        return Path(override).expanduser()
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "gateway").is_dir():
        return candidate
    return Path("/app")


def _default_gateway_dir() -> Path:
    return _repository_root() / "gateway"


class Settings(BaseSettings):
    """Environment-backed settings (prefix-free, names match ``.env`` keys)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    core_api_token: str = Field(default="dev-api-token")
    core_jwt_secret: str = Field(default="dev-jwt-secret")
    core_admin_user: str = Field(default="admin")
    core_admin_password: str = Field(default="admin")
    core_jwt_issuer: str = Field(default="core-odoo")
    core_jwt_ttl_minutes: int = Field(default=720, ge=1)

    core_data_dir: Path = Field(default=Path("./data"))
    core_projects_dir: Path = Field(default=Path("./projects"))
    core_templates_dir: Path = Field(default=Path("./templates"))

    # Host-side equivalents of the bind-mounted directories. The orchestrator
    # renders Compose files for the host daemon, so bind-mount sources must be
    # host paths even though the files are read/written inside the container.
    core_host_data_dir: Path | None = Field(default=None)
    core_host_projects_dir: Path | None = Field(default=None)
    core_host_gateway_dir: Path | None = Field(default=None)

    core_domain_suffix: str = Field(default="localhost")
    core_log_level: str = Field(default="INFO")
    core_cors_origins: str = Field(default="*")

    # Optional overrides. Defaults match the contract repository layout.
    core_repo_root: Path = Field(default_factory=_repository_root)
    core_gateway_dir: Path = Field(default_factory=_default_gateway_dir)
    prometheus_url: str = Field(default="http://prometheus:9090")
    loki_url: str = Field(default="http://loki:3100")
    gateway_healthcheck_timeout: float = Field(default=2.0, gt=0)

    @field_validator(
        "core_data_dir",
        "core_projects_dir",
        "core_templates_dir",
        "core_repo_root",
        "core_gateway_dir",
    )
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator(
        "core_host_data_dir",
        "core_host_projects_dir",
        "core_host_gateway_dir",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if value is None or value == "" or value == ".":
            return None
        return value

    @field_validator(
        "core_host_data_dir",
        "core_host_projects_dir",
        "core_host_gateway_dir",
    )
    @classmethod
    def _absolute_optional(cls, value: Path | None) -> Path | None:
        return None if value is None else value.expanduser().resolve()

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.core_data_dir / 'core.db'}"

    @property
    def envs_dir(self) -> Path:
        return self.core_data_dir / "envs"

    @property
    def iterations_dir(self) -> Path:
        return self.core_data_dir / "iterations"

    @property
    def backups_dir(self) -> Path:
        return self.core_data_dir / "backups"

    @property
    def cors_origins(self) -> list[str]:
        raw = self.core_cors_origins.strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def ensure_dirs(self) -> None:
        for directory in (
            self.core_data_dir,
            self.core_projects_dir,
            self.envs_dir,
            self.backups_dir,
            self.iterations_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
