"""User-facing output: Rich for humans, JSON for machines."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

from rich.console import Console

from .i18n import t

console = Console()
error_console = Console(stderr=True)


@dataclass
class CliState:
    language: str = "es"
    json_output: bool = False
    verbose: bool = False


state = CliState()


def configure(*, language: str, json_output: bool, verbose: bool) -> None:
    state.language = language
    state.json_output = json_output
    state.verbose = verbose


def machine_output() -> bool:
    return state.json_output


def emit(data: Any, *, render: Any | None = None) -> None:
    if state.json_output:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
        return
    if render is not None:
        render(data)


def info(message: str) -> None:
    if state.json_output:
        return
    console.print(message)


def success(message: str) -> None:
    if state.json_output:
        return
    console.print(f"[green]✓[/green] {message}")


def warn(message: str) -> None:
    if state.json_output:
        return
    console.print(f"[yellow]![/yellow] {message}")


def fail(message: str, *, code: str = "error") -> None:
    if state.json_output:
        envelope = {"error": {"code": code, "message": message}}
        sys.stderr.write(json.dumps(envelope, ensure_ascii=False) + "\n")
        return
    error_console.print(f"[red]✖[/red] {message}")


def verbose(message: str) -> None:
    if state.verbose and not state.json_output:
        console.print(f"[dim]{message}[/dim]", markup=True)


def logs_output(text: str) -> None:
    if not text.strip():
        info(t("msg.logs_empty"))
        return
    if state.json_output:
        emit({"logs": text})
        return
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def json_error(message: str, code: str) -> None:
    json.dump(
        {"error": {"code": code, "message": message}},
        sys.stderr,
        ensure_ascii=False,
    )
    sys.stderr.write("\n")
