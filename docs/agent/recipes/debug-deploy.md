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
4. The Traefik router exists for the environment host.
5. The frontend `/auth/login` and `/api/...` paths respond.

Odoo 20-specific failures:

| Error | Fix |
|---|---|
| `KeyError: ir.model.access` | migrate to `security/ir.access.csv` |
| `Invalid field 'groups_id'` | use `group_ids` |
| `Template not found: web.login` | install the `web` module |
| gateway `connection refused` | set `http_interface = 0.0.0.0` |
| bind mount not found | check `CORE_HOST_*` |
