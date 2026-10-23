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

El token de API se considera siempre admin; usalo para automatización, no para
usuarios humanos.

Los roles son globales, pero el acceso a proyectos es por membresía. Un
`operator` o `viewer` solamente ve los proyectos donde fue agregado. El admin
agrega miembros desde **Project Detail → Miembros del proyecto**.

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
Para rotar la key, eliminá el proyecto/entorno y volvé a desplegar.

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

### Backups

```bash
core-odoo backup <nombre> dev
```

Los archivos quedan en `data/backups/<proyecto>-<stage>/`. El orquestador expone
`core_backup_last_success_timestamp_seconds` para la alerta `BackupMissing`.
Copiá los backups fuera del host periódicamente.

### Métricas y logs

- Prometheus: interno, `http://prometheus:9090` dentro de `core-edge`.
- Grafana: `http://grafana.core-odoo.<IP>.nip.io`.
- Loki: interno; Mission Control consulta logs a través del orquestador.
- Alertmanager: interno, sin UI publicada.
- Métricas propias: `core_odoo_up`, `core_odoo_environments_total`,
  `core_deploy_total`, `core_backup_last_success_timestamp_seconds`.

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

### Projects and environments

```bash
core-odoo project list
core-odoo project create <name> --template odoo-module
core-odoo deploy <name> dev --modules base,<module>
core-odoo logs <name> dev
core-odoo env restart <name> dev
core-odoo env delete <name> dev
```

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

### Backups and observability

`core-odoo backup <name> <stage>` writes to
`data/backups/<project>-<stage>/`. Prometheus/Loki/Alertmanager are internal;
Grafana and Uptime Kuma are routed through Traefik. Custom metrics:
`core_odoo_up`, `core_odoo_environments_total`, `core_deploy_total`,
`core_backup_last_success_timestamp_seconds`.

### Troubleshooting

See the Spanish table above; the symptoms and fixes are identical.
