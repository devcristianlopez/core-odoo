"""Every documented command must be reachable through the Typer app."""

from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from core_odoo_cli.main import app, build_app

runner = CliRunner()

ANSI_SGR_SEQUENCE = re.compile(r"\x1b\[[0-9;]*m")

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


def strip_ansi(text: str) -> str:
    """Remove ANSI SGR sequences so assertions see contiguous unstyled text.

    Rich splits styled spans whenever colour is enabled (``--lang`` is rendered
    as ``-`` + ``-lang``), and CI forces colour, so the raw output is not stable.
    """
    return ANSI_SGR_SEQUENCE.sub("", text)


def test_main_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    output = strip_ansi(result.output)
    assert result.exit_code == 0, output
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
        assert command in output


def test_project_and_env_groups_list_subcommands() -> None:
    project = runner.invoke(app, ["project", "--help"])
    project_output = strip_ansi(project.output)
    assert project.exit_code == 0, project_output
    for subcommand in ("create", "list", "delete"):
        assert subcommand in project_output

    env = runner.invoke(app, ["env", "--help"])
    env_output = strip_ansi(env.output)
    assert env.exit_code == 0, env_output
    for subcommand in ("stop", "start", "restart", "delete"):
        assert subcommand in env_output


@pytest.mark.parametrize("path", COMMAND_PATHS)
def test_command_help_succeeds(path: tuple[str, ...]) -> None:
    result = runner.invoke(app, [*path, "--help"])
    output = strip_ansi(result.output)
    assert result.exit_code == 0, output
    assert "Usage:" in output


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
    output = strip_ansi(result.output)
    assert result.exit_code == 0, output
    assert "Usage:" in output
    assert any(probe in output for probe in SPANISH_HELP_PROBES), output


def test_global_language_flag_before_command() -> None:
    result = runner.invoke(build_app("es"), ["--lang", "es", "--help"])
    output = strip_ansi(result.output)
    assert result.exit_code == 0, output
    assert "Idioma" in output


def test_global_flags_are_exposed() -> None:
    result = runner.invoke(app, ["--help"])
    output = strip_ansi(result.output)
    assert "--lang" in output
    assert "--json" in output
    assert "--verbose" in output


def test_documented_stage_choices() -> None:
    result = runner.invoke(app, ["deploy", "--help"])
    output = strip_ansi(result.output)
    assert result.exit_code == 0, output
    for stage in ("dev", "staging", "prod"):
        assert stage in output
