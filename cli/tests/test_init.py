"""``core-odoo init`` must bootstrap configuration without leaking/overwriting secrets."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from core_odoo_cli.commands import system
from core_odoo_cli.compose import DockerInfo
from core_odoo_cli.envfile import SECRET_KEYS, parse_env_file
from core_odoo_cli.main import app

runner = CliRunner()

DOCKER = DockerInfo(version="Docker version 29.7.2", compose_version="Docker Compose v5.5.1")


@pytest.fixture()
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "core-odoo"
    root.mkdir()
    monkeypatch.setenv("CORE_ROOT", str(root))
    monkeypatch.delenv("CORE_ENV_FILE", raising=False)
    monkeypatch.delenv("CORE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("CORE_API_TOKEN", raising=False)
    monkeypatch.setattr(system, "detect_docker", lambda: DOCKER)
    monkeypatch.setattr(system, "detect_domain_suffix", lambda: "10.0.0.2.nip.io")
    return root


def _run_init(*extra: str) -> Result:
    return runner.invoke(app, ["--lang", "en", "init", "--non-interactive", *extra])


def test_init_writes_env_and_config(project_root: Path) -> None:
    result = _run_init()

    assert result.exit_code == 0, result.output
    env_file = project_root / ".env"
    config_file = project_root / "core-odoo.yaml"
    assert env_file.is_file()
    assert config_file.is_file()

    values = parse_env_file(env_file)
    assert values["CORE_LANG"] == "en"
    assert values["CORE_DOMAIN_SUFFIX"] == "10.0.0.2.nip.io"
    assert values["CORE_ADMIN_USER"] == "admin"
    for key in SECRET_KEYS:
        assert values[key], f"{key} must be generated"

    # The deploy health gate is configured out of the box; without it the
    # orchestrator falls back to its own defaults inside Docker.
    assert values["CORE_DEPLOY_HEALTH_TIMEOUT"] == "300"
    assert values["CORE_DEPLOY_HEALTH_INTERVAL"] == "5"

    text = config_file.read_text(encoding="utf-8")
    assert "version: 1" in text
    assert "domain_suffix: 10.0.0.2.nip.io" in text
    assert "compose_files:" in text

    mode = stat.S_IMODE(env_file.stat().st_mode)
    assert mode == 0o600

    assert (project_root / "data").is_dir()
    assert (project_root / "projects").is_dir()


def test_init_honours_domain_suffix_flag(project_root: Path) -> None:
    result = _run_init("--domain-suffix", "example.test")
    assert result.exit_code == 0, result.output
    assert parse_env_file(project_root / ".env")["CORE_DOMAIN_SUFFIX"] == "example.test"


def test_init_rejects_invalid_domain_suffix(project_root: Path) -> None:
    result = _run_init("--domain-suffix", "not a domain!")
    assert result.exit_code != 0
    assert not (project_root / ".env").exists()


def test_init_preserves_secrets_without_force(project_root: Path) -> None:
    assert _run_init().exit_code == 0
    first = parse_env_file(project_root / ".env")

    assert _run_init().exit_code == 0
    second = parse_env_file(project_root / ".env")

    for key in SECRET_KEYS:
        assert second[key] == first[key], f"{key} must be preserved"


def test_init_force_regenerates_secrets(project_root: Path) -> None:
    assert _run_init().exit_code == 0
    first = parse_env_file(project_root / ".env")

    assert _run_init("--force").exit_code == 0
    second = parse_env_file(project_root / ".env")

    for key in SECRET_KEYS:
        assert second[key] != first[key], f"{key} must be regenerated"


def test_init_non_secret_overrides_survive_reruns(project_root: Path) -> None:
    assert _run_init().exit_code == 0
    env_file = project_root / ".env"
    text = env_file.read_text(encoding="utf-8")
    env_file.write_text(text + "CUSTOM_FLAG=keepme\n", encoding="utf-8")

    assert _run_init().exit_code == 0
    assert parse_env_file(env_file)["CUSTOM_FLAG"] == "keepme"


def test_init_json_without_non_interactive_never_prompts(project_root: Path) -> None:
    assert _run_init().exit_code == 0
    first = parse_env_file(project_root / ".env")

    result = runner.invoke(app, ["--json", "--lang", "en", "init"])
    assert result.exit_code == 0, result.output
    assert "\x1b" not in result.output
    payload = json.loads(result.output)
    assert payload["secrets_regenerated"] is False
    assert parse_env_file(project_root / ".env")["CORE_API_TOKEN"] == first["CORE_API_TOKEN"]


def test_init_json_output_is_machine_readable(project_root: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--json",
            "--lang",
            "en",
            "init",
            "--non-interactive",
            "--domain-suffix",
            "example.test",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "\x1b" not in result.output
    payload = json.loads(result.output)
    assert payload["lang"] == "en"
    assert payload["domain_suffix"] == "example.test"
    assert payload["secrets_regenerated"] is False
    assert payload["env_file"].endswith(".env")
    assert payload["config_file"].endswith("core-odoo.yaml")
