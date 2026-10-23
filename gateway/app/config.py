"""backend.yaml loading and validation.

The file is the single source of truth for what the gateway exposes. Only
models, fields, operations and domains declared here are reachable.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

Operation = Literal["list", "read", "create", "update", "delete"]
VALID_OPERATIONS: frozenset[str] = frozenset({"list", "read", "create", "update", "delete"})

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_RESOURCE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


class ConfigError(Exception):
    """backend.yaml is missing or invalid."""


class OdooConfig(BaseModel):
    url: str = Field(min_length=1)
    db: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    user: str = Field(default="bot", min_length=1)

    @field_validator("url")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        return value.rstrip("/")


class AuthConfig(BaseModel):
    mode: Literal["jwt", "none"] = "jwt"
    jwt_secret: str = Field(default="", min_length=0)
    issuer: str = "core-odoo"
    jwt_ttl_minutes: int = Field(default=720, ge=1)


class ResourceConfig(BaseModel):
    name: str
    model: str
    fields: list[str]
    operations: list[Operation]
    domain: list[Any] = Field(default_factory=list)
    search_fields: list[str] = Field(default_factory=list)
    order: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _RESOURCE_NAME.match(value):
            raise ValueError("resource name must be lowercase alphanumeric/dash/underscore")
        return value

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", value):
            raise ValueError("model must look like 'res.partner'")
        return value

    @field_validator("fields")
    @classmethod
    def _validate_fields(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("resource must declare at least one field")
        for field in value:
            if not _FIELD_NAME.match(field):
                raise ValueError(f"invalid field name: {field}")
        return list(dict.fromkeys(value))

    @field_validator("operations")
    @classmethod
    def _validate_operations(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("resource must declare at least one operation")
        unknown = set(value) - VALID_OPERATIONS
        if unknown:
            raise ValueError(f"unknown operations: {', '.join(sorted(unknown))}")
        return list(dict.fromkeys(value))

    @field_validator("search_fields")
    @classmethod
    def _validate_search_fields(cls, value: list[str]) -> list[str]:
        for field in value:
            if not _FIELD_NAME.match(field):
                raise ValueError(f"invalid search field: {field}")
        return list(dict.fromkeys(value))

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, value: list[Any]) -> list[Any]:
        if not isinstance(value, list):
            raise ValueError("domain must be a list")
        return value

    @model_validator(mode="after")
    def _cross_validate(self) -> ResourceConfig:
        declared = set(self.fields)
        missing_search = set(self.search_fields) - declared
        if missing_search:
            raise ValueError(
                f"search_fields not declared in fields: {', '.join(sorted(missing_search))}"
            )
        if self.order:
            order_field = self.order.split()[0]
            if order_field not in declared:
                raise ValueError(f"order field '{order_field}' is not declared in fields")
        return self


class BackendConfig(BaseModel):
    app: str = Field(min_length=1)
    odoo: OdooConfig
    auth: AuthConfig = Field(default_factory=AuthConfig)
    resources: list[ResourceConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_resources(self) -> BackendConfig:
        names = [resource.name for resource in self.resources]
        if len(names) != len(set(names)):
            raise ValueError("resource names must be unique")
        if self.auth.mode == "jwt" and not self.auth.jwt_secret:
            raise ValueError("auth.jwt_secret is required when auth.mode is 'jwt'")
        return self

    def resource(self, name: str) -> ResourceConfig | None:
        return next((item for item in self.resources if item.name == name), None)


def expand_env(value: Any, env: dict[str, str] | None = None) -> Any:
    """Recursively substitute ``${VAR}`` placeholders.

    Missing variables are a configuration error: silently shipping an empty API
    key would produce confusing 401s at runtime.
    """
    environment = os.environ if env is None else env
    if isinstance(value, dict):
        return {key: expand_env(item, environment) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item, environment) for item in value]
    if isinstance(value, str):

        def _replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in environment:
                raise ConfigError(f"missing environment variable: {name}")
            return environment[name]

        return _ENV_PATTERN.sub(_replace, value)
    return value


def load_config(path: str | Path, env: dict[str, str] | None = None) -> BackendConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"backend config not found: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError("backend config is not valid YAML") from exc
    if not isinstance(raw, dict):
        raise ConfigError("backend config must be a YAML mapping")
    try:
        config = BackendConfig.model_validate(expand_env(raw, env))
    except ConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 - pydantic messages are safe to surface
        raise ConfigError(f"invalid backend config: {exc}") from exc

    # The API key is provisioned after the database is initialised. Compose
    # passes ``file:/run/core/odoo_api_key`` so the value can be read once the
    # bootstrap container has finished writing it.
    if config.odoo.api_key.startswith("file:"):
        key_path = Path(config.odoo.api_key[5:])
        try:
            key = key_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"could not read Odoo API key from {key_path}") from exc
        if not key:
            raise ConfigError(f"Odoo API key file {key_path} is empty")
        config.odoo.api_key = key
    return config
