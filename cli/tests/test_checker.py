from __future__ import annotations

from pathlib import Path

from core_odoo_cli.checker import check_project


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    module = project / "odoo" / "addons" / "demo_mod"
    (module / "security").mkdir(parents=True)
    (module / "views").mkdir()
    (module / "__manifest__.py").write_text(
        '{"name": "Demo", "depends": ["base"], "data": ["security/ir.access.csv"]}\n',
        encoding="utf-8",
    )
    (module / "security" / "ir.access.csv").write_text(
        "id,name,model_id,group_id/id,operation,domain\n"
        "access_demo,access.demo,demo_mod.lead,base.group_user,crud,\n",
        encoding="utf-8",
    )
    (project / "backend.yaml").write_text(
        "app: demo\n"
        "odoo:\n  url: http://odoo:8069\n  db: ${ODOO_DB}\n"
        "  api_key: ${ODOO_API_KEY}\n  user: core_gateway\n"
        "auth:\n  mode: jwt\n"
        "resources:\n"
        "  - name: leads\n"
        "    model: demo_mod.lead\n"
        "    fields: [name, stage]\n"
        "    operations: [list, read, create, update, delete]\n"
        "    search_fields: [name]\n",
        encoding="utf-8",
    )
    return project


def test_check_project_ok(tmp_path: Path) -> None:
    result = check_project(_project(tmp_path), "demo")
    assert result["ok"] is True
    assert result["errors"] == []


def test_check_project_flags_legacy_acl(tmp_path: Path) -> None:
    project = _project(tmp_path)
    module = project / "odoo" / "addons" / "demo_mod"
    (module / "security" / "ir.model.access.csv").write_text(
        "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n",
        encoding="utf-8",
    )
    result = check_project(project, "demo")
    assert any(error["code"] == "legacy_acl" for error in result["errors"])


def test_check_project_flags_unknown_search_field(tmp_path: Path) -> None:
    project = _project(tmp_path)
    backend = project / "backend.yaml"
    backend.write_text(
        backend.read_text(encoding="utf-8").replace(
            "search_fields: [name]", "search_fields: [missing]"
        ),
        encoding="utf-8",
    )
    result = check_project(project, "demo")
    assert any(error["code"] == "resource_search" for error in result["errors"])
