from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.providers.base import EnvironmentSpec, ProviderError
from app.providers.docker import DockerProvider

from .conftest import RecordingRunner


@pytest.fixture
def provider_settings(tmp_path: Path) -> Settings:
    return Settings(
        core_data_dir=tmp_path / "data",
        core_projects_dir=tmp_path / "projects",
        core_templates_dir=tmp_path / "templates",
        core_gateway_dir=tmp_path / "gateway",
        core_domain_suffix="test.local",
    )


def test_deploy_renders_compose_and_runs_docker(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    runner = RecordingRunner(
        ps_payload=json.dumps(
            [
                {
                    "Service": "odoo",
                    "State": "running",
                    "Health": "",
                    "Status": "Up",
                }
            ]
        )
    )
    provider = DockerProvider(provider_settings, runner=runner)
    status = provider.deploy(env_spec)

    assert status.status == "running"
    assert status.services[0]["name"] == "odoo"
    assert env_spec.compose_file.is_file()
    assert env_spec.odoo_conf.is_file()
    assert env_spec.backend_config.is_file()

    rendered = yaml.safe_load(env_spec.compose_file.read_text())
    assert rendered["name"] == "core-smoke-test-dev"
    assert rendered["networks"]["edge"] == {"name": "core-edge", "external": True}
    assert rendered["networks"]["internal"]["name"] == "core-smoke-test-dev_default"
    assert rendered["volumes"]["pgdata"]["name"] == "core-smoke-test-dev_pgdata"
    assert rendered["services"]["odoo"]["image"] == "odoo:20"
    assert rendered["services"]["db"]["image"] == "postgres:16-alpine"
    assert rendered["services"]["mailpit"]["image"].startswith("axllent/mailpit")
    assert rendered["services"]["odoo"]["deploy"]["resources"]["limits"] == {
        "cpus": "2.0",
        "memory": "2g",
    }
    labels = rendered["services"]["frontend"]["labels"]
    assert labels["traefik.http.routers.smoke-test-dev-frontend.rule"] == (
        "Host(`smoke-test-dev.core-odoo.test.local`)"
    )
    assert labels["traefik.http.services.smoke-test-dev-frontend.loadbalancer.server.port"] == "80"

    up_call = runner.calls[0]
    assert up_call[:5] == [
        "docker",
        "compose",
        "-p",
        "core-smoke-test-dev",
        "-f",
    ]
    assert up_call[-3:] == ["up", "-d", "--build"]

    conf = env_spec.odoo_conf.read_text()
    assert "proxy_mode = True" in conf
    assert "workers = 0" in conf
    assert f"db_name = {env_spec.db_name}" in conf
    assert f"admin_passwd = {env_spec.master_password}" in conf

    backend = yaml.safe_load(env_spec.backend_config.read_text())
    assert backend["odoo"]["db"] == env_spec.db_name
    assert backend["auth"]["mode"] == "jwt"


def test_prod_limits_and_no_mailpit(provider_settings: Settings, env_spec: EnvironmentSpec) -> None:
    env_spec = dataclasses.replace(env_spec, stage="prod", compose_project="core-smoke-test-prod")
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec)

    rendered = yaml.safe_load(env_spec.compose_file.read_text())
    assert "mailpit" not in rendered["services"]
    assert rendered["services"]["odoo"]["deploy"]["resources"]["limits"] == {
        "cpus": "4.0",
        "memory": "4g",
    }
    assert "workers = 2" in env_spec.odoo_conf.read_text()
    assert "smtp_server" not in env_spec.odoo_conf.read_text()


def test_deploy_failure_raises_provider_error(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    runner = RecordingRunner(failing_fragment="up")
    provider = DockerProvider(provider_settings, runner=runner)
    with pytest.raises(ProviderError) as excinfo:
        provider.deploy(env_spec)
    assert excinfo.value.message == "docker compose up failed"
    assert excinfo.value.details == "boom"


def test_inspect_aggregates_states(provider_settings: Settings, env_spec: EnvironmentSpec) -> None:
    payload = json.dumps(
        [
            {"Service": "db", "State": "running", "Status": "Up"},
            {"Service": "odoo", "State": "exited", "Status": "Exited (0)"},
        ]
    )
    provider = DockerProvider(provider_settings, runner=RecordingRunner(ps_payload=payload))
    env_spec.compose_file.write_text("name: x\n", encoding="utf-8")
    status = provider.inspect(env_spec)
    assert status.status == "running"
    assert [service["name"] for service in status.services] == ["db", "odoo"]


def test_inspect_without_compose_file(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    provider = DockerProvider(provider_settings, runner=RecordingRunner())
    status = provider.inspect(env_spec)
    assert status.status == "not_deployed"
    assert status.services == []


def test_logs_passes_tail(provider_settings: Settings, env_spec: EnvironmentSpec) -> None:
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    env_spec.compose_file.write_text("name: x\n", encoding="utf-8")
    logs = provider.logs(env_spec, 42)
    assert logs == ""
    assert runner.calls[-1][-2:] == ["--tail", "42"]
    assert "logs" in runner.calls[-1]


def test_delete_uses_down_volumes(provider_settings: Settings, env_spec: EnvironmentSpec) -> None:
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    env_spec.compose_file.write_text("name: x\n", encoding="utf-8")
    provider.delete(env_spec)
    assert runner.calls[-1][-3:] == ["down", "-v", "--remove-orphans"]
    assert not env_spec.env_dir.exists()


def test_delete_without_compose_cleans_named_resources(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    provider.delete(env_spec)
    commands = [" ".join(call) for call in runner.calls]
    assert any("docker volume rm -f core-smoke-test-dev_pgdata" in cmd for cmd in commands)
    assert any("docker network rm core-smoke-test-dev_default" in cmd for cmd in commands)


def test_backup_writes_dump(
    provider_settings: Settings, env_spec: EnvironmentSpec, tmp_path: Path
) -> None:
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    env_spec.compose_file.write_text("name: x\n", encoding="utf-8")
    destination = tmp_path / "backups" / "smoke.sql"
    path = provider.backup(env_spec, destination)
    assert path == destination
    assert destination.read_text() == "-- postgres dump\n"
    assert "pg_dump" in runner.calls[-1]
    assert env_spec.db_name in runner.calls[-1]


def test_docker_info_unavailable(provider_settings: Settings) -> None:
    class BrokenRunner:
        def __call__(self, args, *, input=None, timeout=600):
            raise FileNotFoundError("docker")

    provider = DockerProvider(provider_settings, runner=BrokenRunner())
    info = provider.docker_info()
    assert info.available is False
    assert "docker" in (info.error or "")


def test_scaffold_creates_fallback_frontend(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec)
    frontend = provider_settings.core_projects_dir / "smoke-test" / "frontend"
    assert (frontend / "Dockerfile").is_file()
    assert (frontend / "nginx.conf").is_file()
