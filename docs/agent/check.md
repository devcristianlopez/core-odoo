# Project checks

```bash
core-odoo check <project>
core-odoo check <project> --catalog
core-odoo check <project> --frontend
core-odoo --json check <project>
```

What it validates:

- `backend.yaml` shape, resource names, models, fields and operations.
- Odoo module manifests are literal dicts.
- Manifest data files exist.
- Odoo 20 ACLs: rejects `security/ir.model.access.csv`; checks
  `security/ir.access.csv` columns.
- XML and Python syntax.
- With `--catalog`: every declared field exists in the running Odoo model.
- With `--frontend`: runs `npm run build` when `node_modules` exists.

Exit code is `1` when there are errors. JSON output is machine-readable for
agents.
