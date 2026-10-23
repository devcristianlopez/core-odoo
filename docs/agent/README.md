# Agent layer

The agent layer has four separate pieces:

| Piece | Purpose | Location |
|---|---|---|
| Instructions | Rules and boundaries | `AGENTS.md` |
| Catalogue | What Odoo already offers | `core-odoo --json catalog models` |
| Generators | Deterministic boilerplate | `core-odoo generate ...` |
| Skills | Optional task workflows | `skills/` |

## Catalogue

```bash
core-odoo --json catalog models crm-demo --stage dev
core-odoo --json catalog models crm-demo --stage dev --model res.partner
```

The JSON for a specific model contains:

```json
{
  "model": "res.partner",
  "name": "Contact",
  "fields": [
    {"name": "name", "type": "char", "required": true, "relation": null}
  ],
  "access": [
    {"group": "Internal User", "group_xmlid": "base.group_user", "operation": "r"}
  ]
}
```

Use it instead of guessing field names or reading the Odoo source.

## Generators

```bash
core-odoo generate module <project> <module> --model <model> --fields "name:char;..."
core-odoo generate resource <project> <resource> --model <odoo.model> --fields a,b,c
```

The module generator writes only Odoo 20 syntax: `ir.access.csv`, `<list>` views,
manifest and a test. The resource generator edits `backend.yaml` and preserves
the rest of the YAML.

## What still needs a human/agent decision

- domain rules and constraints,
- record-level permissions,
- frontend UX and state,
- third-party integrations,
- migrations and data imports.

## Next increments

- `generate frontend` from a BFF resource,
- `generate sdk` from OpenAPI,
- `core-odoo check` (tests + lint + contract + build),
- MCP server exposing catalogue/generate/deploy as tools.
