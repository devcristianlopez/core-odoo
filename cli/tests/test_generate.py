from __future__ import annotations

from pathlib import Path

import yaml

from core_odoo_cli.generator import (
    GeneratorError,
    generate_module,
    generate_resource,
    parse_fields,
)


def test_parse_fields_supports_selection_and_required() -> None:
    fields = parse_fields("name:char;stage:selection=new:New|won:Won;amount:float!")
    assert [field.name for field in fields] == ["name", "stage", "amount"]
    assert fields[0].required is True
    assert fields[1].selection == (("new", "New"), ("won", "Won"))
    assert fields[2].required is True


def test_parse_fields_rejects_bad_input() -> None:
    try:
        parse_fields("name")
    except GeneratorError:
        pass
    else:  # pragma: no cover - the assertion documents the contract
        raise AssertionError("expected GeneratorError")


def test_generate_module_writes_odoo20_files(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    (project / "odoo" / "addons").mkdir(parents=True)
    result = generate_module(
        project,
        "crm_demo",
        "CRM Demo",
        "lead",
        "name:char;stage:selection=new:New|won:Won;amount:float",
    )
    target = Path(result["path"])
    assert result["model"] == "crm_demo.lead"
    assert (target / "security" / "ir.access.csv").is_file()
    assert "base.group_user,crud" in (target / "security" / "ir.access.csv").read_text()
    model = (target / "models" / "lead.py").read_text()
    assert "_name = \"crm_demo.lead\"" in model
    assert '("new", "New")' in model
    view = (target / "views" / "crm_demo_views.xml").read_text()
    assert "<list" in view
    assert 'widget="statusbar"' in view


def test_generate_resource_appends_backend_resource(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    result = generate_resource(
        project,
        "leads",
        "crm_demo.lead",
        "name,stage,amount",
        search_fields="name,stage",
    )
    data = yaml.safe_load(Path(result["path"]).read_text())
    assert data["resources"][0]["name"] == "leads"
    assert data["resources"][0]["model"] == "crm_demo.lead"
    assert data["resources"][0]["search_fields"] == ["name", "stage"]
