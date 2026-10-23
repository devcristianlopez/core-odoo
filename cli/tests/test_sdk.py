from __future__ import annotations

from pathlib import Path

from core_odoo_cli import sdk


def test_generate_sdk_uses_catalog_types(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "backend.yaml").write_text(
        "app: demo\n"
        "resources:\n"
        "  - name: leads\n"
        "    model: demo_mod.lead\n"
        "    fields: [name, stage, amount]\n"
        "    operations: [list, read, create, update, delete]\n",
        encoding="utf-8",
    )

    def fake_catalog(project_name: str, stage: str, model: str) -> dict:
        return {
            "model": model,
            "fields": [
                {"name": "name", "type": "char", "required": True},
                {"name": "stage", "type": "selection", "required": True},
                {"name": "amount", "type": "float", "required": False},
            ],
        }

    monkeypatch.setattr(sdk, "read_catalog", fake_catalog)
    result = sdk.generate_sdk(project, "demo", output=project / "api.generated.ts")
    text = Path(result["path"]).read_text()
    assert "export interface Lead" in text
    assert "name: string" in text
    assert "amount: number | null" in text
    assert "export const leads" in text
