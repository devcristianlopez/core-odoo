# Architecture

Core Odoo is a **self-hosted software factory** on top of Odoo 20. It provides an
Odoo.sh-style lifecycle (dev → staging → prod) on a single Docker host and, in a
later phase, on Proxmox via the same provider interface.

## Layers

```
┌──────────────────────────────────────────────────────────────┐
│ Mission Control (React)      CLI (core-odoo)                 │
└───────────────┬───────────────────────┬──────────────────────┘
                │ /api/v1 (JWT/token)   │
                ▼                       ▼
┌──────────────────────────────────────────────────────────────┐
│ Orchestrator (FastAPI)                                       │
│  projects · environments · deploy · audit · metrics proxy    │
└───────────────┬──────────────────────────────────────────────┘
                │ Docker Engine API / compose CLI
                ▼
┌──────────────────────────────────────────────────────────────┐
│ Environments (one Compose project per stage)                 │
│  odoo:20 · postgres:16 · mailpit · gateway (BFF) · frontend  │
└───────────────┬──────────────────────────────────────────────┘
                │ JSON-2 API (server-side only)
                ▼
┌──────────────────────────────────────────────────────────────┐
│ Odoo backbone (res.partner, sale.order, project.task, ...)   │
└──────────────────────────────────────────────────────────────┘

Observability (parallel plane):
  Prometheus + exporters ─┐
  Loki + Alloy ───────────┼──> Grafana dashboards / Alertmanager / Uptime Kuma
  Traefik metrics ────────┘
```

## Why a BFF gateway

Exposing Odoo directly would leak its internal model, ACL quirks and API keys to
the browser. The gateway:

- exposes only the resources declared in `backend.yaml`;
- validates fields, domains and operations;
- authenticates end users and issues its own JWT;
- talks to Odoo with a scoped bot API key over JSON-2;
- publishes an OpenAPI contract used to generate the TypeScript client.

The result: frontends are generated against a stable, small API while Odoo stays
an implementation detail.

## Environments

Each stage is an isolated Docker Compose project:

| Stage | Purpose | Data | Limits |
|---|---|---|---|
| dev | day-to-day development and module tests | fresh DB | 2 GB / 2 CPU |
| staging | isolated environment to validate before release; `promote` clones it into prod | own DB | 3 GB / 2 CPU |
| prod | live | persistent | 4 GB / 4 CPU |

Naming: `core-<project>-<stage>`. Isolated networks and volumes; attached to the
shared `core-edge` network only for Traefik routing.

## Module lifecycle

```
scaffold → addon on disk → install on first boot → module updates on redeploy
        → iteration snapshot
        → prod deploy (approval + typed confirm + iteration + DB backup + source restore)
```

Odoo modules are ordinary addons under `projects/<name>/odoo/addons/`, and a
deploy is a (re)start of the stage stack, preceded by an `-u` on redeploy. Today
the path from repo to environment is:

1. **Scaffold** — `core-odoo generate module` writes the manifest, model
   skeleton, `security/ir.access.csv`, views and a test into
   `projects/<name>/odoo/addons/<module>/`. The directory is bind-mounted
   read-only at `/mnt/extra-addons`.
2. **Install on first boot** — `entrypoint.sh` waits for PostgreSQL and checks
   `ir_module_module`. An empty database is initialised with `-i` for the
   declared modules; on later boots `-i` is passed only for modules that are
   missing (for example a newly mounted addon). Tests and lint are not run by a
   deploy — run them in the module directory.
3. **Module updates on redeploy** — a redeploy of an existing environment
   upgrades the modules before the stack starts: a one-shot
   `odoo -u <modules> --stop-after-init` runs, then the health gate. It is
   guarded by a database probe (the `db` service is started and `pg_isready`
   polled first, then the database is checked for existence), so a retry after a
   failed deploy still applies the pending upgrades. `migrations/<version>/`
   scripts run as part of `-u` when the manifest version changed.
4. **Iteration snapshot** — `iteration create` copies the project source
   (excluding `node_modules`, `dist`, caches and secrets) into an immutable,
   versioned snapshot. `iteration restore` puts that source tree back and
   `iteration backup` dumps the database for the version.
5. **Production guardrails** — a prod deploy needs the `admin` role, a
   `--confirm <project>` typed confirmation, an existing iteration and at least
   one database backup for it; the iteration source tree is restored before the
   stack starts. Operators request a deploy and an admin approves or rejects it
   (approvals are recorded in the audit log).

**Implemented:** module updates on redeploy — the one-shot `-u` described above,
guarded by the database probe and followed by the health gate.
`core-odoo env rollback` redeploys the same way.
`core-odoo iteration restore-db` loads an iteration dump into an environment,
recreates the database and redeploys through the same gate. The panel is locked
to the dev network (`CORE_PANEL_ALLOWED_CIDRS`) and each user rotates their own
password with `POST /auth/password`.

**Also implemented:** promotion with a prod clone and neutralization
(`core-odoo promote`) gated by a read-only smoke check of the source, and
automatic rollback to `last_good_iteration` when a deploy fails
(`CORE_AUTO_ROLLBACK`). `core-odoo env rollback` remains for manual recovery.

## Security boundaries

1. Only ports 80/443 are published (Traefik).
2. Apps reach Odoo only through the gateway. The Odoo backend UI is routed on
   `<project>-<stage>-odoo…` but restricted to the operator network with an IP
   allowlist (`CORE_ODOO_UI_ALLOWED_CIDRS`); PostgreSQL is never routed.
3. Per-environment secrets are generated at deploy time, including the Odoo
   `admin` password (readable through the credentials endpoint and the panel).
4. The orchestrator uses a scoped Docker socket access; the API is token/JWT
   protected.
5. Cloudflare Tunnel is optional and exposes only the panel during testing.
6. Every mutating action is written to the audit log.

## Observability

Prometheus scrapes the orchestrator, Traefik, cAdvisor and node-exporter through
static jobs; containers labelled `core.metrics=true` can be added with Docker
service discovery (see `observability/README.md`). Alloy ships container logs to
Loki.
Grafana provisions two dashboards (overview and per-environment). Alertmanager
covers availability, latency, errors, disk, backups, deploys and Odoo cron.

## Roadmap

1. **Sprint 1 (done):** Docker provider, control plane, observability, smoke-test.
2. **Sprint 2 (done):** quality gates/CI; DB restore; promote with prod clone and
   neutralization behind a staging smoke gate; panel self-service; automatic
   rollback on failed deploys. Identity model in
   [ADR 0001](adr/0001-panel-local-identidad-por-entorno.md).
3. **Operational hardening (done):** scheduled backups with offsite mirror,
   TLS (self-signed, ACME opt-in), per-environment credentials, deep promotion
   neutralization and log rotation.
4. Reliability: auto-stop and quotas.
5. Distribution: GHCR images, releases, upgrade path.
6. Proxmox provider with parity.

## Odoo 20 specifics (validated)

- `ir.model.access` no longer exists; modules use `security/ir.access.csv`
  with the `ir.access` model and `operation=crud`.
- The image defaults HTTP to loopback; generated `odoo.conf` sets
  `http_interface = 0.0.0.0` so gateway traffic works over the environment
  network.
- `res.users` uses `group_ids` (not `groups_id`); the bootstrap service creates
  `core_gateway` with `base.group_user` and `base.group_partner_manager`.
- The gateway reads the generated JSON-2 key from
  `/run/core/odoo_api_key` (shared `secrets` volume) after bootstrap completes.
- Compose bind-mount sources are translated from container paths to host paths
  through `CORE_HOST_DATA_DIR`, `CORE_HOST_PROJECTS_DIR` and
  `CORE_HOST_GATEWAY_DIR`.
