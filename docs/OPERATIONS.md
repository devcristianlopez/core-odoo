# Operación · Operations

> Core Odoo Sprint 1. Bilingüe: español primero, English below.

## Español

### Estado del plano de control

```bash
core-odoo status
docker compose -f docker-compose.yml -f docker-compose.observability.yml ps
```

Servicios esperados: `traefik`, `orchestrator`, `mission-control`, `prometheus`,
`loki`, `alloy`, `grafana`, `alertmanager`, `uptime-kuma`, `node-exporter`,
`cadvisor`.

### Usuarios y roles

El primer admin sale de `.env` (`CORE_ADMIN_USER` / `CORE_ADMIN_PASSWORD`).
Después, un admin puede crear más usuarios en **Mission Control → Users**:

- `admin`: todo, incluido crear/borrar proyectos, usuarios y desplegar a prod.
- `operator`: despliega dev/staging, lifecycle, iteraciones, backups y logs.
- `viewer`: solo lectura.

El token de API se considera siempre admin; úsalo para automatización, no para
usuarios humanos.

Los roles globales definen el alcance general y el rol de proyecto define la
operación dentro de ese proyecto:

- `owner`: opera y puede administrar el proyecto (los miembros los gestiona un admin).
- `developer`: opera el proyecto.
- `viewer`: solo lectura dentro del proyecto.

Un `operator` o `viewer` solamente ve los proyectos donde fue agregado. El admin
agrega miembros y asigna el rol desde **Project Detail → Miembros del proyecto**.

### Exposición del panel

Mission Control es una herramienta interna para los desarrolladores: los
usuarios finales de cada app son usuarios de Odoo dentro de su entorno
(ver [ADR 0001](adr/0001-panel-local-identidad-por-entorno.md)). Por eso el
router de Traefik del panel solo acepta tráfico de redes privadas
(`CORE_PANEL_ALLOWED_CIDRS`: loopback y rangos privados por defecto).

Para habilitar otra red, agregá el rango en `.env` y recreá el panel:

```bash
# .env
CORE_PANEL_ALLOWED_CIDRS=127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
docker compose up -d mission-control
```

Con el perfil `tunnel` (cloudflared) el allowlist no filtra: Traefik ve la IP
del contenedor del túnel, no la del cliente.

### Autoservicio del panel

Cada usuario del panel cambia su propia contraseña en **Ajustes →
Contraseña** (`POST /auth/password`): pide la actual, la nueva (mínimo 8
caracteres) y su repetición. El token de API no tiene contraseña.

La sesión es un JWT con vencimiento (`CORE_JWT_TTL`); Ajustes muestra hasta
cuándo es válida y, al expirar, el panel vuelve al login. No hay recuperación
por correo: si alguien pierde la contraseña, un `admin` la resetea con
`PATCH /users/{username}`.

### Proyectos y entornos

```bash
core-odoo project list
core-odoo project create <nombre> --template odoo-module
core-odoo deploy <nombre> dev --modules base,<modulo>
core-odoo logs <nombre> dev
core-odoo env restart <nombre> dev
core-odoo env delete <nombre> dev
```

Cada entorno es un proyecto Compose aislado (`core-<proyecto>-<stage>`) con
PostgreSQL, Odoo, gateway, frontend y Mailpit (dev/staging). Solo el frontend se
publica a través de Traefik.

`--template odoo-module` instala el addon en `odoo/addons/<slug>`, el único
directorio del proyecto que se monta en Odoo. Al crear el proyecto y en cada
deploy el orquestador además hace `chown` del árbol al dueño de
`CORE_PROJECTS_DIR` (es un bind mount del host), así el usuario del host puede
editar los archivos.

### Módulos Odoo 20

Odoo 20 cambió el modelo de permisos:

- El modelo es `ir.access`, no `ir.model.access`.
- El archivo se llama `security/ir.access.csv`.
- Columnas: `id,name,model_id,group_id/id,operation,domain`.
- `operation` usa `crud` (o combinaciones como `r`, `w`, `c`, `u`, `d`).

El manifiesto debe declarar `security/ir.access.csv`. Las plantillas
`templates/odoo-module/` y el fixture `projects/smoke-test/` ya usan este formato.

### API key del gateway

El servicio `bootstrap` se ejecuta una sola vez, después de que Odoo está sano:

1. Crea el usuario `core_gateway` con `base.group_user` y
   `base.group_partner_manager`.
2. Genera una API key JSON-2 persistente.
3. La escribe en el volumen `secrets`, en `/run/core/odoo_api_key`.

El gateway espera a que `bootstrap` termine y lee `file:/run/core/odoo_api_key`.
Para rotar la key, elimina el proyecto/entorno y vuelve a desplegar.

### Iteraciones

```bash
core-odoo iteration create <proyecto> --version 0.1.0 --title "Primera versión"
core-odoo iteration list <proyecto>
core-odoo iteration restore <proyecto> 0.1.0
core-odoo iteration diff <proyecto> 0.1.0
core-odoo iteration backup <proyecto> 0.1.0 --stage dev
core-odoo deploy <proyecto> --stage dev --iteration 0.1.0
# Producción: requiere un backup de la iteración y confirmar el nombre
core-odoo deploy <proyecto> --stage prod --iteration 0.1.0 --confirm <proyecto>
```

Cada iteración guarda un snapshot del código fuente del proyecto (sin
`node_modules`, `dist`, cachés ni secretos). Restaurar reemplaza el código actual
por el snapshot. Desplegar con `--iteration` deja la versión y etapa en el
historial.

Producción tiene guardrails: solo admin, requiere una iteración, un backup de
esa iteración y confirmar el nombre del proyecto. El código se restaura desde
el snapshot antes de desplegar.

`iteration diff` compara archivos contra la iteración anterior. `iteration
backup` crea un dump de PostgreSQL y lo asocia a la iteración; restaurar la base
desde ese dump todavía es una operación manual.

Borrar un proyecto sin `--purge` desregistra el proyecto y elimina sus entornos,
pero conserva el código fuente y las iteraciones. `--purge` elimina también el
código, los snapshots y los backups.

### Promover a producción

Un admin clona staging (o dev) en producción sin empezar de cero:

```bash
core-odoo promote <proyecto> --source staging --confirm <proyecto>
```

El orquestador vuelca la base de origen, recrea la de producción con ese dump,
la neutraliza y redespliega con `-u` y health gate. La neutralización desactiva
`ir_cron` e `ir_mail_server`, desactiva todos los usuarios salvo `admin` y
`core_gateway`, y apunta `web.base.url` a la URL de producción. El dump queda en
`data/backups/<proyecto>-<origen>/`.

Usa `--no-neutralize` sólo si querés conservar los usuarios y los crons tal como
estaban en el origen. La base de producción anterior se descarta.

### Aprobaciones de producción

Un `operator` no despliega directo a producción: crea una solicitud.

```bash
core-odoo approval request <proyecto> --iteration 0.1.0 --reason "listo para prod"
core-odoo approval list --status pending
core-odoo approval approve <id>
core-odoo approval reject <id>
```

La solicitud exige una iteración con backup. Al aprobarla, un admin ejecuta el
deploy con los guardrails de producción.

### Backups

```bash
core-odoo backup <nombre> dev
```

Los archivos quedan en `data/backups/<proyecto>-<stage>/`. El orquestador expone
`core_backup_last_success_timestamp_seconds` para la alerta `BackupMissing`.
Copia los backups fuera del host periódicamente.

### Restaurar base de datos desde una iteración

```bash
core-odoo iteration backup <proyecto> 0.1.0 --stage dev
core-odoo iteration restore-db <proyecto> 0.1.0 --stage staging
# Producción: admin y confirmación tipada
core-odoo iteration restore-db <proyecto> 0.1.0 --stage prod --confirm <proyecto>
```

Se usa el backup más reciente de esa iteración para el entorno elegido. El
orquestador termina las conexiones, recrea la base, carga el dump y redespliega
con `-u` y el health gate; si algo falla, el entorno queda en `error`. No cambia
`last_good_iteration`: restaurar datos no es un deploy.

### Métricas y logs

- Prometheus: interno, `http://prometheus:9090` dentro de `core-edge`.
- Grafana: `http://grafana.core-odoo.<IP>.nip.io`.
- Loki: interno; Mission Control consulta logs a través del orquestador.
- Alertmanager: interno, sin UI publicada.
- Métricas propias: `core_odoo_up`, `core_odoo_environments_total`,
  `core_deploy_total`, `core_backup_last_success_timestamp_seconds`,
  `core_odoo_cron_lag_seconds`.

### Actualizaciones, healthcheck y rollback

Un redeploy de un entorno existente actualiza los módulos antes de levantar el
stack: un contenedor one-shot corre `odoo -u <módulos> --stop-after-init`. Los
módulos son la lista explícita del deploy o, si no la pasas, todos los addons
bajo `projects/<proyecto>/odoo/addons` con `__manifest__.py`. El primer deploy
solo instala (`-i`), nunca actualiza; el entrypoint instala al arrancar los
módulos que todavía falten.

Ciclo normal para cambiar un módulo, sin borrar el entorno: editas el addon,
subes la versión en `__manifest__.py` y despliegas.

```bash
core-odoo deploy <proyecto> --stage dev   # -u de los módulos + healthcheck
```

Odoo solo corre `migrations/` cuando cambió la versión del manifiesto. Una
migración de datos va en `odoo/addons/<módulo>/migrations/<versión>/`, con
scripts `pre-*.py` y `post-*.py`; `<versión>` tiene que coincidir con la del
`__manifest__.py`. Se ejecutan como parte del `-u`.

Un deploy solo se da por bueno cuando el gateway reporta `odoo=true` en su
`/health` dentro de `CORE_DEPLOY_HEALTH_TIMEOUT` (300 s), reintentando cada
`CORE_DEPLOY_HEALTH_INTERVAL` (5 s). Si se agota el tiempo o falla la
actualización, el entorno queda en `status=error`, la falla se audita y se
conserva el `last_good_iteration` anterior. Cada deploy exitoso con
`--iteration` registra `last_good_iteration` / `last_good_at`.

`status=error` no borra nada: el código y la base siguen ahí, pero el entorno no
está sano. Un deploy nuevo sobre un entorno en `error` —o detenido— igual aplica
`-u`: el proveedor levanta el servicio `db`, espera `pg_isready` y consulta si
la base existe, así que recuperas desplegando, sin rollback previo.

`core-odoo env rollback <proyecto> --stage dev` restaura el snapshot de código
de la última iteración buena y vuelve a desplegar con actualización y
healthcheck. Sin iteración buena devuelve `409`; en `prod` exige admin y
`--confirm <proyecto>`. Restaurar reemplaza `backend.yaml`, `odoo/`,
`frontend/`, `odoo-sh.yaml` y `README.md` con el snapshot, así que guarda en git
o en una iteración lo que no quieras perder.

### Desarrollo

Los comandos de desarrollo corren por subproyecto, nunca desde la raíz del repo:

```bash
npm --prefix mission-control ci   # requisito previo de make test / make lint
make test    # pytest en orchestrator/, gateway/, cli/ + vitest en mission-control/
make lint    # ruff x3 + eslint + tsc --noEmit (app y tsconfig.node.json)
make fmt     # ruff format en orchestrator/, gateway/ y cli/
```

`test` y `lint` paran en el primer subproyecto que falla y dicen cuál falló. Si
falta `mission-control/node_modules`, abortan antes del paso de JS con el mensaje
que pide ejecutar `npm --prefix mission-control ci`.

Por qué por directorio: cada subproyecto es dueño de su configuración.
`orchestrator/`, `gateway/` y `cli/` declaran `pytest` (`testpaths = ["tests"]`)
y `ruff` en su propio `pyproject.toml`; `mission-control/` tiene su `eslint`,
`vitest` y `tsconfig`. Correr `pytest` desde la raíz no encuentra ese
`pyproject.toml` y en cambio recolecta `projects/`, `templates/` y
`data/iterations/`, y termina en `ImportPathMismatchError` (o
`ModuleNotFoundError: odoo`).

Tests de módulos Odoo: los `TransactionCase` bajo
`projects/*/odoo/addons/*/tests` no los corre `make test`, porque necesitan una
base Odoo inicializada. Se ejecutan dentro de un entorno ya desplegado:

```bash
docker exec core-<proyecto>-<stage>-odoo \
  odoo -c /etc/odoo/odoo.conf -d <db> \
  --test-enable --stop-after-init -u <modulo>
# si el contenedor ya sirve en 8069: agrega --http-port=8070
```

Ciclo completo: `make e2e` (o `./scripts/e2e.sh`) crea `smoke-test`, despliega
`dev`, ejercita navegador → nginx → gateway → Odoo, verifica Mission Control,
borra el proyecto y comprueba que el host queda limpio.

CI: `.github/workflows/ci.yml` corre los mismos cuatro conjuntos, un job por
subproyecto (`orchestrator`, `gateway`, `cli`, `mission-control`), en cada push a
`main` y en cada pull request.

### Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `docker compose up failed` al desplegar | Bind mount con ruta del contenedor | Verificar `CORE_HOST_*` en `.env` |
| Gateway `degraded` / Odoo `false` | Odoo escucha en `127.0.0.1` | `http_interface = 0.0.0.0` en `odoo.conf` |
| `Template not found: web.login` | Falta el módulo `web` | Inicializar `base,web,<módulos>` |
| `KeyError: ir.model.access` | ACL con formato viejo | Migrar a `security/ir.access.csv` |
| Frontend 404 en Traefik tras crear entorno | Traefik no descubrió el contenedor | `docker compose restart traefik` |
| Bootstrap falla con `Invalid field 'groups_id'` | Odoo 20 usa `group_ids` | Actualizar `bootstrap.py` |

### Logs útiles

```bash
docker compose -f docker-compose.yml logs -f orchestrator
docker logs -f core-<proyecto>-<stage>-odoo
docker logs -f core-<proyecto>-<stage>-gateway
docker logs -f core-<proyecto>-<stage>-bootstrap
```

---

## English

### Control plane health

```bash
core-odoo status
docker compose -f docker-compose.yml -f docker-compose.observability.yml ps
```

### Panel exposure

Mission Control is an internal tool for developers; each app's end users are
Odoo users inside their own environment (see
[ADR 0001](adr/0001-panel-local-identidad-por-entorno.md)). Its Traefik router
therefore only accepts traffic from private networks
(`CORE_PANEL_ALLOWED_CIDRS`, loopback and RFC1918 ranges by default).

To allow another network, add the range to `.env` and recreate the panel:

```bash
# .env
CORE_PANEL_ALLOWED_CIDRS=127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
docker compose up -d mission-control
```

With the `tunnel` profile (cloudflared) the allowlist does not filter: Traefik
sees the tunnel container IP, not the client IP.

### Panel accounts

Each panel user rotates their own password in **Settings → Password**
(`POST /auth/password`): it asks for the current one, the new one (8 characters
minimum) and a repetition. The API token has no password.

The session is a JWT with an expiry (`CORE_JWT_TTL`); Settings shows how long it
is valid and the panel returns to the login page when it expires. There is no
email recovery: an `admin` resets a lost password with
`PATCH /users/{username}`.

### Projects and environments

```bash
core-odoo project list
core-odoo project create <name> --template odoo-module
core-odoo deploy <name> dev --modules base,<module>
core-odoo logs <name> dev
core-odoo env restart <name> dev
core-odoo env delete <name> dev
```

`--template odoo-module` installs the addon under `odoo/addons/<slug>`, the only
project directory mounted into Odoo. Scaffolding and every deploy also `chown`
the project tree to the owner of `CORE_PROJECTS_DIR` (a host bind mount) so the
host user can edit it.

### Odoo 20 permissions

Odoo 20 replaced `ir.model.access` with `ir.access`. Use
`security/ir.access.csv` with columns
`id,name,model_id,group_id/id,operation,domain` and `operation=crud`. The module
manifest must list that file.

### Gateway API key

The one-shot `bootstrap` service waits for Odoo, creates `core_gateway`, grants
`base.group_user` and `base.group_partner_manager`, generates a persistent
JSON-2 key and writes it to `/run/core/odoo_api_key` in the `secrets` volume.
The gateway depends on bootstrap completion and reads the file.

### Promoting to production

An admin clones staging (or dev) into production instead of starting from zero:

```bash
core-odoo promote <project> --source staging --confirm <project>
```

The orchestrator dumps the source database, recreates production from that dump,
neutralizes it and redeploys with `-u` and the health gate. Neutralization
disables `ir_cron` and `ir_mail_server`, deactivates every user except `admin`
and `core_gateway`, and points `web.base.url` at the production URL. The dump is
kept under `data/backups/<project>-<source>/`.

Use `--no-neutralize` only when you want the source users and crons as they are.
The previous production database is discarded.

### Backups and observability

`core-odoo backup <name> <stage>` writes to
`data/backups/<project>-<stage>/`. Prometheus/Loki/Alertmanager are internal;
Grafana and Uptime Kuma are routed through Traefik. Custom metrics:
`core_odoo_up`, `core_odoo_environments_total`, `core_deploy_total`,
`core_backup_last_success_timestamp_seconds`, `core_odoo_cron_lag_seconds`.

### Restoring a database from an iteration

```bash
core-odoo iteration backup <project> 0.1.0 --stage dev
core-odoo iteration restore-db <project> 0.1.0 --stage staging
# Production: admin plus a typed confirmation
core-odoo iteration restore-db <project> 0.1.0 --stage prod --confirm <project>
```

The newest backup of that iteration for the chosen environment is used. The
orchestrator terminates connections, recreates the database, loads the dump and
redeploys with `-u` and the health gate; a failure leaves the environment in
`error`. `last_good_iteration` is untouched: a data restore is not a deploy.

### Updates, healthcheck and rollback

Redeploying an existing environment updates the modules before the stack
starts: a one-shot container runs `odoo -u <modules> --stop-after-init`. The
modules are the explicit deploy list or, when you omit it, every addon under
`projects/<project>/odoo/addons` with a `__manifest__.py`. A first deploy only
installs (`-i`) and never updates; the entrypoint installs at boot whatever is
still missing.

Normal loop for a module change, no need to delete the environment: edit the
addon, bump the version in `__manifest__.py`, deploy.

```bash
core-odoo deploy <project> --stage dev   # -u for project modules + healthcheck
```

Odoo only runs `migrations/` when the manifest version changed. Put data
migrations in `odoo/addons/<module>/migrations/<version>/` as `pre-*.py` and
`post-*.py`; `<version>` must match the `__manifest__.py` you deploy. They run
as part of `-u`.

A deploy only succeeds when the gateway reports `odoo=true` on its `/health`
within `CORE_DEPLOY_HEALTH_TIMEOUT` (300s), retried every
`CORE_DEPLOY_HEALTH_INTERVAL` (5s). On timeout or update failure the environment
is marked `status=error`, the failure is audited and the previous
`last_good_iteration` is kept. Every successful deploy with `--iteration`
records `last_good_iteration` / `last_good_at`.

`status=error` deletes nothing: the code and the database stay, but the
environment is not healthy. A new deploy on an `error` — or stopped —
environment still applies `-u`: the provider starts the `db` service, waits for
`pg_isready` and probes whether the database exists, so deploying again is the
recovery path — no rollback first.

`core-odoo env rollback <project> --stage dev` restores the source snapshot of
the last good iteration and redeploys it with updates and the healthcheck. With
no good iteration it returns `409`; `prod` requires admin and
`--confirm <project>`. Restoring replaces `backend.yaml`, `odoo/`, `frontend/`,
`odoo-sh.yaml` and `README.md` with the snapshot, so keep in git or in an
iteration anything you do not want to lose.

### Development

Development commands run per subproject, never from the repository root:

```bash
npm --prefix mission-control ci   # prerequisite for make test / make lint
make test    # pytest in orchestrator/, gateway/, cli/ + vitest in mission-control/
make lint    # ruff x3 + eslint + tsc --noEmit (app and tsconfig.node.json)
make fmt     # ruff format in orchestrator/, gateway/ and cli/
```

`test` and `lint` stop at the first failing subproject and name it. If
`mission-control/node_modules` is missing, both abort before the JS step with a
message telling you to run `npm --prefix mission-control ci`.

Each subproject owns its tool configuration: `orchestrator/`, `gateway/` and
`cli/` declare `pytest` (`testpaths = ["tests"]`) and `ruff` in their own
`pyproject.toml`; `mission-control/` ships its own `eslint`, `vitest` and
`tsconfig`. Running `pytest` from the root does not pick up that
`pyproject.toml`; it collects `projects/`, `templates/` and `data/iterations/`
instead and fails with `ImportPathMismatchError` (or
`ModuleNotFoundError: odoo`).

Odoo module tests (`projects/*/odoo/addons/*/tests`) are `TransactionCase`
classes that need an initialised Odoo database, so `make test` does not run them.
Run them inside a deployed environment:

```bash
docker exec core-<project>-<stage>-odoo \
  odoo -c /etc/odoo/odoo.conf -d <db> \
  --test-enable --stop-after-init -u <module>
# add --http-port=8070 when the container already serves on 8069
```

Full loop: `make e2e` (or `./scripts/e2e.sh`) creates `smoke-test`, deploys
`dev`, exercises browser → nginx → gateway → Odoo, checks Mission Control,
deletes the project and asserts a clean host.

CI: `.github/workflows/ci.yml` runs the same four suites, one job per subproject
(`orchestrator`, `gateway`, `cli`, `mission-control`), on every push to `main`
and every pull request.

### Troubleshooting

See the Spanish table above; the symptoms and fixes are identical.
