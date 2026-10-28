# Core Odoo

**Self-hosted, distributable software factory built on Odoo 20.**

[![CI](https://github.com/devcristianlopez/core-odoo/actions/workflows/ci.yml/badge.svg)](https://github.com/devcristianlopez/core-odoo/actions/workflows/ci.yml) [![License](https://img.shields.io/badge/license-Apache--2.0%20%2F%20LGPL--3.0-blue.svg)](LICENSE)

Core Odoo turns Odoo into a reusable backend backbone and gives you an
Odoo.sh-style workflow: isolated environments (`dev` → `staging` → `prod`),
custom Odoo modules with real tests, generated frontends, and full
observability — all on a single Docker host.

> Estado: operativo en un host Docker. Entornos, auto-rollback, backups
> programados (con copia offsite opcional), promociones con neutralización,
> TLS, credenciales por entorno y observabilidad ya están. Siguen auto-stop,
> quotas y distribución (GHCR, releases); después, el provider Proxmox.

Projects start empty: creating one only lays out its addons and frontend, and
the first module comes from the generator. They live in `projects/` on the host
and are **local-only** (gitignored): the repository ships the templates, not the
apps. Keep each project's history in its own repository when it needs one.

## Quick start

```bash
git clone <repo> core-odoo && cd core-odoo
./install.sh            # or: uv run --project cli core-odoo init
uv run --project cli core-odoo up   # repo path; `core-odoo` alone needs the CLI installed
# panel: http://core-odoo.<your-ip>.nip.io
```

Requirements: Docker Engine 24+, Docker Compose v2, 6 GB RAM recommended
(observability + one environment). Validated with Odoo 20.0 and Traefik 3.6.

## What you get

- **Odoo 20 backbone** — reuse `res.partner`, `sale.order`, `project.task`, etc.
- **Declarative BFF** — expose only the models/fields you declare in `backend.yaml`.
- **Environment pipeline** — one isolated Compose project per stage.
- **Versioned iterations** — immutable source snapshots, database backup/restore and deploy history.
- **Module lifecycle** — scaffold, install, snapshot, approved prod deploy.
- **Promotion with neutralization** — clone staging into prod, wipe its documents and keep `last_good_iteration`.
- **Scheduled backups** — one dump per environment plus the control plane, 7-day retention, optional offsite mirror.
- **TLS and operator access** — self-signed HTTPS (or ACME with a public domain) and the Odoo backend on the operator network only.
- **Per-environment credentials** — generated Odoo admin password, readable from the panel or `core-odoo env credentials`.
- **Observability** — Prometheus, Loki (14-day retention), Grafana, Alertmanager, Uptime Kuma.
- **Mission Control** — visual panel for projects, environments, metrics and logs.
- **Bilingual** — Spanish and English (UI, CLI, docs).
- **Multi-user panel** — global roles plus per-project owner/developer/viewer membership.
- **Production approvals** — operators request, admins approve and deploy.

## Agent development

- [Agent instructions](AGENTS.md)
- [Agent layer](docs/agent/README.md)
- [Model catalogue](docs/agent/model-catalog.md)
- Skills: `skills/odoo-module`, `skills/odoo-frontend`, `skills/odoo-deploy`

```bash
core-odoo --json catalog models <project> --stage dev --model res.partner
core-odoo generate module <project> <module> --model <model> --fields "name:char;..."
core-odoo generate resource <project> <resource> --model <module>.<model> --fields name,...
core-odoo generate sdk <project> --stage dev
core-odoo generate frontend <project> --stage dev
core-odoo check <project> --catalog --frontend
core-odoo mcp serve   # MCP tools for OpenCode/Claude/Cursor
core-odoo iteration create <project> --version 0.1.0 --title "First release"
core-odoo promote <project> --iteration 0.1.0 --confirm <project>
core-odoo env credentials <project> --stage dev
```

### Development

```bash
npm --prefix mission-control ci   # once; prerequisite for make test / make lint
make test                        # pytest (orchestrator, gateway, cli) + vitest (panel)
make lint                        # ruff x3 + eslint + tsc --noEmit
```

The suites run per subproject because each one owns its `pyproject.toml` or JS
tooling. CI (`.github/workflows/ci.yml`) runs the same four suites. Module tests
and the full `make e2e` loop are covered in [Operations](docs/OPERATIONS.md).

### Landing page

`site/` holds the static presentation page — plain HTML, CSS and JS, no build
step. Preview it with `python3 -m http.server 8099 --directory site`.
`.github/workflows/pages.yml` publishes it to GitHub Pages (Settings → Pages →
Source: GitHub Actions); it is published at
<https://devcristianlopez.github.io/core-odoo/>.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Interface contract](docs/CONTRACT.md)
- [Installation](docs/INSTALL.md)
- [Operations](docs/OPERATIONS.md)
- [ADR 0001 — panel local e identidad por entorno](docs/adr/0001-panel-local-identidad-por-entorno.md)
- [Odoo 20 module notes](templates/odoo-module/README.md)

## License

Platform: Apache-2.0. Odoo modules: LGPL-3.0.
