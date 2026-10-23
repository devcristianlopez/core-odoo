# Model catalogue

`core-odoo --json catalog models` runs `odoo shell` inside the deployed environment and
returns `ir.model`, `ir.model.fields` and `ir.access` data. It is read-only.

## Examples

```bash
# Summary of installed models
core-odoo --json catalog models crm-demo --stage dev

# Machine-readable summary
core-odoo --json catalog models crm-demo --stage dev

# One model with fields and ACL
core-odoo --json catalog models crm-demo --stage dev --model res.partner
```

## Why not read the source?

The catalogue reflects the **running database**: custom modules, installed
third-party modules and Odoo 20 changes. Reading `odoo/addons` misses what is
actually installed and the ACL that applies.

## Caveats

- The environment must be running and healthy.
- The command uses `docker exec`; it is intended for the developer host, not
  from inside an arbitrary container.
- It does not expose record-level rules; those live in `ir.rule` and must be
  reviewed separately.
