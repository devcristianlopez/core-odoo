# smoke-test

Disposable end-to-end fixture for Core Odoo.

It is created and deleted by [`scripts/e2e.sh`](../../scripts/e2e.sh): the script
registers the project through the orchestrator API, deploys stage `dev`, exercises
the full browser → nginx → gateway → Odoo path, and then deletes the project and
asserts that no `core-smoke-test*` containers, networks or volumes remain.

> Do not use this project as a production template. The gateway runs with
> `auth.mode: none` because the fixture has no end-user credentials.

## Contents

| Path | Purpose |
|---|---|
| `odoo-sh.yaml` | Project descriptor: Odoo 20, stages, modules, tests |
| `backend.yaml` | Gateway contract: `contacts` → `res.partner` |
| `odoo/addons/smoke_test/` | Odoo module adding `nickname` to contacts |
| `frontend/` | Vite + React + TS app (list/create contacts) |

## Odoo module

`smoke_test` (LGPL-3.0, version `20.0.1.0.0`, depends `base`):

- adds `nickname = fields.Char()` to `res.partner`;
- inherits the base list, form and search views;
- adds access rights for `base.group_user`;
- includes `TransactionCase` coverage that creates a partner with a nickname;
- ships Spanish translations in `i18n/es.po`.

## Gateway resource

```yaml
resources:
  - name: contacts
    model: res.partner
    fields: [name, email, phone, city, nickname]
    operations: [list, read, create, update, delete]
    domain: []
    search_fields: [name, email]
    order: name asc
```

`odoo.db` is `smoke_test_dev` because the orchestrator derives database names as
`<project>_<stage>`; this fixture is only deployed to `dev`.

## Local development

```bash
# from the repository root
./install.sh --dev
API_HOST="api.core-odoo.$(grep '^CORE_DOMAIN_SUFFIX=' .env | cut -d= -f2-)"
curl -X POST "http://127.0.0.1/api/v1/projects" \
  -H "Host: ${API_HOST}" \
  -H "Authorization: Bearer $(grep CORE_API_TOKEN .env | cut -d= -f2-)" \
  -H 'Content-Type: application/json' \
  -d '{"name":"smoke-test","template":"odoo-module"}'
./scripts/e2e.sh
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The production image is built by the environment Compose template and served by
nginx, which proxies `/api/` to `http://gateway:8000`.
