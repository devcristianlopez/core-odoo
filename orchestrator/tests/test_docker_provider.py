from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.providers import docker as docker_module
from app.providers.base import EnvironmentSpec, ProviderError
from app.providers.docker import DockerProvider

from .conftest import RecordingRunner

RUNNING_PS_PAYLOAD = json.dumps(
    [{"Service": "odoo", "State": "running", "Health": "", "Status": "Up"}]
)


class FakeClock:
    """Virtual clock so healthcheck tests never sleep for real."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ProbeRunner:
    """Fake docker CLI that reports services and a controllable probe result."""

    def __init__(
        self,
        *,
        ps_payload: str = RUNNING_PS_PAYLOAD,
        db_probe_output: str = "1\n",
        probe_returncode: int = 0,
        probe_output: str = '{"odoo": true}',
        logs_output: str = "gateway: waiting for odoo\n",
    ) -> None:
        self.calls: list[list[str]] = []
        self.ps_payload = ps_payload
        self.db_probe_output = db_probe_output
        self.probe_returncode = probe_returncode
        self.probe_output = probe_output
        self.logs_output = logs_output

    def __call__(
        self,
        args: list[str],
        *,
        input: str | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        if "ps" in args:
            return subprocess.CompletedProcess(args, 0, self.ps_payload, "")
        if "pg_isready" in args:
            return subprocess.CompletedProcess(args, 0, "", "")
        if "psql" in args:
            return subprocess.CompletedProcess(args, 0, self.db_probe_output, "")
        if "logs" in args:
            return subprocess.CompletedProcess(args, 0, self.logs_output, "")
        if "exec" in args:
            return subprocess.CompletedProcess(args, self.probe_returncode, self.probe_output, "")
        return subprocess.CompletedProcess(args, 0, "", "")


class DatabaseStartupRunner(RecordingRunner):
    """Recording fake whose ``pg_isready`` answers follow a script.

    A stopped environment is simulated by returning a non-zero exit code for
    the first answers; once the script is exhausted the database reports ready.
    """

    def __init__(self, *, pg_isready_returncodes: list[int]) -> None:
        super().__init__()
        self.pg_isready_returncodes = list(pg_isready_returncodes)

    def __call__(
        self,
        args: list[str],
        *,
        input: str | None = None,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess[str]:
        result = super().__call__(args, input=input, timeout=timeout)
        if "pg_isready" not in args:
            return result
        returncode = self.pg_isready_returncodes.pop(0) if self.pg_isready_returncodes else 0
        stderr = "" if returncode == 0 else "no response\n"
        return subprocess.CompletedProcess(args, returncode, "", stderr)


def _small_health_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"core_deploy_health_timeout": 10, "core_deploy_health_interval": 5.0}
    )


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


def test_deploy_without_update_skips_module_update(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo"])
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec, update=False)

    assert not any("--stop-after-init" in call for call in runner.calls)
    assert runner.calls[0][-3:] == ["up", "-d", "--build"]


def test_deploy_with_update_runs_module_update_before_up(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo", "crm_extra"])
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec, update=True)

    update_call = next(call for call in runner.calls if "--stop-after-init" in call)
    assert update_call[6:] == [
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
        env_spec.db_name,
        "-u",
        "crm_demo,crm_extra",
        "--without-demo=True",
    ]
    assert runner.calls.index(update_call) < len(runner.calls) - 1
    up_call = runner.calls[runner.calls.index(update_call) + 1]
    assert up_call[-3:] == ["up", "-d", "--build"]


def test_update_skips_when_no_explicit_modules_or_addons(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    # The fixture creates an (empty) addons directory, matching a project with
    # no installable modules.
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec, update=True)

    assert not any("-u" in call for call in runner.calls)
    assert not any("--stop-after-init" in call for call in runner.calls)


def test_update_skips_when_database_does_not_exist(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    # A deploy that never initialised the database must take the install path,
    # even when the caller asked for an update.
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo"])
    runner = RecordingRunner(db_probe_output="")
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec, update=True)

    commands = [" ".join(call) for call in runner.calls]
    assert not any("--stop-after-init" in command for command in commands)
    assert not any(" -u " in command for command in commands)
    # The db service is started first for the readiness probe; the install path
    # is still a full build-up of every service.
    assert any(call[-3:] == ["up", "-d", "--build"] for call in runner.calls)


def test_update_runs_when_database_exists(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo"])
    runner = RecordingRunner(db_probe_output="1\n")
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec, update=True)

    update_call = next(call for call in runner.calls if "--stop-after-init" in call)
    assert update_call[update_call.index("-u") + 1] == "crm_demo"


def test_database_probe_queries_the_db_service(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo"])
    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec, update=True)

    probe_call = next(call for call in runner.calls if "psql" in call)
    assert probe_call[6:] == [
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "odoo",
        "-d",
        "postgres",
        "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname='{env_spec.db_name}'",
    ]


def test_database_probe_failure_never_blocks_deploy(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo"])

    def runner(args: list[str], *, input: str | None = None, timeout: int = 600):
        if "psql" in args:
            raise OSError("docker socket unavailable")
        return RecordingRunner()(args, input=input, timeout=timeout)

    provider = DockerProvider(provider_settings, runner=runner)
    status = provider.deploy(env_spec, update=True)

    assert status.status == "running"


def test_update_starts_database_and_waits_for_readiness(
    provider_settings: Settings, env_spec: EnvironmentSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stopped environment must still run ``-u``: bring the db service up and
    # wait for pg_isready instead of mistaking the stopped server for a fresh one.
    clock = FakeClock()
    monkeypatch.setattr(docker_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(docker_module.time, "sleep", clock.sleep)
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo"])
    runner = DatabaseStartupRunner(pg_isready_returncodes=[1, 1, 0])
    provider = DockerProvider(provider_settings, runner=runner)

    provider.deploy(env_spec, update=True)

    calls = runner.calls
    db_up_index = next(index for index, call in enumerate(calls) if call[-3:] == ["up", "-d", "db"])
    probe_indexes = [index for index, call in enumerate(calls) if "pg_isready" in call]
    psql_index = next(index for index, call in enumerate(calls) if "psql" in call)
    update_index = next(index for index, call in enumerate(calls) if "--stop-after-init" in call)

    assert [calls[index][calls[index].index("exec") :] for index in probe_indexes] == [
        ["exec", "-T", "db", "pg_isready", "-U", "odoo", "-q"]
    ] * 3
    assert db_up_index < probe_indexes[0]
    assert max(probe_indexes) < psql_index < update_index
    assert calls[update_index][calls[update_index].index("-u") + 1] == "crm_demo"
    assert clock.now == 2.0


def test_update_fails_when_database_never_becomes_ready(
    provider_settings: Settings, env_spec: EnvironmentSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(docker_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(docker_module.time, "sleep", clock.sleep)
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo"])
    runner = DatabaseStartupRunner(pg_isready_returncodes=[1] * 120)
    provider = DockerProvider(provider_settings, runner=runner)

    with pytest.raises(ProviderError) as excinfo:
        provider.deploy(env_spec, update=True)

    assert excinfo.value.message == "database did not become ready before module update"
    assert "no response" in (excinfo.value.details or "")
    # Only the db service is started, and the update/install path never runs.
    assert [call[-3:] for call in runner.calls].count(["up", "-d", "db"]) == 1
    assert not any("--stop-after-init" in call for call in runner.calls)
    assert not any("-u" in call for call in runner.calls)
    assert not any(call[-3:] == ["up", "-d", "--build"] for call in runner.calls)
    assert clock.now >= docker_module.DATABASE_READY_TIMEOUT_SECONDS - 1


def test_update_discovers_addons_when_spec_modules_is_empty(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    module_dir = env_spec.addons_dir / "upgrade_check"
    module_dir.mkdir()
    (module_dir / "__manifest__.py").write_text("{'name': 'Upgrade Check'}\n", encoding="utf-8")
    assert env_spec.modules == []

    runner = RecordingRunner()
    provider = DockerProvider(provider_settings, runner=runner)
    provider.deploy(env_spec, update=True)

    update_call = next(call for call in runner.calls if "--stop-after-init" in call)
    assert update_call[update_call.index("-u") + 1] == "upgrade_check"


def test_module_update_failure_is_wrapped(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    env_spec = dataclasses.replace(env_spec, modules=["crm_demo"])
    provider = DockerProvider(provider_settings, runner=RecordingRunner(failing_fragment="-u"))
    with pytest.raises(ProviderError) as excinfo:
        provider.deploy(env_spec, update=True)
    assert excinfo.value.message == "odoo module update failed"
    assert excinfo.value.details == "boom"


def test_healthcheck_returns_when_probe_succeeds(
    provider_settings: Settings, env_spec: EnvironmentSpec
) -> None:
    runner = ProbeRunner(probe_returncode=0)
    provider = DockerProvider(provider_settings, runner=runner)
    status = provider.deploy(env_spec)

    assert status.status == "running"
    probe_calls = [call for call in runner.calls if "exec" in call]
    assert len(probe_calls) == 1
    assert probe_calls[0][probe_calls[0].index("exec") :] == [
        "exec",
        "-T",
        "gateway",
        "python",
        "-c",
        docker_module.HEALTH_PROBE_SCRIPT,
    ]


def test_healthcheck_times_out_with_log_tail(
    provider_settings: Settings, env_spec: EnvironmentSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(docker_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(docker_module.time, "sleep", clock.sleep)
    runner = ProbeRunner(probe_returncode=1, probe_output="connection refused")
    provider = DockerProvider(_small_health_settings(provider_settings), runner=runner)

    with pytest.raises(ProviderError) as excinfo:
        provider.deploy(env_spec)

    assert excinfo.value.message == "environment smoke-test/dev did not become healthy within 10s"
    assert "connection refused" in (excinfo.value.details or "")
    assert "gateway: waiting for odoo" in (excinfo.value.details or "")
    assert any("logs" in call for call in runner.calls)


def test_healthcheck_treats_exited_services_as_not_ready(
    provider_settings: Settings, env_spec: EnvironmentSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(docker_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(docker_module.time, "sleep", clock.sleep)
    exited = json.dumps(
        [{"Service": "odoo", "State": "exited", "Health": "", "Status": "Exited (1)"}]
    )
    runner = ProbeRunner(ps_payload=exited, probe_returncode=0)
    provider = DockerProvider(_small_health_settings(provider_settings), runner=runner)

    with pytest.raises(ProviderError) as excinfo:
        provider.deploy(env_spec)

    assert "odoo=exited" in (excinfo.value.details or "")
    # The gateway probe must not run while a service is not running.
    assert not any("exec" in call for call in runner.calls)
