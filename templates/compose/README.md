# Environment Compose template

One isolated Docker Compose project per `project + stage`:

```
core-<project>-<stage>          # Compose project (contract §1)
```

| Service | Image | Internal port | Purpose |
|---|---|---|---|
| `db` | `postgres:16-alpine` | 5432 | Odoo database |
| `odoo` | `odoo:20` | 8069 | Backend, never published |
| `mailpit` | `axllent/mailpit` | 1025 / 8025 | SMTP sink + web UI |
| `gateway` | `${CORE_REPO_ROOT}/gateway` | 8000 | Declarative BFF |
| `frontend` | `${CORE_PROJECT_DIR}/frontend` | 80 | Static SPA + `/api` proxy |

Only the frontend joins the external `core-edge` network and is routed by
Traefik at:

```
http://<project>-<stage>.core-odoo.<CORE_DOMAIN_SUFFIX>
```

## Rendering

The orchestrator renders an environment stack into
`data/envs/<project>-<stage>/`. Sprint 1 currently renders
`orchestrator/app/templates/env-compose.yml.j2`; this directory is the
reference stack and must stay aligned with it (healthchecks, module install,
secret names and volume names are part of the contract):

1. `docker-compose.env.yml` is used as-is (Compose interpolation).
2. `env.template` is filled and written as `.env` next to the stack.
3. `odoo.conf.template` is filled and written as `odoo.conf`.
4. `entrypoint.sh` is copied (mode `0755`).

Required variables: `CORE_REPO_ROOT`, `CORE_PROJECT_DIR`, `CORE_PROJECT`,
`CORE_STAGE`, `CORE_DOMAIN_SUFFIX`, `ODOO_DB`, `POSTGRES_PASSWORD`,
`ODOO_MASTER_PASSWORD`, `ODOO_API_KEY`, `GATEWAY_JWT_SECRET`,
`ODOO_INIT_MODULES`, `ODOO_WITHOUT_DEMO`, `ODOO_DEMO`, `CORE_WORKERS`,
`CORE_LOG_LEVEL`, `CORE_MEM_LIMIT`, `CORE_CPU_LIMIT`.

Stage limits (architecture table):

| Stage | Memory | CPUs |
|---|---|---|
| `dev` | `2g` | `2` |
| `staging` | `3g` | `2` |
| `prod` | `4g` | `4` |

`dev` uses `CORE_WORKERS=0`. Demo data is disabled by default in every stage:
the orchestrator writes `without_demo = True` into `odoo.conf` and renders
`ODOO_DEMO=0`. `prod` uses `CORE_WORKERS=2`.

## First boot

`entrypoint.sh` waits for `pg_isready`, checks `ir_module_module` in the
database, and:

- database empty → `odoo -i <ODOO_INIT_MODULES> --without-demo=True` (unless
  `ODOO_DEMO=1`);
- module missing → installs it;
- otherwise → plain `odoo` start.

Named volumes (`pgdata`, `odoo_data`, `filestore`) are prefixed with the Compose
project, so `docker compose -p core-<project>-<stage> down -v` removes all state.
The project directory (`projects/<name>/odoo/addons`) is mounted read-only at
`/mnt/extra-addons`.

## Manual smoke run

```bash
cd data/envs/smoke-test-dev
docker compose --env-file .env -f docker-compose.env.yml config
docker compose --env-file .env -f docker-compose.env.yml up -d --build
docker compose -p core-smoke-test-dev ps
```
