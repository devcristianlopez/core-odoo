"""Lazy i18n for click parameters.

Option/argument help strings are built when Typer registers a command, not when
the Python function is defined. Using these helpers keeps the catalog key and
refreshes every registered help string before a Typer app is assembled.
"""

from __future__ import annotations

from typing import Any

import typer
from typer.models import ArgumentInfo, OptionInfo

from .i18n import t

_HELP_REGISTRY: list[tuple[OptionInfo | ArgumentInfo, str]] = []


def option(key: str, *param_decls: Any, **kwargs: Any) -> OptionInfo:
    """Create a ``typer.Option`` whose help text follows the active language."""
    info = typer.Option(*param_decls, help=t(key), **kwargs)
    _HELP_REGISTRY.append((info, key))
    return info


def argument(key: str, *param_decls: Any, **kwargs: Any) -> ArgumentInfo:
    """Create a ``typer.Argument`` whose help text follows the active language."""
    info = typer.Argument(*param_decls, help=t(key), **kwargs)
    _HELP_REGISTRY.append((info, key))
    return info


def refresh_help() -> None:
    """Re-render all registered parameter help text in the active language."""
    for info, key in _HELP_REGISTRY:
        info.help = t(key)
