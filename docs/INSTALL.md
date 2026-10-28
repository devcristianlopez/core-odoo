# Instalación · Installation

> Kizuku — Docker provider en un solo host. Documento bilingüe: español primero, English below.

## Español

### Requisitos

- Linux con Docker Engine 24+ y Docker Compose v2 (`docker compose`).
- 6 GB de RAM recomendados (plano de control + observabilidad + un entorno).
- Puertos **80** y **443** libres. Traefik es el único servicio que publica puertos.
- Acceso al socket `/var/run/docker.sock` para el orquestador.
- `curl`, `openssl` y `python3`.
- `uv` (recomendado): instala el CLI `core-odoo` y ejecuta el servidor MCP.
- Node 24 y npm solo para desarrollar el panel (`make test`, `make lint`); la
  imagen del panel compila con Node dentro de Docker.

### Instalación rápida

```bash
git clone <repo> kizuku
cd kizuku
./install.sh --lang es
core-odoo status
```

`install.sh` genera `.env` con secretos aleatorios, crea `data/`, levanta el plano
de control y la observabilidad y, si `uv` está disponible, instala el CLI con
`uv tool install --editable ./cli`.

> Si `uv` no está, el script sigue y avisa: instala uv y ejecuta
> `uv tool install --editable ./cli`, o usa
> `uv run --project cli core-odoo <comando>` desde el repo.

```bash
core-odoo init --lang es --non-interactive
core-odoo up
```

### URLs locales

El dominio por defecto usa `nip.io` con la IP del host:

- Panel: `http://core-odoo.<IP>.nip.io`
- API: `http://api.core-odoo.<IP>.nip.io`
- App de un entorno: `http://<proyecto>-<stage>.core-odoo.<IP>.nip.io`
- Backend Odoo del entorno: `http://<proyecto>-<stage>-odoo.core-odoo.<IP>.nip.io`
- Grafana: `http://grafana.core-odoo.<IP>.nip.io`
- Uptime Kuma: `http://uptime.core-odoo.<IP>.nip.io`

Los hostnames de entorno y del backend Odoo también responden por **https** con
certificado autofirmado (`CORE_TLS_MODE=acme` los pasa a Let's Encrypt).

El usuario y la contraseña del panel/API están en `.env`
(`CORE_ADMIN_USER`, `CORE_ADMIN_PASSWORD`, `CORE_API_TOKEN`).

### Variables importantes

| Variable | Uso |
|---|---|
| `CORE_DOMAIN_SUFFIX` | Sufijo de dominio, por ejemplo `192.168.1.50.nip.io` |
| `CORE_API_URL` | URL pública del orquestador (`http://api.core-odoo.<suffix>`) |
| `CORE_DATA_DIR` | Datos dentro del contenedor (`/app/data`) |
| `CORE_PROJECTS_DIR` | Proyectos dentro del contenedor (`/app/projects`) |
| `CORE_HOST_DATA_DIR` | Ruta absoluta del host para `data/` |
| `CORE_HOST_PROJECTS_DIR` | Ruta absoluta del host para `projects/` |
| `CORE_HOST_GATEWAY_DIR` | Ruta absoluta del host para `gateway/` |
| `CORE_API_TOKEN` | Token de la API del orquestador |

Las variables `CORE_HOST_*` son obligatorias cuando el orquestador corre en
Docker: el daemon resuelve los bind mounts en el host, no dentro del contenedor.
`core-odoo init` y `install.sh` las completan automáticamente.

| Grupo | Variables |
|---|---|
| Backups | `CORE_BACKUP_ENABLED`, `CORE_BACKUP_INTERVAL_HOURS`, `CORE_BACKUP_RETENTION_DAYS`, `CORE_BACKUP_OFFSITE_DIR` |
| TLS | `CORE_TLS_MODE` (`selfsigned` o `acme`), `CORE_ACME_EMAIL` |
| Acceso | `CORE_PANEL_ALLOWED_CIDRS`, `CORE_ODOO_UI_ALLOWED_CIDRS` |
| Deploy | `CORE_DEPLOY_HEALTH_TIMEOUT`, `CORE_DEPLOY_HEALTH_INTERVAL`, `CORE_AUTO_ROLLBACK` |

### Validación

```bash
./scripts/e2e.sh
```

El E2E crea el proyecto desechable `smoke-test`, despliega `dev`, prueba CRUD de
contactos por Traefik, verifica Mission Control, borra el proyecto y comprueba
que no queden contenedores, redes ni volúmenes.

### Actualización

```bash
git pull
core-odoo upgrade
```

Los datos viven en volúmenes Docker y en `data/`; un `up` normal no los borra.

### Desinstalación

```bash
core-odoo down
docker compose -f docker-compose.yml -f docker-compose.observability.yml down -v
```

Esto elimina contenedores, redes y volúmenes del plano de control. Revisa antes
los backups en `data/backups/`.

---

## English

### Requirements

- Linux with Docker Engine 24+ and Docker Compose v2 (`docker compose`).
- 6 GB RAM recommended (control plane + observability + one environment).
- Ports **80** and **443** free. Traefik is the only published service.
- Access to `/var/run/docker.sock` for the orchestrator.
- `curl`, `openssl` and `python3`.
- `uv` (recommended): installs the `core-odoo` CLI and runs the MCP server.
- Node 24 and npm only to develop the panel (`make test`, `make lint`); the
  panel image builds with Node inside Docker.

### Quick install

```bash
git clone <repo> kizuku
cd kizuku
./install.sh --lang en
core-odoo status
```

`install.sh` writes `.env` with random secrets, creates `data/`, starts the
control plane plus observability and, when `uv` is available, installs the CLI
with `uv tool install --editable ./cli`.

> Without `uv` the script still runs and warns: install uv and run
> `uv tool install --editable ./cli`, or use
> `uv run --project cli core-odoo <command>` from the repository.

```bash
core-odoo init --lang en --non-interactive
core-odoo up
```

### Local URLs

- Panel: `http://core-odoo.<IP>.nip.io`
- API: `http://api.core-odoo.<IP>.nip.io`
- Environment app: `http://<project>-<stage>.core-odoo.<IP>.nip.io`
- Environment Odoo backend: `http://<project>-<stage>-odoo.core-odoo.<IP>.nip.io`
- Grafana: `http://grafana.core-odoo.<IP>.nip.io`
- Uptime Kuma: `http://uptime.core-odoo.<IP>.nip.io`

Environment and Odoo backend hosts also answer over **https** with a self-signed
certificate (`CORE_TLS_MODE=acme` switches them to Let's Encrypt).

Credentials are in `.env` (`CORE_ADMIN_USER`, `CORE_ADMIN_PASSWORD`,
`CORE_API_TOKEN`).

### Host path variables

`CORE_HOST_DATA_DIR`, `CORE_HOST_PROJECTS_DIR` and `CORE_HOST_GATEWAY_DIR` must
be absolute host paths when the orchestrator runs in Docker. The Docker daemon
resolves bind mounts on the host. `core-odoo init` and `install.sh` fill them.

| Group | Variables |
|---|---|
| Backups | `CORE_BACKUP_ENABLED`, `CORE_BACKUP_INTERVAL_HOURS`, `CORE_BACKUP_RETENTION_DAYS`, `CORE_BACKUP_OFFSITE_DIR` |
| TLS | `CORE_TLS_MODE` (`selfsigned` or `acme`), `CORE_ACME_EMAIL` |
| Access | `CORE_PANEL_ALLOWED_CIDRS`, `CORE_ODOO_UI_ALLOWED_CIDRS` |
| Deploy | `CORE_DEPLOY_HEALTH_TIMEOUT`, `CORE_DEPLOY_HEALTH_INTERVAL`, `CORE_AUTO_ROLLBACK` |

### Validation

```bash
./scripts/e2e.sh
```

The E2E creates the disposable `smoke-test` project, deploys `dev`, exercises
contact CRUD through Traefik, checks Mission Control, deletes the project and
asserts no containers, networks or volumes remain.

### Upgrade / uninstall

```bash
git pull
core-odoo upgrade

core-odoo down
docker compose -f docker-compose.yml -f docker-compose.observability.yml down -v
```
