---
name: odoo-module
description: >-
  Create or extend an Odoo 20 addon inside a Core Odoo project: read the live
  catalogue, generate the module, then write models, fields, ACL, views and
  tests with Odoo 20 syntax and deploy to dev. Use for any change under
  projects/<project>/odoo/addons/<module>.
---

# Odoo module

Business models live in `projects/<project>/odoo/addons/<module>/`. The
platform (`orchestrator/`, `gateway/`, `cli/`, `mission-control/`) is not an
addon: do not put project models there. Generated projects are local and never
committed (see `AGENTS.md`).

## 1. Read the live catalogue first

```bash
core-odoo --json catalog models <project> --stage dev
core-odoo --json catalog models <project> --stage dev --model res.partner
```

The catalogue runs `odoo shell` **inside the deployed container**. It returns
the models, fields, required flags, relations and `ir.access` rows that are
actually installed, including third-party modules; the source tree does not.

- Reuse `res.partner`, `res.users`, `res.company`, `product.*`, `project.*` and
  anything the catalogue already lists. Never redefine `res.partner`.
- `container_missing` means dev is not running: deploy it before inspecting.

Read the house rules for the files you will touch, from the sibling
`odoo-guidelines` skill:

| Touching | Read |
|---|---|
| a new or moved file | [module structure](../odoo-guidelines/guidelines/module_structure.md) |
| `__manifest__.py` | [manifest](../odoo-guidelines/guidelines/manifest.md) |
| a field | [fields](../odoo-guidelines/guidelines/fields.md) |
| compute, constraint, domain, `create` | [ORM](../odoo-guidelines/guidelines/orm.md) |
| `views/`, `data/` | [views](../odoo-guidelines/guidelines/xml.md) |
| `security/` | [access rights](../odoo-guidelines/guidelines/security.md) |
| `tests/` | [tests](../odoo-guidelines/guidelines/tests.md) |
| a loop over records | [performance](../odoo-guidelines/guidelines/performance.md) |

## 2. Generate the skeleton

```bash
core-odoo generate module <project> <module> \
  --title "<Module title>" --model <model> \
  --fields "name:char;email:char;stage:selection=new:New|won:Won;notes:text"
```

It writes `__manifest__.py`, `models/<model>.py`, `security/ir.access.csv`,
`views/<model>_views.xml`, `tests/test_<model>.py` and the `__init__` files.
The model is `<module>.<model>` and the file is written once: regenerate into a
new module, or edit in place from then on.

Supported field grammar (anything else is written by hand):

| Token | Odoo field |
|---|---|
| `name:char` | `Char` |
| `notes:text` | `Text` |
| `qty:integer` | `Integer` |
| `amount:float` | `Float` |
| `active:boolean` | `Boolean` |
| `due:date`, `at:datetime` | `Date`, `Datetime` |
| `stage:selection=new:New|won:Won` | `Selection`, first option is the default |
| `partner_id:many2one=res.partner` | `Many2one` |

Suffix `!` marks a field required (`name:char!`). Monetary, Html, One2many,
Many2many, computed fields, `ondelete`, constraints and indexes are written by
hand.

## 3. Write the model

- `_name` is `<module>.<thing>`, `_description` is mandatory, add `_order`
  when the default order is wrong. One model class per file.
- Compute with `compute=` and `@api.depends(...)`; only stored computes may
  write to the database, and they must have no side effects.
- Validate with `@api.constrains`; declare SQL constraints and indexes as model
  attributes (`_check_x = models.Constraint("CHECK (...)", "msg")`,
  `_idx_x = models.Index("(field)")`). `_sql_constraints` is ignored in Odoo 20.
- Override `create` with `@api.model_create_multi` and always call `super()`.
- Translate static literals with `_()`; never build a translation string at
  runtime.
- No `create` or `search` inside a loop: use `mapped`, `filtered`,
  `recordset.ids` and batched writes.

```python
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Appointment(models.Model):
    _name = "salon.appointment"
    _description = "Salon appointment"
    _order = "scheduled_at desc"

    name = fields.Char(required=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade")
    scheduled_at = fields.Datetime(required=True)
    duration_minutes = fields.Integer(default=30)
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Done"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )

    @api.constrains("duration_minutes")
    def _check_duration(self):
        for record in self:
            if record.duration_minutes <= 0:
                raise ValidationError(self.env._("The duration must be positive."))
```

## 4. Security

Odoo 20 writes ACL as `ir.access` rows in `security/ir.access.csv`:

```csv
id,name,model_id,group_id/id,operation,domain
access_salon_appointment_user,Salon appointment user,salon.appointment,base.group_user,crud,
```

- `operation` is `crud` or a subset (`r`, `w`, `c`, `u`, `d`).
- `group_id/id` is an xmlid: `base.group_user` (internal), `base.group_system`
  (settings), or a group declared by the module.
- Add `security/ir.rule.xml` when row-level filtering is needed
  (`domain_force`, `groups`, `perm_read`/`perm_write`/...).
- Restrict one field with `groups="<module>.group_xmlid"`.
- Never grant `c`/`u`/`d` to `base.group_public` or `base.group_portal`, and do
  not widen access with a bare `sudo()`. Audit the result with the
  `odoo-security` skill.

## 5. Views

Odoo 20 uses `<list>`, `<form>` and `<search>` (never `<tree>`), and
`invisible=`/`readonly=` expressions instead of `attrs=`:

```xml
<list string="Appointments">
  <field name="name"/>
  <field name="partner_id"/>
  <field name="scheduled_at"/>
  <field name="state" widget="badge"/>
</list>
```

The generated views are a starting point: add fields, buttons and filters.
Extend another module with an explicit anchor, never by position:

```xml
<xpath expr="//field[@name='partner_id']" position="after">
  <field name="scheduled_at"/>
</xpath>
```

## 6. Tests

Every generated module ships a `TransactionCase`. Keep it meaningful: the test
must fail without the change.

```python
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAppointment(TransactionCase):
    def test_duration_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.env["salon.appointment"].create(
                {"name": "Cut", "duration_minutes": 0}
            )
```

Addon tests need a real database, so run them inside the deployed container:

```bash
docker exec core-<project>-dev-odoo \
  odoo -c /etc/odoo/odoo.conf -d <project>_dev \
  --test-enable --stop-after-init -u <module>
```

`make test` at the repository root does **not** run addon tests.

## 7. Ship it

```bash
core-odoo check <project> --catalog --frontend
core-odoo deploy <project> --stage dev
core-odoo logs <project> --stage dev --tail 200
```

A redeploy applies `-u <module>`, waits for the gateway health check and rolls
back to `last_good_iteration` when it fails. Promote, roll back and debug with
the `odoo-deploy` skill.

## Checklist

- [ ] Catalogue inspected and no model duplicated.
- [ ] Skeleton generated; business logic lives in the model.
- [ ] ACL row for the model, record rules where the row is not enough.
- [ ] Views use `<list>`/`<form>`/`<search>` and `invisible=`/`readonly=`.
- [ ] At least one test that fails without the change.
- [ ] `core-odoo check` passes.
- [ ] Deploy to dev is green and the module appears in the log.

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError: ir.model.access` | Odoo 19 ACL | use `security/ir.access.csv` |
| `Invalid field 'groups_id'` | Odoo 20 rename | use `group_ids` |
| View rejected on install | `<tree>` or `attrs=` | `<list>`, `invisible=` |
| Module not updated after deploy | not passed to `-u` | `core-odoo deploy <project> --stage dev --modules <module>` |
| Field missing in the form | not in the view | add it to the view XML |
| Constraint never created | `_sql_constraints` on Odoo 20 | declare `models.Constraint` |
