"""Project-level checks that agents can run before deploying."""

from __future__ import annotations

import ast
import csv
import re
import subprocess
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import yaml

from .commands.catalog import read_catalog
from .errors import CliError

RESOURCE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MODEL_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
OPERATIONS = {"list", "read", "create", "update", "delete"}


def _issue(level: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"level": level, "code": code, "message": message, **extra}


def _manifest(path: Path) -> dict[str, Any] | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return None
    for node in tree.body:
        value_node = None
        if isinstance(node, (ast.Assign, ast.Expr)):
            value_node = node.value
        if value_node is None:
            continue
        try:
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _check_backend(project_dir: Path, issues: list[dict[str, Any]]) -> None:
    path = project_dir / "backend.yaml"
    if not path.is_file():
        issues.append(_issue("error", "backend_missing", "backend.yaml is missing", path=str(path)))
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        issues.append(
            _issue("error", "backend_invalid", f"backend.yaml is invalid: {exc}", path=str(path))
        )
        return
    if not isinstance(data, dict):
        issues.append(
            _issue("error", "backend_invalid", "backend.yaml must be a mapping", path=str(path))
        )
        return
    if "odoo" not in data:
        issues.append(_issue("warning", "backend_no_odoo", "backend.yaml has no odoo section"))
    if "auth" not in data:
        issues.append(_issue("warning", "backend_no_auth", "backend.yaml has no auth section"))
    resources = data.get("resources")
    if not isinstance(resources, list):
        issues.append(_issue("error", "backend_resources", "resources must be a list"))
        return
    seen: set[str] = set()
    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            issues.append(
                _issue("error", "resource_invalid", f"resource #{index} is not a mapping")
            )
            continue
        name = str(resource.get("name", "")).strip()
        model = str(resource.get("model", "")).strip()
        fields = resource.get("fields")
        operations = resource.get("operations")
        search = resource.get("search_fields", [])
        if not RESOURCE_NAME.match(name):
            issues.append(_issue("error", "resource_name", f"invalid resource name: {name!r}"))
        if name in seen:
            issues.append(_issue("error", "resource_duplicate", f"duplicate resource: {name}"))
        seen.add(name)
        if not MODEL_NAME.match(model):
            issues.append(
                _issue("error", "resource_model", f"invalid model: {model!r}", resource=name)
            )
        if not isinstance(fields, list) or not fields:
            issues.append(
                _issue("error", "resource_fields", "fields must be a non-empty list", resource=name)
            )
            fields = []
        for field in fields:
            if not FIELD_NAME.match(str(field)):
                issues.append(
                    _issue("error", "resource_field", f"invalid field: {field!r}", resource=name)
                )
        if not isinstance(operations, list) or not operations:
            issues.append(
                _issue(
                    "error",
                    "resource_operations",
                    "operations must be a non-empty list",
                    resource=name,
                )
            )
            operations = []
        unknown = set(map(str, operations)) - OPERATIONS
        if unknown:
            issues.append(
                _issue(
                    "error",
                    "resource_operation",
                    f"unknown operations: {', '.join(sorted(unknown))}",
                    resource=name,
                )
            )
        if isinstance(search, list) and search:
            extra = set(map(str, search)) - set(map(str, fields))
            if extra:
                issues.append(
                    _issue(
                        "error",
                        "resource_search",
                        f"search_fields not declared in fields: {', '.join(sorted(extra))}",
                        resource=name,
                    )
                )


def _check_modules(project_dir: Path, issues: list[dict[str, Any]]) -> None:
    addons = project_dir / "odoo" / "addons"
    if not addons.is_dir():
        issues.append(_issue("warning", "addons_missing", "odoo/addons directory is missing"))
        return
    modules = [
        path for path in addons.iterdir() if path.is_dir() and (path / "__manifest__.py").is_file()
    ]
    if not modules:
        issues.append(_issue("warning", "no_modules", "no Odoo modules found"))
    for module in modules:
        manifest = _manifest(module / "__manifest__.py")
        if manifest is None:
            issues.append(
                _issue(
                    "error",
                    "manifest_invalid",
                    "manifest is not a literal dict",
                    module=module.name,
                )
            )
        else:
            for data_file in manifest.get("data", []) or []:
                if not (module / str(data_file)).is_file():
                    issues.append(
                        _issue(
                            "error",
                            "manifest_data_missing",
                            f"data file is missing: {data_file}",
                            module=module.name,
                        )
                    )
        legacy = module / "security" / "ir.model.access.csv"
        if legacy.is_file():
            issues.append(
                _issue(
                    "error",
                    "legacy_acl",
                    "Odoo 20 uses security/ir.access.csv, not ir.model.access.csv",
                    module=module.name,
                )
            )
        acl = module / "security" / "ir.access.csv"
        if acl.is_file():
            with acl.open(encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle), [])
            required = {"id", "name", "model_id", "group_id/id", "operation"}
            missing = required - set(header)
            if missing:
                issues.append(
                    _issue(
                        "error",
                        "acl_header",
                        f"ir.access.csv is missing columns: {', '.join(sorted(missing))}",
                        module=module.name,
                    )
                )
        for xml in module.rglob("*.xml"):
            try:
                ElementTree.fromstring(xml.read_text(encoding="utf-8"))
            except ElementTree.ParseError as exc:
                issues.append(
                    _issue("error", "xml_invalid", f"{xml.name}: {exc}", module=module.name)
                )
        for python in module.rglob("*.py"):
            try:
                ast.parse(python.read_text(encoding="utf-8"), filename=str(python))
            except SyntaxError as exc:
                issues.append(
                    _issue("error", "python_invalid", f"{python.name}: {exc}", module=module.name)
                )


def _check_catalog(
    project_dir: Path,
    project_name: str,
    stage: str,
    issues: list[dict[str, Any]],
) -> None:
    backend = project_dir / "backend.yaml"
    if not backend.is_file():
        return
    data = yaml.safe_load(backend.read_text(encoding="utf-8")) or {}
    for resource in data.get("resources", []) if isinstance(data, dict) else []:
        if not isinstance(resource, dict):
            continue
        name = str(resource.get("name", ""))
        model = str(resource.get("model", ""))
        fields = [str(field) for field in resource.get("fields", [])]
        try:
            payload = read_catalog(project_name, stage, model)
        except CliError as exc:
            issues.append(_issue("error", "catalog_unavailable", exc.message, resource=name))
            continue
        catalog_fields = {
            str(field.get("name")) for field in payload.get("fields", []) if isinstance(field, dict)
        }
        missing = [field for field in fields if field not in catalog_fields and field != "id"]
        if missing:
            issues.append(
                _issue(
                    "error",
                    "catalog_fields",
                    f"fields not found in Odoo: {', '.join(missing)}",
                    resource=name,
                )
            )


def _check_frontend(project_dir: Path, issues: list[dict[str, Any]]) -> None:
    frontend = project_dir / "frontend"
    package = frontend / "package.json"
    if not package.is_file():
        issues.append(_issue("warning", "frontend_missing", "frontend/package.json is missing"))
        return
    if not (frontend / "node_modules").is_dir():
        issues.append(
            _issue(
                "warning",
                "frontend_deps",
                "frontend/node_modules is missing; run npm install first",
            )
        )
        return
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=frontend,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        issues.append(_issue("error", "frontend_build", f"frontend build failed: {exc}"))
        return
    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout or "").splitlines()[-8:])
        issues.append(_issue("error", "frontend_build", tail[-1000:]))


def check_project(
    project_dir: Path,
    project_name: str,
    *,
    stage: str = "dev",
    catalog: bool = False,
    frontend: bool = False,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    _check_backend(project_dir, issues)
    _check_modules(project_dir, issues)
    if catalog:
        _check_catalog(project_dir, project_name, stage, issues)
    if frontend:
        _check_frontend(project_dir, issues)
    errors = [issue for issue in issues if issue["level"] == "error"]
    warnings = [issue for issue in issues if issue["level"] == "warning"]
    return {
        "ok": not errors,
        "project": project_name,
        "path": str(project_dir),
        "errors": errors,
        "warnings": warnings,
    }
