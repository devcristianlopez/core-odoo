"""Deterministic scaffolds that keep agents away from boilerplate.

The generator deliberately favours a small, explicit field grammar over magic:
``name:char;email:char;amount:float``. Selection options use ``|`` and
many2one relations use ``=`` (for example ``stage:selection=new:New|won:Won``
or ``partner_id:many2one=res.partner``).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import yaml

FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
SUPPORTED_TYPES = {
    "char": "Char",
    "text": "Text",
    "integer": "Integer",
    "float": "Float",
    "boolean": "Boolean",
    "date": "Date",
    "datetime": "Datetime",
    "selection": "Selection",
    "many2one": "Many2one",
}
ALL_OPERATIONS = ["list", "read", "create", "update", "delete"]


class GeneratorError(ValueError):
    """Invalid generator input."""


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    label: str
    required: bool = False
    relation: str | None = None
    selection: tuple[tuple[str, str], ...] = ()


def parse_fields(raw: str) -> list[FieldSpec]:
    fields: list[FieldSpec] = []
    seen: set[str] = set()
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise GeneratorError(f"expected field:type, got {chunk!r}")
        name, rest = chunk.split(":", 1)
        name = name.strip()
        if not FIELD_NAME.match(name):
            raise GeneratorError(f"invalid field name: {name!r}")
        if name in seen:
            raise GeneratorError(f"duplicate field: {name}")
        seen.add(name)

        required = rest.endswith("!")
        if required:
            rest = rest[:-1]
        type_name, _, argument = rest.partition("=")
        type_name = type_name.strip().lower()
        if type_name not in SUPPORTED_TYPES:
            raise GeneratorError(
                f"unsupported field type {type_name!r}; use {', '.join(sorted(SUPPORTED_TYPES))}"
            )
        if type_name not in {"selection", "many2one"} and argument:
            raise GeneratorError(f"field {name!r} does not accept '=' arguments")

        selection: tuple[tuple[str, str], ...] = ()
        relation: str | None = None
        if type_name == "selection":
            options: list[tuple[str, str]] = []
            for item in argument.split("|"):
                value, _, label = item.partition(":")
                value = value.strip()
                label = label.strip() or value.replace("_", " ").title()
                if not value:
                    raise GeneratorError(f"selection field {name!r} has an empty option")
                options.append((value, label))
            if not options:
                raise GeneratorError(f"selection field {name!r} needs options")
            selection = tuple(options)
        elif type_name == "many2one":
            relation = argument.strip()
            if not relation:
                raise GeneratorError(f"many2one field {name!r} needs a relation")

        fields.append(
            FieldSpec(
                name=name,
                type=type_name,
                label=name.replace("_", " ").title(),
                required=required or name == "name",
                relation=relation,
                selection=selection,
            )
        )
    if not fields:
        raise GeneratorError("at least one field is required")
    return fields


def _model_name(module: str, model: str) -> str:
    return model if "." in model else f"{module}.{model}"


def _class_name(model_name: str) -> str:
    return "".join(part.title() for part in model_name.split(".")).replace("_", "")


def _field_line(field: FieldSpec) -> str:
    args: list[str] = []
    if field.type == "selection":
        options = ", ".join(f'("{value}", "{label}")' for value, label in field.selection)
        args.append(f"selection=[{options}]")
        args.append(f'default="{field.selection[0][0]}"')
    elif field.type == "many2one":
        args.append(f'"{field.relation}"')
    elif field.type == "float":
        args.append("digits=(12, 2)")
    if field.required:
        args.append("required=True")
    inner = ", ".join(args)
    return f'    {field.name} = fields.{SUPPORTED_TYPES[field.type]}({inner})'


def render_model(module: str, model: str, title: str, fields: list[FieldSpec]) -> str:
    model_name = _model_name(module, model)
    lines = [
        "# Copyright 2026 Core Odoo contributors",
        "# SPDX-License-Identifier: LGPL-3.0",
        "from odoo import fields, models",
        "",
        "",
        f"class {_class_name(model_name)}(models.Model):",
        f'    _name = "{model_name}"',
        f'    _description = "{title}"',
        '    _order = "create_date desc"',
        "",
    ]
    lines.extend(_field_line(field) for field in fields)
    lines.append("")
    return "\n".join(lines)


def render_views(module: str, model: str, title: str, fields: list[FieldSpec]) -> str:
    model_name = _model_name(module, model)
    selection = next((field for field in fields if field.type == "selection"), None)
    list_fields = [field for field in fields if field.type != "text"]
    search_fields = [field for field in fields if field.type in {"char", "text"}][:3]
    form_fields = "\n".join(
        f'                            <field name="{f.name}"/>' for f in fields[1:]
    )
    list_xml = "\n".join(f'                <field name="{f.name}"/>' for f in list_fields)
    search_xml = "\n".join(f'                <field name="{f.name}"/>' for f in search_fields)
    header = (
        f'                    <field name="{selection.name}" widget="statusbar"/>\n'
        if selection
        else ""
    )
    return f'''<?xml version="1.0" encoding="utf-8"?>
<!-- Copyright 2026 Core Odoo contributors — SPDX-License-Identifier: LGPL-3.0 -->
<odoo>
    <record id="view_{module}_{model}_list" model="ir.ui.view">
        <field name="name">{model_name}.list</field>
        <field name="model">{model_name}</field>
        <field name="arch" type="xml">
            <list string="{escape(title)}">
{list_xml}
            </list>
        </field>
    </record>

    <record id="view_{module}_{model}_form" model="ir.ui.view">
        <field name="name">{model_name}.form</field>
        <field name="model">{model_name}</field>
        <field name="arch" type="xml">
            <form string="{escape(title)}">
                <header>
{header}                </header>
                <sheet>
                    <div class="oe_title">
                        <h1><field name="{fields[0].name}" placeholder="{escape(title)}"/></h1>
                    </div>
                    <group>
{form_fields}
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="view_{module}_{model}_search" model="ir.ui.view">
        <field name="name">{model_name}.search</field>
        <field name="model">{model_name}</field>
        <field name="arch" type="xml">
            <search string="{escape(title)}">
{search_xml}
            </search>
        </field>
    </record>

    <record id="action_{module}_{model}" model="ir.actions.act_window">
        <field name="name">{escape(title)}</field>
        <field name="res_model">{model_name}</field>
        <field name="view_mode">list,form</field>
    </record>

    <menuitem id="menu_{module}_root" name="{escape(title)}" sequence="90"/>
    <menuitem id="menu_{module}_{model}" name="{escape(title)}"
              parent="menu_{module}_root" action="action_{module}_{model}" sequence="10"/>
</odoo>
'''


def render_manifest(module: str, title: str) -> str:
    return f'''# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0
{{
    "name": "{title}",
    "summary": "{title} Odoo module",
    "version": "20.0.1.0.0",
    "category": "Uncategorized",
    "license": "LGPL-3",
    "author": "Kizuku",
    "website": "https://kizuku.local",
    "depends": ["base"],
    "data": [
        "security/ir.access.csv",
        "views/{module}_views.xml",
    ],
    "installable": True,
    "application": True,
}}
'''


def render_tests(model_name: str) -> str:
    return f'''# Copyright 2026 Core Odoo contributors
# SPDX-License-Identifier: LGPL-3.0
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class Test{_class_name(model_name)}(TransactionCase):
    def test_model_is_registered(self):
        model = self.env["{model_name}"]
        self.assertEqual(model._name, "{model_name}")
'''


def generate_module(
    project_dir: Path,
    module: str,
    title: str,
    model: str,
    fields_raw: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    if not MODULE_NAME.match(module):
        raise GeneratorError("module must be snake_case (letters, numbers, underscores)")
    target = project_dir / "odoo" / "addons" / module
    if target.exists():
        if not force:
            raise GeneratorError(f"module already exists: {target}")
        shutil.rmtree(target)

    fields = parse_fields(fields_raw)
    model_name = _model_name(module, model)
    model_file = model_name.rsplit(".", 1)[-1].replace("-", "_")
    view_file = f"{module}_views.xml"
    (target / "models").mkdir(parents=True)
    (target / "security").mkdir()
    (target / "views").mkdir()
    (target / "tests").mkdir()
    (target / "__init__.py").write_text("from . import models\n", encoding="utf-8")
    (target / "models" / "__init__.py").write_text(
        f"from . import {model_file}\n", encoding="utf-8"
    )
    (target / "models" / f"{model_file}.py").write_text(
        render_model(module, model, title, fields), encoding="utf-8"
    )
    (target / "security" / "ir.access.csv").write_text(
        "id,name,model_id,group_id/id,operation,domain\n"
        f"access_{module}_{model_file}_user,{model_name} user,{model_name},base.group_user,crud,\n",
        encoding="utf-8",
    )
    (target / "views" / view_file).write_text(
        render_views(module, model, title, fields), encoding="utf-8"
    )
    (target / "__manifest__.py").write_text(render_manifest(module, title), encoding="utf-8")
    (target / "tests" / "__init__.py").write_text(
        f"from . import test_{model_file}\n", encoding="utf-8"
    )
    (target / "tests" / f"test_{model_file}.py").write_text(
        render_tests(model_name), encoding="utf-8"
    )
    return {
        "module": module,
        "model": model_name,
        "title": title,
        "path": str(target),
        "files": sorted(
            str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()
        ),
    }


def generate_resource(
    project_dir: Path,
    resource: str,
    model: str,
    fields_raw: str,
    *,
    operations: str = ",".join(ALL_OPERATIONS),
    search_fields: str = "name",
    order: str | None = None,
) -> dict[str, Any]:
    backend = project_dir / "backend.yaml"
    if backend.is_file():
        data = yaml.safe_load(backend.read_text(encoding="utf-8")) or {}
    else:
        data = {
            "app": project_dir.name,
            "odoo": {
                "url": "http://odoo:8069",
                "db": "${ODOO_DB}",
                "api_key": "${ODOO_API_KEY}",
                "user": "core_gateway",
            },
            "auth": {
                "mode": "jwt",
                "jwt_secret": "${GATEWAY_JWT_SECRET}",
                "issuer": "core-odoo",
            },
            "resources": [],
        }
    if not isinstance(data, dict):
        raise GeneratorError("backend.yaml must contain a mapping")
    resources = data.setdefault("resources", [])
    if not isinstance(resources, list):
        raise GeneratorError("backend.yaml resources must be a list")
    field_list = [field.strip() for field in fields_raw.split(",") if field.strip()]
    if not field_list:
        raise GeneratorError("resource fields cannot be empty")
    operation_list = [op.strip() for op in operations.split(",") if op.strip()]
    unknown = set(operation_list) - set(ALL_OPERATIONS)
    if unknown:
        raise GeneratorError(f"unknown operations: {', '.join(sorted(unknown))}")
    search_list = [field.strip() for field in search_fields.split(",") if field.strip()]
    entry: dict[str, Any] = {
        "name": resource,
        "model": model,
        "fields": field_list,
        "operations": operation_list,
        "domain": [],
        "search_fields": search_list,
    }
    if order:
        entry["order"] = order
    for index, existing in enumerate(resources):
        if isinstance(existing, dict) and existing.get("name") == resource:
            resources[index] = entry
            break
    else:
        resources.append(entry)
    backend.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return {"resource": resource, "model": model, "path": str(backend)}
