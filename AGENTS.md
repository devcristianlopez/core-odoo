# Core Odoo — Agent Instructions

> These are project conventions. They do not replace your system or agent
> instructions. Follow your agent/system instructions first; use this file for
> repository-specific conventions.

This repository is a self-hosted software factory built on **Odoo 20**. Odoo is
the backend: models, ORM, users, groups, ACL, views, cron, mail and reports are
already there. Do not rebuild them.

## Golden rules

1. **Do not rebuild auth, CRUD, deployment, logging or metrics.** Use the
   gateway, orchestrator and CLI.
2. **Inspect before modelling.** Run `core-odoo --json catalog models` before creating
   a model. Reuse `res.partner`, `res.users`, `res.company`, `ir.*` and the
   project modules already installed.
3. **Declarative first.** Prefer `backend.yaml` + generators over hand-written
   FastAPI/controller code.
4. **Odoo 20 is not Odoo 19.** Use `security/ir.access.csv` (`ir.access`,
   `operation=crud`), `res.users.group_ids`, and `<list>` views.
5. **Never expose Odoo to the browser.** Browser → frontend nginx → gateway →
   Odoo. The gateway allowlist is the API contract.
6. **Every generated module needs a real test.** A deploy is not proof.
7. **Keep generated sections intact.** Put business logic in the model methods
   and UI logic in the frontend; do not fight the generator.

## Golden path

```bash
# 1. What already exists?
core-odoo --json catalog models crm-demo --stage dev --model res.partner

# 2. Generate an Odoo 20 module (model, ACL, views, tests)
core-odoo generate module crm-demo crm_demo \
  --title "CRM Demo" \
  --model lead \
  --fields "name:char;contact_name:char;email:char;stage:selection=new:New|contacted:Contacted|won:Won;expected_revenue:float;notes:text"

# 3. Add the BFF resource (gateway + OpenAPI)
core-odoo generate resource crm-demo leads \
  --model crm_demo.lead \
  --fields name,contact_name,email,stage,expected_revenue,notes \
  --search-fields name,contact_name,email

# 4. For a new project, generate a complete login + CRUD frontend
#    (this also writes the typed SDK). Skip it for an existing custom app.
core-odoo generate frontend <project> --stage dev

# 4b. For an existing frontend, generate only the typed SDK
core-odoo generate sdk <project> --stage dev --output frontend/src/api.generated.ts

# 5. Validate the project before deploying
core-odoo check <project> --catalog --frontend

# 6. Deploy and inspect
core-odoo deploy crm-demo --stage dev
core-odoo logs crm-demo --stage dev
```

Field grammar:

```text
name:char
amount:float
notes:text
active:boolean
stage:selection=new:New|won:Won
partner_id:many2one=res.partner
name:char!        # explicitly required
```

## Iterations

Projects evolve through immutable, versioned snapshots:

```bash
core-odoo iteration create <project> --version 0.1.0 --title "First release"
core-odoo iteration list <project>
core-odoo iteration restore <project> 0.1.0
core-odoo iteration diff <project> 0.1.0
core-odoo iteration backup <project> 0.1.0 --stage dev
core-odoo deploy <project> --stage dev --iteration 0.1.0
```

A snapshot copies the project source (without `node_modules`, `dist`, caches or
secrets). Restoring replaces the current source tree. Deploy with `--iteration`
to link the deployment to the version in the timeline.

## What is generated vs. what you write

| Generated | You write |
|---|---|
| manifest, model skeleton, ACL, views, test | business rules, constraints, computed fields |
| `backend.yaml` resource entry | domains, permissions, custom endpoints |
| frontend scaffold | screens, UX, state, integrations |

## Odoo 20 pitfalls

- `ir.model.access` no longer exists. Use `security/ir.access.csv` with
  `id,name,model_id,group_id/id,operation,domain` and `operation=crud`.
- `res.users` uses `group_ids`, not `groups_id`.
- Views use `<list>`, `<form>`, `<search>`; not the old `<tree>` wrapper.
- The generated Odoo config sets `http_interface = 0.0.0.0`; keep it so the
  gateway can reach `/web/login` and `/json/2`.
- JSON-2 `create` takes `vals_list`.

## MCP tools

When the `core-odoo` MCP server is available (OpenCode, Claude Code, Cursor),
prefer its typed tools: `catalog_models`, `generate_module`,
`generate_resource`, `generate_sdk`, `generate_frontend`, `check_project`,
`deploy_project`, `environment_logs`. The CLI remains the source of truth.

## Skills

Optional workflows live in `skills/`:

- `skills/odoo-module` — add a model/module safely.
- `skills/odoo-frontend` — consume the BFF from a generated frontend.
- `skills/odoo-deploy` — deploy, inspect and debug an environment.

The CLI is the portable interface; skills are progressive-disclosure wrappers.
