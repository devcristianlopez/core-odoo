"""Catalog integrity and language detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core_odoo_cli import i18n
from core_odoo_cli.envfile import parse_env_file
from core_odoo_cli.i18n import (
    DEFAULT_LANGUAGE,
    LOCALES_DIR,
    SUPPORTED_LANGUAGES,
    detect_language,
    load_catalog,
    normalize_language,
    set_language,
    t,
)


def _catalog(language: str) -> dict[str, str]:
    return json.loads((LOCALES_DIR / f"{language}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_catalog_is_flat_string_map(language: str) -> None:
    catalog = _catalog(language)
    assert catalog, f"{language} catalog is empty"
    for key, value in catalog.items():
        assert isinstance(key, str) and key, "catalog keys must be non-empty strings"
        assert isinstance(value, str), f"{language}:{key} must map to a string"


def test_catalogs_share_the_same_keys() -> None:
    catalogs = {language: _catalog(language) for language in SUPPORTED_LANGUAGES}
    reference = set(catalogs[DEFAULT_LANGUAGE])
    for language, catalog in catalogs.items():
        assert set(catalog) == reference, (
            f"{language} catalog differs: missing={sorted(reference - set(catalog))} "
            f"extra={sorted(set(catalog) - reference)}"
        )


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_placeholders_are_consistent_across_catalogs(language: str) -> None:
    import string

    es = _catalog("es")
    catalog = _catalog(language)
    formatter = string.Formatter()
    for key, template in catalog.items():
        expected = {field for _, field, _, _ in formatter.parse(es[key]) if field}
        actual = {field for _, field, _, _ in formatter.parse(template) if field}
        assert actual == expected, f"{language}:{key} placeholders differ from es"


def test_normalize_language_handles_locale_variants() -> None:
    assert normalize_language("es_ES.UTF-8") == "es"
    assert normalize_language("en-US") == "en"
    assert normalize_language("ES") == "es"
    assert normalize_language("fr") is None
    assert normalize_language("") is None
    assert normalize_language(None) is None


def test_detect_language_prefers_explicit_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORE_LANG", "es")
    assert detect_language(["--lang", "en", "status"]) == "en"
    assert detect_language(["--lang=es"]) == "es"


def test_detect_language_falls_back_to_env_then_system(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CORE_ROOT", str(tmp_path))
    monkeypatch.setenv("CORE_LANG", "en")
    assert detect_language([]) == "en"
    monkeypatch.delenv("CORE_LANG")
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    for variable in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(variable, raising=False)
    assert detect_language([]) == "es"
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert detect_language([]) == DEFAULT_LANGUAGE


def test_missing_key_returns_key_and_unknown_placeholder_is_tolerated() -> None:
    set_language("es")
    assert t("does.not.exist") == "does.not.exist"
    assert t("msg.project_created", name="demo", unexpected=1).startswith("Proyecto")
    set_language("es")


def test_env_file_parser_quotes_and_exports(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nexport CORE_LANG=es\nCORE_API_TOKEN='abc def'\n"
        'CORE_ADMIN_PASSWORD="p@ss"\nIGNORED\n',
        encoding="utf-8",
    )
    values = parse_env_file(path)
    assert values == {
        "CORE_LANG": "es",
        "CORE_API_TOKEN": "abc def",
        "CORE_ADMIN_PASSWORD": "p@ss",
    }


def test_load_catalog_uses_cache() -> None:
    i18n._catalogs.clear()
    first = load_catalog("en")
    second = load_catalog("en")
    assert first is second
