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
| dev | feature branches, demo data, tests | fresh DB | 2 GB / 2 CPU |
| staging | production clone, neutralized | prod copy | 3 GB / 2 CPU |
| prod | live | persistent | 4 GB / 4 CPU |

Naming: `core-<project>-<stage>`. Isolated networks and volumes; attached to the
shared `core-edge` network only for Traefik routing.

## Module lifecycle

```
scaffold → dev (install + tests + lint) → staging (prod clone + -u + smoke)
        → prod (backup + snapshot + -u + healthcheck) → rollback on failure
```

Odoo modules are ordinary addons under `projects/<name>/odoo/addons/`. A version
bump in `__manifest__.py` triggers `-u` during promotion. Data migrations live in
`migrations/<version>/`.

## Security boundaries

1. Only ports 80/443 are published (Traefik).
2. Odoo and PostgreSQL are never routed publicly.
3. Per-environment secrets are generated at deploy time.
4. The orchestrator uses a scoped Docker socket access; the API is token/JWT
   protected.
5. Cloudflare Tunnel is optional and exposes only the panel during testing.
6. Every mutating action is written to the audit log.

## Observability

Prometheus scrapes the orchestrator, Traefik, cAdvisor, node-exporter and any
container labelled `core.metrics=true`. Alloy ships container logs to Loki.
Grafana provisions two dashboards (overview and per-environment). Alertmanager
covers availability, latency, errors, disk, backups, deploys and Odoo cron.

## Roadmap

1. **Sprint 1 (current):** Docker provider, control plane, observability, smoke-test.
2. GitOps: webhooks, promotion, DB clone/neutralization, quality gates.
3. Reliability: backups/restore, rollback, auto-stop, quotas.
4. Distribution: installer, GHCR images, releases, upgrade path.
5. Proxmox provider with parity.

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
