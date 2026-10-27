---
name: odoo-deploy
description: Deploy, inspect and debug a Core Odoo environment. Use after changing a module, backend.yaml or frontend, or when a deploy/gateway/Odoo health check fails.
---

# Odoo deploy

## Workflow

```bash
core-odoo iteration create <project> --version 0.1.0 --title "First release"
core-odoo check <project> --catalog --frontend
core-odoo deploy <project> --stage dev --iteration 0.1.0
core-odoo logs <project> --stage dev --tail 200
core-odoo env rollback <project> --stage dev   # back to the last good iteration
```

A redeploy applies module updates (`-u`) and only succeeds when the gateway
reports `odoo=true` within `CORE_DEPLOY_HEALTH_TIMEOUT`; otherwise the
environment stays in `status=error` and keeps its previous
`last_good_iteration`. `core-odoo env rollback` restores that snapshot and
redeploys with the same health gate (production needs `--confirm <project>`).

If the deploy fails after restoring an iteration, inspect the iteration and the
environment logs before retrying.

Then check:

1. `docker compose -f data/envs/<project>-dev/docker-compose.yml -p core-<project>-dev ps`
2. Odoo log: module install errors.
3. `bootstrap`: `API key provisioned`.
4. Gateway `/health`: `{"status":"ok","odoo":true}`.
5. Environment URL through Traefik.
6. `GET /api/<resource>` without token → 401 when auth is `jwt`.
7. `POST /auth/login` → token; then CRUD with `Authorization: Bearer`.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `ir.model.access` KeyError | Odoo 19 ACL | migrate to `ir.access.csv` |
| `groups_id` invalid | Odoo 20 renamed it | use `group_ids` |
| `web.login` missing | `web` not installed | install `base,web,<module>` |
| gateway `odoo:false` | Odoo on loopback | `http_interface = 0.0.0.0` |
| bind mount missing | container path | set `CORE_HOST_*` |
| Traefik 404 for a new env | router not discovered | restart Traefik |
| deploy ends in `error` | `-u` failed or health gate timed out | read the logs, then `core-odoo env rollback` |
