from __future__ import annotations

from pathlib import Path

from core_odoo_cli import frontend_generator


def test_generate_frontend_writes_app_and_schema(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "backend.yaml").write_text(
        "app: demo\nresources:\n  - name: contacts\n    model: res.partner\n"
        "    fields: [name, email]\n    operations: [list, read, create, update, delete]\n",
        encoding="utf-8",
    )
    schema = [
        {
            "name": "contacts",
            "apiKey": "contacts",
            "model": "res.partner",
            "operations": ["list", "read", "create", "update", "delete"],
            "fields": [
                {"name": "name", "type": "string", "required": True},
                {"name": "email", "type": "string | null", "required": False},
            ],
        }
    ]
    monkeypatch.setattr(frontend_generator, "load_schema", lambda *args, **kwargs: schema)
    template = Path(__file__).resolve().parents[2] / "templates" / "agent-frontend"
    result = frontend_generator.generate_frontend(
        project,
        "demo",
        template_dir=template,
    )
    frontend = Path(result["path"])
    assert (frontend / "src" / "App.tsx").is_file()
    assert (frontend / "src" / "api.generated.ts").is_file()
    assert (frontend / "src" / "schema.generated.ts").is_file()
    assert '"apiKey": "contacts"' in (frontend / "src" / "schema.generated.ts").read_text()
    assert "demo-frontend" in (frontend / "package.json").read_text()
