# Recipe: debug a deploy

```bash
core-odoo deploy <project> --stage dev
core-odoo logs <project> --stage dev --tail 200
docker compose -f data/envs/<project>-dev/docker-compose.yml -p core-<project>-dev ps
```

Check in this order:

1. `bootstrap` completed (`API key provisioned`).
2. Odoo is healthy and reaches PostgreSQL.
3. Gateway `/health` reports `odoo: true`.
4. The Traefik router exists for the environment host. Traefik only publishes
   routers for **healthy** containers, so a 404 right after a deploy usually
   means the frontend healthcheck has not passed yet; `core-odoo deploy` waits
   for it, a manual `docker compose up` does not.
5. The frontend `/auth/login` and `/api/...` paths respond.
6. The Odoo backend answers on `<project>-<stage>-odoo…` from an allowed
   network, and `core-odoo env credentials <project> --stage <stage>` gives its
   admin password.

Odoo 20-specific failures:

| Error | Fix |
|---|---|
| `KeyError: ir.model.access` | migrate to `security/ir.access.csv` |
| `Invalid field 'groups_id'` | use `group_ids` |
| `Template not found: web.login` | install the `web` module |
| gateway `connection refused` | set `http_interface = 0.0.0.0` |
| bind mount not found | check `CORE_HOST_*` |
