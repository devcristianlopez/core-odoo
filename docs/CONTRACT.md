# Core Odoo — Interface Contract (Sprint 1)

This document is the single source of truth for all components. Do not change
an interface without updating this file and notifying the orchestrator.

## 1. Naming

- Control stack compose project: `core-odoo`
- Environment compose project: `core-<project>-<stage>` (e.g. `core-smoke-dev`)
- Docker network (shared edge): `core-edge` (external, created by the control stack)
- Environment networks: `core-<project>-<stage>_default` (internal)
- Volumes: `core-<project>-<stage>_pgdata`, `_odoo_data`, `_filestore`, `_backups`
- Container names: `core-<project>-<stage>-<service>`
- Traefik router/service names: `<project>-<stage>-<service>`

## 2. Ports (inside containers)

| Service | Port |
|---|---|
| Odoo | 8069 |
| PostgreSQL | 5432 |
| Mailpit SMTP / UI | 1025 / 8025 |
| Gateway (BFF) | 8000 |
| Frontend (nginx) | 80 |
| Orchestrator API | 8080 |
| Mission Control (nginx) | 3000 |
| Traefik HTTP/HTTPS | 80 / 443 |
| Prometheus | 9090 |
| Loki | 3100 |
| Grafana | 3000 |
| Alertmanager | 9093 |
| Uptime Kuma | 3001 |

Host-published ports: **only 80 and 443** (Traefik). Everything else is internal
or routed through Traefik subdomains.

## 3. Hostnames (nip.io, no external DNS required)

Given host IP `<IP>` (e.g. `192.168.1.50`):

- Panel: `core-odoo.<IP>.nip.io`
- Orchestrator API: `api.core-odoo.<IP>.nip.io`
- Grafana: `grafana.core-odoo.<IP>.nip.io`
- Prometheus: `prometheus.core-odoo.<IP>.nip.io` (basic auth)
- Alertmanager: `alerts.core-odoo.<IP>.nip.io` (basic auth)
- Uptime Kuma: `uptime.core-odoo.<IP>.nip.io`
- Environment app: `<project>-<stage>.core-odoo.<IP>.nip.io`
- Odoo backend (internal only, never routed publicly): `odoo` service name

Cloudflared quick tunnel exposes only `http://traefik:80` for the panel during
testing. The URL is ephemeral by design.

## 4. Control-plane environment variables (`.env`)

```dotenv
CORE_LANG=es
CORE_DOMAIN_SUFFIX=192.168.1.50.nip.io
CORE_API_URL=http://api.core-odoo.192.168.1.50.nip.io
CORE_ADMIN_USER=admin
CORE_ADMIN_PASSWORD=<generated>
CORE_API_TOKEN=<generated>
CORE_JWT_SECRET=<generated>
CORE_ODOO_MASTER_PASSWORD=<generated>
CORE_DATA_DIR=./data
CORE_PROJECTS_DIR=./projects
CORE_TEMPLATES_DIR=./templates
# Absolute host paths for Docker-in-Docker bind mounts.
CORE_HOST_DATA_DIR=/srv/core-odoo/data
CORE_HOST_PROJECTS_DIR=/srv/core-odoo/projects
CORE_HOST_GATEWAY_DIR=/srv/core-odoo/gateway
CORE_LOG_LEVEL=INFO
CORE_DOCKER_SOCKET=/var/run/docker.sock
# A deploy only succeeds when the gateway reports odoo=true within these limits.
CORE_DEPLOY_HEALTH_TIMEOUT=300
CORE_DEPLOY_HEALTH_INTERVAL=5
CORE_AUTO_ROLLBACK=true
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<generated>
PROMETHEUS_RETENTION=15d
LOKI_RETENTION=336h
```

## 5. Orchestrator API (v1)

Base path `/api/v1`. Auth: `Authorization: Bearer <CORE_API_TOKEN>` for machine
calls, or a JWT obtained from `POST /auth/login` (UI).

`POST /auth/password` lets any authenticated panel user rotate their own
password: the current one must match and the new one must differ and be at least
8 characters. The machine API token has no password and gets `400`.

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/health` | – | `{status, version}` |
| POST | `/auth/login` | `{username, password}` | `{access_token, token_type}` |
| GET | `/auth/me` | – | `{username, role}` |
| POST | `/auth/password` | `{current_password, new_password}` | `{changed: true}` |
| GET | `/users` | – | `[User]` (admin) |
| POST | `/users` | `{username, password, role}` | `User` (admin) |
| PATCH | `/users/{username}` | `{password?, role?, active?}` | `User` (admin) |
| GET | `/status` | – | `{docker, disk, environments, version}` |
| GET | `/projects` | – | `[Project]` |
| POST | `/projects` | `{name, template, repo_url?}` | `Project` |
| GET | `/projects/{name}` | – | `Project` |
| DELETE | `/projects/{name}` | `?confirm=<name>&purge=<bool>` | `{deleted: true}` |
| GET | `/projects/{name}/environments` | – | `[Environment]` |
| POST | `/projects/{name}/deploy` | `{stage, branch?, modules?, iteration?, confirm?}` | `Environment` |
| POST | `/projects/{name}/deploy-requests` | `{iteration, reason?}` | `DeploymentRequest` |
| GET | `/deploy-requests` | `?status=pending` | `[DeploymentRequest]` |
| POST | `/deploy-requests/{id}/approve` | – | `DeploymentRequest` (admin) |
| POST | `/deploy-requests/{id}/reject` | – | `DeploymentRequest` (admin) |
| GET | `/projects/{name}/iterations` | – | `[Iteration]` |
| GET | `/projects/{name}/iterations/{version}` | – | `Iteration` |
| GET | `/projects/{name}/access` | – | `{role}` (member/admin) |
| GET | `/projects/{name}/members` | – | `[ProjectMember]` (admin) |
| POST | `/projects/{name}/members` | `{username, role}` | `ProjectMember` (admin) |
| PATCH | `/projects/{name}/members/{username}` | `{role}` | `ProjectMember` (admin) |
| DELETE | `/projects/{name}/members/{username}` | – | `{deleted: true}` (admin) |
| POST | `/projects/{name}/iterations` | `{version, title, notes?, branch?, commit_sha?, modules?}` | `Iteration` |
| POST | `/projects/{name}/iterations/{version}/restore` | – | `Iteration` |
| GET | `/projects/{name}/iterations/{version}/diff` | `?against=<version>` | `IterationDiff` |
| GET | `/projects/{name}/iterations/{version}/backups` | – | `[IterationBackup]` |
| POST | `/projects/{name}/iterations/{version}/backup` | `?stage=dev` | `IterationBackup` |
| POST | `/projects/{name}/iterations/{version}/restore-db` | `{stage?, confirm?}` | `Environment` |
| POST | `/projects/{name}/promote` | `{source_stage?, confirm?, neutralize?, skip_smoke?}` | `Environment` (admin) |
| POST | `/projects/{name}/environments/{stage}/start` | – | `Environment` |
| POST | `/projects/{name}/environments/{stage}/stop` | – | `Environment` |
| POST | `/projects/{name}/environments/{stage}/restart` | – | `Environment` |
| POST | `/projects/{name}/environments/{stage}/rollback` | `{confirm?}` | `Environment` |
| DELETE | `/projects/{name}/environments/{stage}` | `?confirm=<name>/<stage>` | `{deleted: true}` |
| GET | `/projects/{name}/environments/{stage}/logs` | `?tail=200` | `{logs: string}` |
| POST | `/projects/{name}/environments/{stage}/backup` | – | `{backup: true, path, created_at}` |
| GET | `/metrics/query` | `?query=<promql>` | Prometheus JSON passthrough |
| GET | `/audit` | `?limit=100` | `[AuditEvent]` |

`Project`: `{name, template, repo_url, created_at, environments: [Environment]}`
`Environment`: `{project, stage, status, url, compose_project, services, created_at, updated_at}`
`Environment` also carries `last_good_iteration` and `last_good_at`: the last
iteration that deployed successfully and when, i.e. the rollback target. They
move only on a successful deploy that carries an `iteration`; a failed deploy
(or an iteration-less one) never changes them.

Stages allowed: `dev`, `staging`, `prod`.

Roles: `admin` (everything), `operator` (deploy dev/staging, lifecycle,
iterations, backups, logs) and `viewer` (read-only). Project create/delete,
environment delete, production deploy and user management require `admin`.
The API token is always treated as `admin`. Non-admin users only see projects
where they are a member; `GET /projects` is filtered and project endpoints
return `403` for non-members. Project roles are `owner`, `developer` and
`viewer`: viewer is read-only, developer/owner can operate. Admins can manage
membership from the project detail page.

Production deploys require `confirm` equal to the project name, a versioned
iteration and at least one database backup for that iteration. The source is
restored from the iteration snapshot before deploying. An operator can create a
deployment request; an admin must approve it before the production deploy runs.

`POST /projects/{name}/environments/{stage}/rollback` restores the source
snapshot of `last_good_iteration` and redeploys it with module updates and the
health check. It returns `409` when there is no last good iteration (or its
snapshot is gone), `404` when the iteration record is missing, and `502` when
the redeploy fails (the environment is then `error`). Production rollback
requires `admin` and `confirm` equal to the project name.
`POST /projects/{name}/iterations/{version}/restore-db` loads the newest backup
of that iteration for `stage` into the environment and redeploys it with module
updates and the health gate. The database is recreated first and connections are
terminated, so the dump is the only source of truth afterwards. It returns `409`
when the iteration has no backup for that stage, `404` when the iteration or the
environment is missing, and `502` when the restore or the redeploy fails (the
environment is then `error`). Production requires `admin` and `confirm` equal to
the project name. `last_good_iteration` is left untouched: a data restore is not
a deploy.

A deploy that fails after the environment had a successful iteration redeploys
that iteration automatically (`CORE_AUTO_ROLLBACK`, default `true`) and returns
the recovered environment with `auto_rolled_back: true`. The failed deploy is
still audited as `environment.deploy` (failed) and the recovery as
`environment.auto_rollback`. With the flag off, or when there is nothing to roll
back to, the call returns `502` and the environment stays `error`.

`POST /projects/{name}/promote` clones a `dev`/`staging` environment into
production: before touching production it runs a read-only smoke check on the
source (services running and gateway `odoo=true`; `skip_smoke` bypasses it),
then dumps the source database, recreates the production database
from that dump, neutralizes it and redeploys with module updates and the health
gate. Promotion always requires `admin` and `confirm` equal to the project name,
and creates the `prod` environment when it does not exist yet. Neutralization
(`neutralize`, default `true`) disables `ir_cron` and `ir_mail_server`, deactivates
every user except `admin` and `core_gateway`, and points `web.base.url` at the
production URL. The dump is kept under `data/backups/<project>-<source>/`. It
returns `404` when the source environment is missing, `409` when the source has
never been deployed and `502` when the clone, the neutralization or the deploy
fails (production is then `error`).


## 6. Gateway (BFF) contract

Each environment runs one gateway. It reads `backend.yaml` mounted at
`/app/backend.yaml`.

```yaml
app: smoke-test
odoo:
  url: http://odoo:8069
  db: smoke_test
  # A literal key, or file:/run/core/odoo_api_key (bootstrap volume).
  api_key: file:/run/core/odoo_api_key
  user: core_gateway
auth:
  mode: jwt            # jwt | none
  jwt_secret: ${GATEWAY_JWT_SECRET}
  issuer: core-odoo
resources:
  - name: contacts
    model: res.partner
    fields: [name, email, phone, city, nickname]
    operations: [list, read, create, update, delete]
    domain: []
    search_fields: [name, email]
    order: name asc
```

Endpoints:

| Method | Path | Description |
|---|---|---|
| GET | `/health` | health + Odoo connectivity |
| POST | `/auth/login` | `{login, password}` -> `{access_token}` (validates against Odoo) |
| GET | `/api/{resource}` | list: `?limit=&offset=&order=&q=` |
| GET | `/api/{resource}/{id}` | read |
| POST | `/api/{resource}` | create |
| PATCH | `/api/{resource}/{id}` | update |
| DELETE | `/api/{resource}/{id}` | delete |
| GET | `/openapi.json` | generated OpenAPI 3.1 |

Security rules:

- Only models/fields/operations declared in `backend.yaml` are reachable.
- Odoo is called through `/json/2/<model>/<method>` with a bearer API key.
- Odoo 20 `create` takes `vals_list`; the gateway posts a single-element list
  and normalises the returned id.
- The gateway never forwards Odoo's raw error tracebacks; it returns a stable
  error envelope `{error: {code, message, details?}}`.
- Odoo is never exposed to the browser.

## 7. Odoo environment

- Image: `odoo:20`
- DB: `postgres:16-alpine`
- `proxy_mode = True`
- Odoo listens on `0.0.0.0:8069` inside the environment network only. The
  generated `odoo.conf` sets `http_interface = 0.0.0.0` (Odoo 20 defaults to
  loopback in this image), so the gateway can reach `/web/login` and `/json/2`.
- First boot installs `base`, `web` and the project modules. `web` provides the
  login page and session endpoints used by the gateway.
- Odoo 20 permissions use `security/ir.access.csv` (`ir.access` model,
  `operation=crud`), not the Odoo 19 `ir.model.access.csv` format.
- Master password and DB password are generated per environment.
- Mail: SMTP -> `mailpit:1025` for `dev`/`staging`; disabled for `prod` by default.
- `prod` uses `--workers=2`; `dev`/`staging` use `--workers=0`.
- Addons mounted from `projects/<name>/odoo/addons`.
- A redeploy of an existing environment runs
  `odoo -u <project modules> --stop-after-init` before the stack starts
  (explicit deploy list, else every addon with a `__manifest__.py`); only the
  first boot installs (`-i`).
- Filestore and DB data in named volumes.

## 8. Mission Control

- React 18 + TypeScript + Vite + Tailwind + shadcn-style components + Recharts.
- Talks **only** to the orchestrator (`/api/v1`), never directly to Docker,
  Prometheus or Loki (the orchestrator proxies those).
- Auth: login form -> `POST /auth/login` -> JWT stored in memory/localStorage.
- i18n: `es` and `en`, persisted in `localStorage`, default from browser.
- Pages: Login, Dashboard, Projects, Project detail, Environment detail,
  Logs viewer, Audit log, Settings.

## 9. Observability

- Prometheus scrapes: orchestrator, Traefik, cAdvisor and node-exporter (host)
  through static jobs; containers labelled `core.metrics=true` can be added with
  Docker service discovery (see `observability/README.md`).
- Loki receives container logs through Alloy (Docker discovery).
- Grafana datasources and dashboards are provisioned from files.
- Dashboards: `core-overview` and `core-environment`.
- Alert rules: environment down, HTTP 5xx rate, p95 latency, disk > 85%,
  backup missing, deploy failed, Odoo cron lag.
- Orchestrator metrics: `core_odoo_up`, `core_odoo_environments_total`,
  `core_deploy_total{project,stage,status}`,
  `core_backup_last_success_timestamp_seconds{project,stage}` and
  `core_odoo_cron_lag_seconds{project,stage,cron}`.
- Alertmanager routes to a configurable webhook (default: log only).
- Uptime Kuma is part of the stack; monitors are created from its UI.

## 10. CLI

```
core-odoo init [--lang es|en] [--domain-suffix <suffix>] [--non-interactive]
core-odoo up | down | restart | status
core-odoo project create <name> [--template <template>]
core-odoo project list
core-odoo project delete <name> [--confirm <name>] [--purge]
core-odoo deploy <name> --stage dev|staging|prod [--branch <branch>] [--iteration <version>] [--confirm <name>]
core-odoo iteration list <name>
core-odoo iteration create <name> --version <version> --title <title>
core-odoo iteration restore <name> <version>
core-odoo iteration diff <name> <version> [--against <version>]
core-odoo iteration backup <name> <version> --stage <stage>
core-odoo env stop|start|restart <name> --stage <stage>
core-odoo env rollback <name> --stage <stage> [--confirm <name>]
core-odoo env delete <name> --stage <stage> [--confirm <name>/<stage>]
core-odoo logs <name> --stage <stage> [--tail 200]
core-odoo backup <name> --stage <stage>
core-odoo upgrade
core-odoo --json catalog models <project> --stage dev [--model <model>]
core-odoo generate module <project> <module> --model <model> --fields "... "
core-odoo generate resource <project> <resource> --model <odoo.model> --fields a,b,c
core-odoo generate sdk <project> --stage dev [--output frontend/src/api.generated.ts]
core-odoo generate frontend <project> --stage dev [--template <path>] [--force]
core-odoo check <project> [--catalog] [--frontend]
core-odoo approval list [--status pending]
core-odoo approval request <project> --iteration <version> [--reason <text>]
core-odoo approval approve <request-id>
core-odoo approval reject <request-id>
core-odoo mcp serve
```

Global flags: `--lang`, `--json`, `--verbose`.

## 11. Repository layout

```
core-odoo/
├── cli/                     # Python CLI (uv, typer, rich)
├── orchestrator/            # FastAPI control plane
├── gateway/                 # FastAPI BFF
├── mission-control/         # React UI
├── observability/           # provisioning files
├── templates/               # compose, odoo-module, frontend-starter
├── projects/                # project sources (MVP: local dirs)
├── docs/                    # docs ES/EN + agent recipes
├── skills/                  # optional agent workflows
├── .github/                 # CI: one job per subproject (ruff+pytest / npm)
├── AGENTS.md                # agent rules and golden path
├── opencode.json            # OpenCode MCP config
├── .mcp.json                # Claude Code MCP config
├── docker-compose.yml       # control plane
├── docker-compose.observability.yml
├── .env.example
├── install.sh
└── LICENSE
```

## 12. Definition of done (Sprint 1)

1. `core-odoo init && core-odoo up` works on a clean Docker host.
2. `core-odoo project create smoke-test && core-odoo deploy smoke-test --stage dev`
   produces a reachable app.
3. Mission Control lists the project/environment with metrics and logs.
4. A simulated failure triggers an alert.
5. `core-odoo project delete smoke-test` leaves no containers, networks or volumes.
6. Docs exist in ES and EN.
