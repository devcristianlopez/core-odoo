"""Provider abstraction: the orchestrator only speaks to this interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class ProviderError(Exception):
    """A provider operation failed (Docker, filesystem, ...)."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


@dataclass(frozen=True)
class EnvironmentSpec:
    project: str
    stage: str
    compose_project: str
    env_dir: Path
    project_dir: Path
    addons_dir: Path
    gateway_dir: Path
    backend_config: Path
    db_name: str
    db_password: str
    master_password: str
    odoo_api_key: str
    gateway_jwt_secret: str
    domain_suffix: str
    template: str = "empty"
    branch: str | None = None
    modules: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"http://{self.project}-{self.stage}.core-odoo.{self.domain_suffix}"

    @property
    def compose_file(self) -> Path:
        return self.env_dir / "docker-compose.yml"

    @property
    def odoo_conf(self) -> Path:
        return self.env_dir / "odoo.conf"

    @property
    def frontend_dir(self) -> Path:
        return self.project_dir / "frontend"


@dataclass
class ProviderStatus:
    status: str
    services: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DockerInfo:
    available: bool
    version: str | None = None
    error: str | None = None


@dataclass
class DiskInfo:
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


@runtime_checkable
class EnvironmentProvider(Protocol):
    def prepare(self, spec: EnvironmentSpec) -> None: ...

    def deploy(self, spec: EnvironmentSpec, *, update: bool = False) -> ProviderStatus: ...

    def start(self, spec: EnvironmentSpec) -> ProviderStatus: ...

    def stop(self, spec: EnvironmentSpec) -> ProviderStatus: ...

    def restart(self, spec: EnvironmentSpec) -> ProviderStatus: ...

    def delete(self, spec: EnvironmentSpec) -> None: ...

    def logs(self, spec: EnvironmentSpec, tail: int) -> str: ...

    def inspect(self, spec: EnvironmentSpec) -> ProviderStatus: ...

    def backup(self, spec: EnvironmentSpec, destination: Path) -> Path: ...

    def restore_database(self, spec: EnvironmentSpec, dump: Path) -> None: ...

    def neutralize_database(self, spec: EnvironmentSpec, base_url: str) -> None: ...

    def smoke(self, spec: EnvironmentSpec) -> tuple[bool, str]: ...

    def docker_info(self) -> DockerInfo: ...

    def disk_info(self) -> DiskInfo: ...
