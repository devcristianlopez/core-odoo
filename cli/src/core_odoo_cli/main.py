"""Typer entrypoint for the ``core-odoo`` CLI."""

from __future__ import annotations

import sys

import typer

from .commands import catalog as catalog_commands
from .commands import generate as generate_commands
from .commands import projects as project_commands
from .commands import system
from .errors import CliError
from .i18n import detect_language, normalize_language, set_language, t
from .options import option, refresh_help
from .output import configure, fail
from .settings import RuntimeSettings


def _language_from_argv(argv: list[str]) -> str | None:
    """Read ``--lang`` before Typer builds help strings (assessed eagerly)."""
    for index, arg in enumerate(argv):
        if arg == "--lang" and index + 1 < len(argv):
            return normalize_language(argv[index + 1])
        if arg.startswith("--lang="):
            return normalize_language(arg.split("=", 1)[1])
    return None


def _callback(
    ctx: typer.Context,
    lang: str | None = option("opt.lang", None, "--lang"),
    json_output: bool = option("opt.json", False, "--json"),
    verbose: bool = option("opt.verbose", False, "--verbose"),
) -> None:
    settings = RuntimeSettings.load()
    normalized = normalize_language(lang)
    if lang and normalized is None:
        raise CliError(t("error.lang_invalid", lang=lang), code="lang_invalid")
    chosen = normalized or normalize_language(settings.values.get("CORE_LANG")) or detect_language()
    set_language(chosen)
    configure(language=chosen, json_output=json_output, verbose=verbose)
    ctx.obj = settings


def build_app(language: str | None = None) -> typer.Typer:
    if language:
        set_language(language)
    refresh_help()
    app = typer.Typer(
        help=t("app.help"),
        no_args_is_help=True,
        add_completion=False,
        pretty_exceptions_enable=False,
    )
    app.callback()(_callback)

    app.command("init", help=t("cmd.init"))(system.init_command)
    app.command("up", help=t("cmd.up"))(system.up_command)
    app.command("down", help=t("cmd.down"))(system.down_command)
    app.command("restart", help=t("cmd.restart"))(system.restart_command)
    app.command("status", help=t("cmd.status"))(system.status_command)
    app.command("upgrade", help=t("cmd.upgrade"))(system.upgrade_command)

    project_app = typer.Typer(help=t("cmd.project"), no_args_is_help=True)
    project_app.command("create", help=t("cmd.project.create"))(project_commands.project_create)
    project_app.command("list", help=t("cmd.project.list"))(project_commands.project_list)
    project_app.command("delete", help=t("cmd.project.delete"))(project_commands.project_delete)
    app.add_typer(project_app, name="project")

    env_app = typer.Typer(help=t("cmd.env"), no_args_is_help=True)
    env_app.command("stop", help=t("cmd.env.stop"))(project_commands.env_stop)
    env_app.command("start", help=t("cmd.env.start"))(project_commands.env_start)
    env_app.command("restart", help=t("cmd.env.restart"))(project_commands.env_restart)
    env_app.command("delete", help=t("cmd.env.delete"))(project_commands.env_delete)
    app.add_typer(env_app, name="env")

    app.command("deploy", help=t("cmd.deploy"))(project_commands.deploy)
    app.command("logs", help=t("cmd.logs"))(project_commands.logs)
    app.command("backup", help=t("cmd.backup"))(project_commands.backup)

    catalog_app = typer.Typer(help=t("cmd.catalog"), no_args_is_help=True)
    catalog_app.command("models", help=t("cmd.catalog.models"))(catalog_commands.catalog_models)
    app.add_typer(catalog_app, name="catalog")

    generate_app = typer.Typer(help=t("cmd.generate"), no_args_is_help=True)
    generate_app.command("module", help=t("cmd.generate.module"))(generate_commands.module)
    generate_app.command("resource", help=t("cmd.generate.resource"))(generate_commands.resource)
    app.add_typer(generate_app, name="generate")

    return app


app = build_app()


def main() -> None:
    language = _language_from_argv(sys.argv[1:])
    if language:
        set_language(language)
    try:
        build_app()()
    except CliError as exc:
        fail(exc.message, code=exc.code)
        raise SystemExit(exc.exit_code) from None
    except KeyboardInterrupt:
        fail(t("msg.cancelled"), code="cancelled")
        raise SystemExit(130) from None


if __name__ == "__main__":  # pragma: no cover
    main()
