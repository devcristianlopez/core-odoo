---
name: odoo-module
description: Create or extend an Odoo 20 module safely using the Core Odoo catalogue and generators. Use when adding models, fields, ACL, views or tests to a project.
---

# Odoo module

## Workflow

1. Run `core-odoo --json catalog models <project> --stage dev`.
2. Reuse an existing model if it fits. Do not duplicate `res.partner`.
3. Generate:
   ```bash
   core-odoo generate module <project> <module> \
     --title "<title>" --model <model> --fields "<field grammar>"
   ```
4. Add business logic to `models/<model>.py`.
5. Add domain tests under `tests/`.
6. Deploy to `dev` and verify through the gateway.

## Odoo 20 rules

- `security/ir.access.csv`, model `ir.access`, `operation=crud`.
- `res.users.group_ids`, not `groups_id`.
- `<list>` views, not `<tree>`.
- Keep `http_interface = 0.0.0.0` in generated config.

## Never

- Do not add a second auth stack.
- Do not expose Odoo directly.
- Do not edit generated ACL/view files by hand unless you are intentionally
  diverging; prefer regenerating or writing a separate inherited view.
