from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.base import (
    DiskInfo,
    DockerInfo,
    EnvironmentSpec,
    ProviderStatus,
)

API_TOKEN = "test-api-token"


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, EnvironmentSpec]] = []
        self.specs: list[EnvironmentSpec] = []
        self.deploy_updates: list[bool] = []
        self.restored_dumps: list[Path] = []
        self.neutralized: list[str] = []
        self.smoke_ok = True
        self.deploy_status = ProviderStatus(
            status="running",
            services=[{"name": "odoo", "state": "running", "health": "", "status": "Up"}],
        )
        self.fail_with: Exception | None = None
        self.fail_on: str | None = None
        self.fail_times: int | None = None

    def _record(self, action: str, spec: EnvironmentSpec) -> None:
        self.calls.append((action, spec))
        self.specs.append(spec)
        if (
            self.fail_with is not None
            and (self.fail_on is None or self.fail_on == action)
            and (self.fail_times is None or self.fail_times > 0)
        ):
            if self.fail_times is not None:
                self.fail_times -= 1
            raise self.fail_with

    def prepare(self, spec: EnvironmentSpec) -> None:
        self._record("prepare", spec)

    def deploy(self, spec: EnvironmentSpec, *, update: bool = False) -> ProviderStatus:
        self.deploy_updates.append(update)
        self._record("deploy", spec)
        return self.deploy_status

    def start(self, spec: EnvironmentSpec) -> ProviderStatus:
        self._record("start", spec)
        return self.deploy_status

    def stop(self, spec: EnvironmentSpec) -> ProviderStatus:
        self._record("stop", spec)
        return ProviderStatus(status="stopped", services=[])

    def restart(self, spec: EnvironmentSpec) -> ProviderStatus:
        self._record("restart", spec)
        return self.deploy_status

    def delete(self, spec: EnvironmentSpec) -> None:
        self._record("delete", spec)

    def logs(self, spec: EnvironmentSpec, tail: int) -> str:
        self._record("logs", spec)
        return f"log tail {tail}"

    def inspect(self, spec: EnvironmentSpec) -> ProviderStatus:
        return self.deploy_status

    def backup(self, spec: EnvironmentSpec, destination: Path) -> Path:
        self._record("backup", spec)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("-- dump\n", encoding="utf-8")
        return destination

    def restore_database(self, spec: EnvironmentSpec, dump: Path) -> None:
        self.restored_dumps.append(dump)
        self._record("restore_database", spec)

    def neutralize_database(self, spec: EnvironmentSpec, base_url: str) -> None:
        self.neutralized.append(base_url)
        self._record("neutralize_database", spec)

    def smoke(self, spec: EnvironmentSpec) -> tuple[bool, str]:
        self._record("smoke", spec)
        return (self.smoke_ok, "gateway ok" if self.smoke_ok else "gateway odoo=false")

    def docker_info(self) -> DockerInfo:
        return DockerInfo(available=True, version="test")

    def disk_info(self) -> DiskInfo:
        return DiskInfo(total_gb=100.0, used_gb=25.0, free_gb=75.0, percent=25.0)


@dataclass
class AppHarness:
    client: TestClient
    provider: FakeProvider
    settings: Settings
    app: Any = field(repr=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        core_api_token=API_TOKEN,
        core_jwt_secret="test-jwt-secret",
        core_admin_user="admin",
        core_admin_password="admin-password",
        core_data_dir=tmp_path / "data",
        core_projects_dir=tmp_path / "projects",
        core_templates_dir=tmp_path / "templates",
        core_domain_suffix="test.local",
        core_gateway_dir=tmp_path / "gateway",
    )


@pytest.fixture
def harness(settings: Settings) -> Iterator[AppHarness]:
    provider = FakeProvider()
    app = create_app(settings, provider=provider)
    with TestClient(app) as client:
        yield AppHarness(client=client, provider=provider, settings=settings, app=app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_TOKEN}"}


@pytest.fixture
def create_project(
    harness: AppHarness, auth_headers: dict[str, str]
) -> Callable[[str], dict[str, Any]]:
    def _create(name: str = "smoke-test", template: str = "empty") -> dict[str, Any]:
        response = harness.client.post(
            "/api/v1/projects",
            json={"name": name, "template": template},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture
def env_spec(tmp_path: Path) -> EnvironmentSpec:
    project_dir = tmp_path / "projects" / "smoke-test"
    addons = project_dir / "odoo" / "addons"
    addons.mkdir(parents=True)
    (project_dir / "frontend").mkdir(parents=True)
    env_dir = tmp_path / "data" / "envs" / "smoke-test-dev"
    env_dir.mkdir(parents=True)
    return EnvironmentSpec(
        project="smoke-test",
        stage="dev",
        compose_project="core-smoke-test-dev",
        env_dir=env_dir,
        project_dir=project_dir,
        addons_dir=addons,
        gateway_dir=tmp_path / "gateway",
        backend_config=env_dir / "backend.yaml",
        db_name="smoke_test_dev",
        db_password="db-password",
        master_password="master-password",
        odoo_api_key="api-key",
        gateway_jwt_secret="jwt-secret",
        domain_suffix="test.local",
    )


HEALTHY_PS_PAYLOAD = json.dumps(
    [{"Service": "odoo", "State": "running", "Health": "", "Status": "Up"}]
)


class RecordingRunner:
    def __init__(
        self,
        *,
        ps_payload: str = HEALTHY_PS_PAYLOAD,
        db_probe_output: str = "1\n",
        failing_fragment: str | None = None,
    ) -> None:
        self.calls: list[list[str]] = []
        self.inputs: list[str | None] = []
        self.ps_payload = ps_payload
        self.db_probe_output = db_probe_output
        self.failing_fragment = failing_fragment

    def __call__(
        self,
        args: list[str],
        *,
        input: str | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        self.inputs.append(input)
        if self.failing_fragment and self.failing_fragment in args:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        if "ps" in args:
            return subprocess.CompletedProcess(args, 0, self.ps_payload, "")
        if "pg_isready" in args:
            return subprocess.CompletedProcess(args, 0, "", "")
        if "psql" in args:
            return subprocess.CompletedProcess(args, 0, self.db_probe_output, "")
        if "pg_dump" in args:
            return subprocess.CompletedProcess(args, 0, "-- postgres dump\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")
