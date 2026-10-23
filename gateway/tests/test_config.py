from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfigError, load_config


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "backend.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_config_expands_environment(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
app: demo
odoo:
  url: http://odoo:8069
  db: demo_db
  api_key: ${ODOO_KEY}
auth:
  mode: jwt
  jwt_secret: ${GATEWAY_SECRET}
resources:
  - name: contacts
    model: res.partner
    fields: [name, email]
    operations: [list, read]
    domain: []
    search_fields: [name]
    order: name asc
""",
    )
    config = load_config(path, env={"ODOO_KEY": "key", "GATEWAY_SECRET": "a" * 32})
    assert config.odoo.api_key == "key"
    assert config.auth.jwt_secret == "a" * 32
    assert config.odoo.url == "http://odoo:8069"
    assert config.resources[0].model == "res.partner"


def test_load_config_missing_env_var(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
app: demo
odoo:
  url: http://odoo:8069
  db: demo
  api_key: ${MISSING_KEY}
auth:
  mode: none
resources: []
""",
    )
    with pytest.raises(ConfigError, match="MISSING_KEY"):
        load_config(path, env={})


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_jwt_mode_requires_secret(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
app: demo
odoo:
  url: http://odoo:8069
  db: demo
  api_key: key
auth:
  mode: jwt
resources: []
""",
    )
    with pytest.raises(ConfigError, match="jwt_secret"):
        load_config(path)


def test_undeclared_search_field_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
app: demo
odoo:
  url: http://odoo:8069
  db: demo
  api_key: key
auth:
  mode: none
resources:
  - name: contacts
    model: res.partner
    fields: [name]
    operations: [list]
    search_fields: [email]
""",
    )
    with pytest.raises(ConfigError, match="search_fields"):
        load_config(path)


def test_unknown_operation_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
app: demo
odoo:
  url: http://odoo:8069
  db: demo
  api_key: key
auth:
  mode: none
resources:
  - name: contacts
    model: res.partner
    fields: [name]
    operations: [list, destroy]
""",
    )
    with pytest.raises(ConfigError, match="destroy"):
        load_config(path)
