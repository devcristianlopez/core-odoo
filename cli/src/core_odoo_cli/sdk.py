"""TypeScript SDK generation from a project's backend.yaml contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .commands.catalog import read_catalog

_FIELD_TYPES = {
    "char": "string",
    "text": "string",
    "html": "string",
    "selection": "string",
    "date": "string",
    "datetime": "string",
    "integer": "number",
    "float": "number",
    "monetary": "number",
    "boolean": "boolean",
    "json": "unknown",
    "many2one": "unknown",
    "one2many": "unknown",
    "many2many": "unknown",
}
_NULLABLE = {"string", "number", "unknown"}
_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


class SdkError(ValueError):
    """Invalid backend contract or output path."""


def _pascal(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", value)
    return "".join(part[:1].upper() + part[1:] for part in parts if part) or "Resource"


def _singular(value: str) -> str:
    if value.endswith("ies") and len(value) > 3:
        return value[:-3] + "y"
    if value.endswith("s") and not value.endswith("ss") and len(value) > 1:
        return value[:-1]
    return value


def _camel(value: str) -> str:
    pascal = _pascal(value)
    return pascal[:1].lower() + pascal[1:]


def _type_for(field: str, info: tuple[str, bool] | None) -> str:
    if field == "id":
        return "number"
    odoo_type, required = info if info else ("", False)
    base = _FIELD_TYPES.get(odoo_type or "", "unknown")
    if required:
        return base
    return f"{base} | null" if base in _NULLABLE else base


def _load_backend(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "backend.yaml"
    if not path.is_file():
        raise SdkError(f"backend.yaml not found in {project_dir}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SdkError("backend.yaml must contain a mapping")
    resources = data.get("resources")
    if not isinstance(resources, list):
        raise SdkError("backend.yaml resources must be a list")
    return data


def _render_request_helper() -> str:
    return """const API_BASE = ''

export interface ApiRequestOptions {
  method?: string
  body?: unknown
  token?: string
  baseUrl?: string
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.token) headers.Authorization = `Bearer ${options.token}`
  const response = await fetch(`${options.baseUrl ?? API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const payload = (await response.json().catch(() => ({}))) as {
    detail?: string
    error?: { message?: string }
  }
  if (!response.ok) {
    throw new Error(
      (typeof payload.detail === 'string' && payload.detail) ||
        payload.error?.message ||
        `HTTP ${response.status}`,
    )
  }
  return payload as T
}

export async function login(login: string, password: string): Promise<string> {
  const data = await apiRequest<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: { login, password },
  })
  return data.access_token
}
"""


def generate_sdk(
    project_dir: Path,
    project_name: str,
    *,
    stage: str = "dev",
    output: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    data = _load_backend(project_dir)
    target = output or project_dir / "frontend" / "src" / "api.generated.ts"
    if target.exists() and not force:
        raise SdkError(f"SDK already exists: {target} (use --force)")
    target.parent.mkdir(parents=True, exist_ok=True)

    catalog: dict[str, dict[str, tuple[str, bool]]] = {}
    resources: list[dict[str, Any]] = []
    for resource in data["resources"]:
        if not isinstance(resource, dict):
            raise SdkError("each resource must be a mapping")
        name = str(resource.get("name", "")).strip()
        model = str(resource.get("model", "")).strip()
        fields = [str(field) for field in resource.get("fields", []) if str(field).strip()]
        operations = [str(op) for op in resource.get("operations", []) if str(op).strip()]
        if not name or not model or not fields:
            raise SdkError("resources need name, model and fields")
        if model not in catalog:
            catalog[model] = {}
            try:
                payload = read_catalog(project_name, stage, model)
                catalog[model] = {
                    str(field.get("name")): (
                        str(field.get("type") or ""),
                        bool(field.get("required")),
                    )
                    for field in payload.get("fields", [])
                    if isinstance(field, dict)
                }
            except Exception:
                # Catalog is optional: fall back to unknown field types so the
                # SDK can still be generated offline.
                catalog[model] = {}
        resources.append({"name": name, "model": model, "fields": fields, "operations": operations})

    lines = [
        "/**",
        " * Generated by core-odoo generate sdk. Do not edit by hand.",
        " * Regenerate after changing backend.yaml.",
        " */",
        _render_request_helper(),
    ]
    for resource in resources:
        type_name = _pascal(_singular(resource["name"]))
        lines.append(f"export interface {type_name} {{")
        lines.append("  id: number")
        for field in resource["fields"]:
            if field == "id":
                continue
            field_type = _type_for(field, catalog[resource["model"]].get(field))
            lines.append(f"  {field}: {field_type}")
        lines.append("}")
        lines.append(f"export type {type_name}Input = Omit<{type_name}, 'id'>")
        lines.append("")

    for resource in resources:
        type_name = _pascal(_singular(resource["name"]))
        api_name = _camel(resource["name"])
        base = f"/api/{resource['name']}"
        lines.append(f"export const {api_name} = {{")
        operations = set(resource["operations"])
        if "list" in operations:
            lines.append(
                f"  list: (token: string): Promise<{type_name}[]> => "
                f"apiRequest<{type_name}[]>('{base}', {{ token }}),"
            )
        if "read" in operations:
            lines.append(
                f"  read: (token: string, id: number): Promise<{type_name}> => "
                f"apiRequest<{type_name}>(`{base}/${{id}}`, {{ token }}),"
            )
        if "create" in operations:
            lines.append(
                f"  create: (token: string, values: {type_name}Input): "
                f"Promise<{{ id: number }}> => apiRequest<{{ id: number }}>('{base}', "
                "{ method: 'POST', body: values, token }),"
            )
        if "update" in operations:
            lines.append(
                f"  update: (token: string, id: number, values: Partial<{type_name}Input>): "
                f"Promise<unknown> => apiRequest(`{base}/${{id}}`, "
                "{ method: 'PATCH', body: values, token }),"
            )
        if "delete" in operations:
            lines.append(
                f"  delete: (token: string, id: number): Promise<unknown> => "
                f"apiRequest(`{base}/${{id}}`, {{ method: 'DELETE', token }}),"
            )
        lines.append("}")
        lines.append("")

    lines.append("export const api = {")
    for resource in resources:
        lines.append(f"  {_camel(resource['name'])},")
    lines.append("}")
    lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    return {
        "path": str(target),
        "resources": [resource["name"] for resource in resources],
        "models": [resource["model"] for resource in resources],
    }
