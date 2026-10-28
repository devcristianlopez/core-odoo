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
7. **Projects are local.** `projects/<name>` is gitignored and never committed;
   only `templates/` and the platform live in this repository.
8. **Keep generated sections intact.** Put business logic in the model methods
   and UI logic in the frontend; do not fight the generator.

## Golden path

A new project starts **empty**: `core-odoo project create <project>` only lays
out `odoo/addons` and `frontend/`. The first module always comes from the
generator, so the project name and the module name never collide. Deploy after
that first module exists, otherwise Odoo boots with `base` and `web` only.

```bash
# 0. Create the project (empty: addons + frontend, no module yet)
core-odoo project create <project>

# 1. What already exists? (needs a deployed environment)
core-odoo --json catalog models <project> --stage dev --model res.partner

# 2. Generate an Odoo 20 module (model, ACL, views, tests)
core-odoo generate module <project> <module> \
  --title "<Module title>" \
  --model <model> \
  --fields "name:char;email:char;stage:selection=new:New|won:Won;notes:text"

# 3. Add the BFF resource (gateway + OpenAPI)
core-odoo generate resource <project> <resource> \
  --model <module>.<model> \
  --fields name,email,stage,notes \
  --search-fields name,email

# 4. For a new project, generate a complete login + CRUD frontend
#    (this also writes the typed SDK). Skip it for an existing custom app.
core-odoo generate frontend <project> --stage dev

# 4b. For an existing frontend, generate only the typed SDK
core-odoo generate sdk <project> --stage dev --output frontend/src/api.generated.ts

# 5. Validate the project before deploying
core-odoo check <project> --catalog --frontend

# 6. Deploy and inspect
core-odoo deploy <project> --stage dev
# A redeploy applies module updates (-u); a failed deploy rolls back to
# last_good_iteration, and `core-odoo env rollback` recovers by hand.
core-odoo logs <project> --stage dev

# 7. Promote (needs an iteration; restores its snapshot, copies the filestore,
#    wipes the cloned documents and sets last_good_iteration)
core-odoo promote <project> --iteration 0.1.0 --confirm <project>

# 8. The Odoo backend (crons, mail, accounting) and its generated admin password
core-odoo env credentials <project> --stage dev
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
# Production requires --confirm <project>, an iteration and an iteration backup
core-odoo deploy <project> --stage prod --iteration 0.1.0 --confirm <project>
# Preferred: clone staging (iteration optional, newest by default)
core-odoo promote <project> --source staging --iteration 0.1.0 --confirm <project>
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

## Copy and language

Spanish copy is **neutral Spanish with tuteo**: second person is `tú`
(`puedes`, `tienes`, `escribes`, `usa`, `crea`), never Rioplatense voseo
(`tenés`, `podés`, `mirá`, `usá`, `escribí`, `creá`) and never Argentinian
slang (`acá`, `che`, `laburo`, `plata`). Use `aquí`, not `acá`. This applies to
the landing page in `site/`, Mission Control strings, CLI locales, docs,
templates and generated projects. English copy is US English.

## Permissions

The panel has `admin`, `operator` and `viewer` users. The API token and MCP
server act as `admin`. Non-admin users only see projects where they are a
member. Project roles are `owner`, `developer` and `viewer`; viewer is read-only.
Ask a human before destructive operations on production. Destructive deletes
require typed confirmation (`--confirm` in the CLI). Use `--purge` to
remove source code, iteration snapshots and backups; without it the project is
only unregistered.

## MCP tools

When the `core-odoo` MCP server is available (OpenCode, Claude Code, Cursor),
prefer its typed tools: `catalog_models`, `generate_module`,
`generate_resource`, `generate_sdk`, `generate_frontend`, `check_project`,
`deploy_project`, `environment_logs`. The CLI remains the source of truth.

## Skills and agents

Skills are on-demand playbooks under `skills/`; `skills/README.md` is the index
and `skills/UPSTREAM.md` records the vendored Odoo set. Load the one that
matches the task instead of guessing.

| Task | Skill |
|---|---|
| models, fields, views, ACL, tests | `odoo-module` + `odoo-guidelines` |
| security audit of an addon | `odoo-security` |
| review a diff, commit or module | `odoo-review` |
| screens against the BFF | `odoo-frontend` |
| deploy, promote, roll back, logs | `odoo-deploy` |
| OWL, JavaScript or SCSS under `static/` | `odoo-web-guidelines` |

`odoo-module`, `odoo-frontend` and `odoo-deploy` are ours; the rest are copied
verbatim from Odoo 20 (`skills/UPSTREAM.md`). Do not edit the vendored files.

Project agents live in `.opencode/agents/`:

- `odoo-module-dev` builds addons (catalogue, generator, tests, dev deploy),
- `odoo-reviewer` reviews without editing,
- `odoo-operator` deploys, promotes and rolls back without touching code.

After editing a skill or an agent, run `python3 scripts/check_skills.py`; CI
runs the same check. The CLI remains the portable interface.
