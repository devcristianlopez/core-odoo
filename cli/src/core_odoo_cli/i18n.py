"""Tiny JSON-catalog i18n layer (Spanish by default, English supported)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .envfile import find_repo_root, parse_env_file

DEFAULT_LANGUAGE = "es"
SUPPORTED_LANGUAGES: tuple[str, ...] = ("es", "en")
LOCALES_DIR = Path(__file__).resolve().parent / "locales"

_catalogs: dict[str, dict[str, str]] = {}
_language = DEFAULT_LANGUAGE


def normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    head = value.strip().lower().replace("-", "_").split("_")[0].split(".")[0]
    return head if head in SUPPORTED_LANGUAGES else None


def load_catalog(language: str) -> dict[str, str]:
    if language not in _catalogs:
        path = LOCALES_DIR / f"{language}.json"
        _catalogs[language] = json.loads(path.read_text(encoding="utf-8"))
    return _catalogs[language]


def set_language(language: str) -> None:
    global _language
    normalized = normalize_language(language) or DEFAULT_LANGUAGE
    load_catalog(normalized)
    _language = normalized


def get_language() -> str:
    return _language


def t(key: str, **kwargs: object) -> str:
    catalog = load_catalog(_language)
    template = catalog.get(key)
    if template is None:
        template = load_catalog("en").get(key, key)
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def _flag_value(args: list[str], flag: str) -> str | None:
    for index, arg in enumerate(args):
        if arg == flag and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith(f"{flag}="):
            return arg.split("=", 1)[1]
    return None


def detect_language(argv: list[str] | None = None) -> str:
    args = list(sys.argv[1:] if argv is None else argv)

    explicit = _flag_value(args, "--lang")
    if explicit:
        return normalize_language(explicit) or DEFAULT_LANGUAGE

    env_language = os.environ.get("CORE_LANG")
    if env_language:
        normalized = normalize_language(env_language)
        if normalized:
            return normalized

    try:
        file_values = parse_env_file(find_repo_root() / ".env")
    except OSError:
        file_values = {}
    normalized = normalize_language(file_values.get("CORE_LANG"))
    if normalized:
        return normalized

    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        normalized = normalize_language(os.environ.get(variable))
        if normalized:
            return normalized
    return DEFAULT_LANGUAGE


set_language(detect_language())
