"""Every documented command must be reachable through the Typer app."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from core_odoo_cli.main import app, build_app

runner = CliRunner()

COMMAND_PATHS: tuple[tuple[str, ...], ...] = (
    ("init",),
    ("up",),
    ("down",),
    ("restart",),
    ("status",),
    ("upgrade",),
    ("deploy",),
    ("logs",),
    ("backup",),
    ("project", "create"),
    ("project", "list"),
    ("project", "delete"),
    ("env", "stop"),
    ("env", "start"),
    ("env", "restart"),
    ("env", "delete"),
)


def test_main_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    for command in (
        "init",
        "up",
        "down",
        "restart",
        "status",
        "upgrade",
        "deploy",
        "logs",
        "backup",
        "project",
        "env",
    ):
        assert command in result.output


def test_project_and_env_groups_list_subcommands() -> None:
    project = runner.invoke(app, ["project", "--help"])
    assert project.exit_code == 0
    for subcommand in ("create", "list", "delete"):
        assert subcommand in project.output

    env = runner.invoke(app, ["env", "--help"])
    assert env.exit_code == 0
    for subcommand in ("stop", "start", "restart", "delete"):
        assert subcommand in env.output


@pytest.mark.parametrize("path", COMMAND_PATHS)
def test_command_help_succeeds(path: tuple[str, ...]) -> None:
    result = runner.invoke(app, [*path, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


SPANISH_HELP_PROBES = (
    "Idioma",
    "Nombre del proyecto",
    "Entorno",
    "Rama de git",
    "Número de líneas",
    "Sufijo de dominio",
    "Plantilla",
    "No hacer preguntas",
    "Sobrescribe",
    "No preguntar",
    "Gestiona",
    "Prepara",
    "Levanta",
    "Detiene",
    "Reinicia",
    "Muestra",
    "Actualiza",
    "Lista",
)


@pytest.mark.parametrize("path", COMMAND_PATHS)
def test_spanish_help_is_rendered(path: tuple[str, ...]) -> None:
    result = runner.invoke(build_app("es"), [*path, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output
    assert any(probe in result.output for probe in SPANISH_HELP_PROBES), result.output


def test_global_language_flag_before_command() -> None:
    result = runner.invoke(build_app("es"), ["--lang", "es", "--help"])
    assert result.exit_code == 0
    assert "Idioma" in result.output


def test_global_flags_are_exposed() -> None:
    result = runner.invoke(app, ["--help"])
    assert "--lang" in result.output
    assert "--json" in result.output
    assert "--verbose" in result.output


def test_documented_stage_choices() -> None:
    result = runner.invoke(app, ["deploy", "--help"])
    assert result.exit_code == 0
    for stage in ("dev", "staging", "prod"):
        assert stage in result.output
