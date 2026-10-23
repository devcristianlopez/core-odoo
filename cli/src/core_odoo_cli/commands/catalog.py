"""Odoo catalogue commands for agents and humans."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from rich.console import Console
from rich.table import Table

from ..errors import CliError
from ..i18n import t
from ..options import argument, option
from ..output import emit, info, machine_output

console = Console()
CATALOG_MARKER = "CORE_CATALOG_JSON="


def _database_name(project: str, stage: str) -> str:
    return f"{project.replace('-', '_')}_{stage}"


def _container_name(project: str, stage: str) -> str:
    return f"core-{project}-{stage}-odoo"


def _catalog_script(model: str | None) -> str:
    model_literal = repr(model)
    return f'''import json
model_name = {model_literal}
domain = [("model", "=", model_name)] if model_name else [("transient", "=", False)]
records = env["ir.model"].search(domain, order="model")
result = []
for record in records:
    payload = {{"model": record.model, "name": record.name}}
    if model_name:
        fields = []
        for field in env["ir.model.fields"].search([("model_id", "=", record.id)], order="name"):
            fields.append(
                {{
                    "name": field.name,
                    "type": field.ttype,
                    "label": field.field_description,
                    "required": bool(field.required),
                    "readonly": bool(field.readonly),
                    "relation": field.relation or None,
                    "selection": field.selection or None,
                    "store": bool(field.store),
                }}
            )
        accesses = []
        for access in env["ir.access"].search([("model_id", "=", record.id)]):
            group = access.group_id
            external = group.get_external_id().get(group.id) if group else None
            accesses.append(
                {{
                    "group": group.name if group else None,
                    "group_xmlid": external,
                    "operation": access.operation,
                    "domain": access.domain or None,
                }}
            )
        payload["fields"] = fields
        payload["access"] = accesses
    else:
        payload["field_count"] = env["ir.model.fields"].search_count([("model_id", "=", record.id)])
    result.append(payload)
print("{CATALOG_MARKER}" + json.dumps(result, default=str, ensure_ascii=False))
'''


def read_catalog(project: str, stage: str, model: str | None = None) -> dict[str, Any]:
    container = _container_name(project, stage)
    exists = subprocess.run(
        ["docker", "ps", "--filter", f"name=^{container}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if exists.returncode != 0 or exists.stdout.strip() != container:
        raise CliError(t("error.container_missing", container=container), code="container_missing")

    command = [
        "docker",
        "exec",
        "-i",
        container,
        "odoo",
        "shell",
        "-c",
        "/etc/odoo/odoo.conf",
        "-d",
        _database_name(project, stage),
        "--no-http",
        "--log-level=error",
    ]
    try:
        result = subprocess.run(
            command,
            input=_catalog_script(model),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise CliError(t("error.catalog_failed", detail=str(exc)), code="catalog_failed") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-5:]
        raise CliError(t("error.catalog_failed", detail=" ".join(detail)), code="catalog_failed")
    for line in reversed(result.stdout.splitlines()):
        if line.startswith(CATALOG_MARKER):
            try:
                payload = json.loads(line[len(CATALOG_MARKER) :])
            except json.JSONDecodeError as exc:
                raise CliError(
                    t("error.catalog_failed", detail=str(exc)), code="catalog_failed"
                ) from exc
            if model:
                return payload[0] if payload else {"model": model, "fields": [], "access": []}
            return {"count": len(payload), "models": payload}
    detail = (result.stderr or result.stdout or "").strip().splitlines()[-5:]
    raise CliError(t("error.catalog_failed", detail=" ".join(detail)), code="catalog_failed")


def catalog_models(
    project: str = argument("arg.project"),
    stage: str = option("opt.stage", "dev", "--stage"),
    model: str | None = option("opt.model", None, "--model"),
) -> None:
    """List installed Odoo models, fields and access rules."""
    payload = read_catalog(project, stage, model)
    if machine_output():
        emit(payload)
        return
    if model:
        console.print(f"[bold]{payload.get('model')}[/bold] — {payload.get('name', '')}")
        table = Table()
        table.add_column(t("header.field"))
        table.add_column(t("header.type"))
        table.add_column(t("header.required"))
        table.add_column(t("header.relation"))
        for field in payload.get("fields", []):
            table.add_row(
                field.get("name", ""),
                str(field.get("type", "")),
                "yes" if field.get("required") else "",
                str(field.get("relation") or ""),
            )
        console.print(table)
        return
    table = Table(title=t("msg.catalog_loaded", count=payload.get("count", 0)))
    table.add_column(t("header.model"))
    table.add_column(t("header.name"))
    table.add_column(t("header.fields"))
    for row in payload.get("models", []):
        table.add_row(row.get("model", ""), row.get("name", ""), str(row.get("field_count", "")))
    console.print(table)
    info(t("msg.catalog_hint"))
