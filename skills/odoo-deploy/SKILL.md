---
name: odoo-deploy
description: >-
  Deploy, promote, roll back and debug a Kizuku environment: iterations,
  health gate, compose logs, Odoo admin credentials and common failures. Use
  after changing a module, backend.yaml or frontend, or when a deploy or
  health check fails.
---

# Odoo deploy

## What a deploy does

`core-odoo deploy <project> --stage <stage>` renders the environment compose
file, builds the frontend, starts PostgreSQL, Odoo, the gateway and nginx, and
applies module updates (`-u`). It returns only when the gateway reports
`odoo=true`; otherwise it rolls back to `last_good_iteration`
(`CORE_AUTO_ROLLBACK`) and the response carries `auto_rolled_back=true`. With
nothing to roll back to, the environment stays in `status=error`.

## Golden path

```bash
core-odoo check <project> --catalog --frontend
core-odoo iteration create <project> --version 0.1.0 --title "First release"
core-odoo deploy <project> --stage dev --iteration 0.1.0
core-odoo logs <project> --stage dev --tail 200
core-odoo env credentials <project> --stage dev
```

## Iterations and promotion

```bash
core-odoo iteration list <project>
core-odoo iteration diff <project> 0.1.0
core-odoo iteration backup <project> 0.1.0 --stage staging
core-odoo promote <project> --source staging --iteration 0.1.0 --confirm <project>
```

Promotion restores the iteration snapshot, clones the staging database and
filestore, neutralizes cron jobs, mail servers and users, and wipes the
business documents that must not reach production. It needs an iteration
(newest by default) and sets `last_good_iteration`. Production always requires
`--confirm <project>`.

## Rollback and recovery

```bash
core-odoo env rollback <project> --stage dev      # last good iteration
core-odoo iteration restore <project> 0.1.0       # source only
core-odoo iteration restore-db <project> 0.1.0 --stage dev --confirm <project>
```

`env rollback` restores the snapshot and redeploys through the same health
gate. Restoring data does **not** move `last_good_iteration`. Never
`TRUNCATE ... CASCADE` the Odoo schema: `res_company` owns foreign keys to
`account_move`, so a cascade wipes users and partners. Use the ordered deletes
in the orchestrator.

## Verify a deploy

1. `docker compose -f data/envs/<project>-<stage>/docker-compose.yml -p core-<project>-<stage> ps`
2. Odoo log: module install or migration errors.
3. Bootstrap log: `API key provisioned`.
4. Gateway `/health`: `{"status":"ok","odoo":true}`.
5. The environment URL through Traefik loads the frontend.
6. `GET /api/<resource>` without a token returns 401 (when `auth.mode: jwt`).
7. `POST /auth/login` returns a token; a CRUD call with `Authorization: Bearer`
   succeeds.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `ir.model.access` KeyError | Odoo 19 ACL | migrate to `ir.access.csv` |
| `groups_id` invalid | Odoo 20 renamed it | use `group_ids` |
| `web.login` missing | `web` not installed | install `base,web,<module>` |
| gateway `odoo:false` | Odoo on loopback | `http_interface = 0.0.0.0` |
| bind mount missing | container path | set `CORE_HOST_*` |
| Traefik 404 for a new env | router not discovered | restart Traefik |
| deploy ends in `error` | `-u` failed or health timed out | read the logs, then `core-odoo env rollback` |
| frontend 502 after deploy | nginx started before the gateway | redeploy; the deploy waits for health |
| `container_missing` in `catalog` | dev not deployed | deploy dev first |

## Safety

- Ask a human before anything destructive on production.
- `promote` and `deploy --stage prod` need `--confirm <project>`; deletions
  need the same typed confirmation.
- `--purge` removes source, iterations and backups; without it the project is
  only unregistered.
- Do not delete backups or dumps to "make room" without being asked.
