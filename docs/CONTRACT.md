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
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<generated>
PROMETHEUS_RETENTION=15d
LOKI_RETENTION=336h
```

## 5. Orchestrator API (v1)

Base path `/api/v1`. Auth: `Authorization: Bearer <CORE_API_TOKEN>` for machine
calls, or a JWT obtained from `POST /auth/login` (UI).

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/health` | – | `{status, version}` |
| POST | `/auth/login` | `{username, password}` | `{access_token, token_type}` |
| GET | `/auth/me` | – | `{username, role}` |
| GET | `/users` | – | `[User]` (admin) |
| POST | `/users` | `{username, password, role}` | `User` (admin) |
| PATCH | `/users/{username}` | `{password?, role?, active?}` | `User` (admin) |
| GET | `/status` | – | `{docker, disk, environments, version}` |
| GET | `/projects` | – | `[Project]` |
| POST | `/projects` | `{name, template, repo_url?}` | `Project` |
| GET | `/projects/{name}` | – | `Project` |
| DELETE | `/projects/{name}` | – | `{deleted: true}` |
| GET | `/projects/{name}/environments` | – | `[Environment]` |
| POST | `/projects/{name}/deploy` | `{stage, branch?, modules?, iteration?, confirm?}` | `Environment` |
| GET | `/projects/{name}/iterations` | – | `[Iteration]` |
| GET | `/projects/{name}/iterations/{version}` | – | `Iteration` |
| GET | `/projects/{name}/members` | – | `[ProjectMember]` (admin) |
| POST | `/projects/{name}/members` | `{username}` | `ProjectMember` (admin) |
| DELETE | `/projects/{name}/members/{username}` | – | `{deleted: true}` (admin) |
| POST | `/projects/{name}/iterations` | `{version, title, notes?, branch?, commit_sha?, modules?}` | `Iteration` |
| POST | `/projects/{name}/iterations/{version}/restore` | – | `Iteration` |
| GET | `/projects/{name}/iterations/{version}/diff` | `?against=<version>` | `IterationDiff` |
| GET | `/projects/{name}/iterations/{version}/backups` | – | `[IterationBackup]` |
| POST | `/projects/{name}/iterations/{version}/backup` | `?stage=dev` | `IterationBackup` |
| POST | `/projects/{name}/environments/{stage}/start` | – | `Environment` |
| POST | `/projects/{name}/environments/{stage}/stop` | – | `Environment` |
| POST | `/projects/{name}/environments/{stage}/restart` | – | `Environment` |
| DELETE | `/projects/{name}/environments/{stage}` | – | `{deleted: true}` |
| GET | `/projects/{name}/environments/{stage}/logs` | `?tail=200` | `{logs: string}` |
| POST | `/projects/{name}/environments/{stage}/backup` | – | `{backup: true, path, created_at}` |
| GET | `/metrics/query` | `?query=<promql>` | Prometheus JSON passthrough |
| GET | `/audit` | `?limit=100` | `[AuditEvent]` |

`Project`: `{name, template, repo_url, created_at, environments: [Environment]}`
`Environment`: `{project, stage, status, url, compose_project, services, created_at, updated_at}`

Stages allowed: `dev`, `staging`, `prod`.

Roles: `admin` (everything), `operator` (deploy dev/staging, lifecycle,
iterations, backups, logs) and `viewer` (read-only). Project create/delete,
environment delete, production deploy and user management require `admin`.
The API token is always treated as `admin`. Non-admin users only see projects
where they are a member; `GET /projects` is filtered and project endpoints
return `403` for non-members. Admins can manage membership from the project
detail page.

Production deploys require `confirm` equal to the project name, a versioned
iteration and at least one database backup for that iteration. The source is
restored from the iteration snapshot before deploying.

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

- Prometheus scrapes: orchestrator, Traefik, cAdvisor, node-exporter (host),
  and any container with label `core.metrics=true`.
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
- Uptime Kuma monitors the panel, API and each environment URL.

## 10. CLI

```
core-odoo init [--lang es|en] [--domain-suffix <suffix>] [--non-interactive]
core-odoo up | down | restart | status
core-odoo project create <name> [--template <template>]
core-odoo project list
core-odoo project delete <name>
core-odoo deploy <name> --stage dev|staging|prod [--branch <branch>] [--iteration <version>] [--confirm <name>]
core-odoo iteration list <name>
core-odoo iteration create <name> --version <version> --title <title>
core-odoo iteration restore <name> <version>
core-odoo iteration diff <name> <version> [--against <version>]
core-odoo iteration backup <name> <version> --stage <stage>
core-odoo env stop|start|restart <name> --stage <stage>
core-odoo env delete <name> --stage <stage>
core-odoo logs <name> --stage <stage> [--tail 200]
core-odoo backup <name> --stage <stage>
core-odoo upgrade
core-odoo --json catalog models <project> --stage dev [--model <model>]
core-odoo generate module <project> <module> --model <model> --fields "... "
core-odoo generate resource <project> <resource> --model <odoo.model> --fields a,b,c
core-odoo generate sdk <project> --stage dev [--output frontend/src/api.generated.ts]
core-odoo generate frontend <project> --stage dev [--template <path>] [--force]
core-odoo check <project> [--catalog] [--frontend]
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
