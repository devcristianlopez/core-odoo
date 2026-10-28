# Upstream Odoo skills

Four skills under `skills/` are vendored **verbatim** from Odoo's own skill
library, so agents get Odoo's house rules instead of a paraphrase.

| Skill | Covers |
|---|---|
| `odoo-guidelines` | module structure, manifest, Python/ORM, fields, controllers, XML views, QWeb reports, access rights, performance, tests, stable branches |
| `odoo-security` | access control, `sudo`, SQL and domain injection, public methods, routes and CSRF, XSS, file access, deserialization |
| `odoo-review` | the two-pass review process, mapping changed files to guidelines, stable vs master, version traps |
| `odoo-web-guidelines` | JavaScript, Owl templates and SCSS under `static/src/` |

- Source: <https://github.com/odoo/odoo/tree/20.0/skills>
- Ref: branch `20.0`, commit `299075f17026` (2026-10-28)
- License: LGPL-3.0, see `ODOO-LICENSE.txt`

## Why `odoo-git` is not installed

The upstream set also ships `odoo-git`, which documents Odoo core's
`[TAG] scope: summary` commit format and the branch and pull-request rules of
the `odoo/odoo` repository. Core Odoo uses conventional commits
(`feat(panel): ...`), so loading that skill here would produce the wrong
history. It is neither copied nor linked.

## Scope in this repository

- `odoo-guidelines` applies to every file under
  `projects/<project>/odoo/addons/<module>/`.
- `odoo-web-guidelines` only applies if an addon ships `static/src/`.
  Generated frontends are React under `frontend/`, not Owl; for those use
  `odoo-frontend`.
- `odoo-review` and `odoo-security` apply to any addon change, including
  reviewing generated modules.

## Syncing

```bash
base=https://raw.githubusercontent.com/odoo/odoo/20.0/skills
for f in \
  odoo-guidelines/SKILL.md odoo-guidelines/AUTHORING.md \
  odoo-guidelines/guidelines/comments.md odoo-guidelines/guidelines/controllers.md \
  odoo-guidelines/guidelines/fields.md odoo-guidelines/guidelines/manifest.md \
  odoo-guidelines/guidelines/module_structure.md odoo-guidelines/guidelines/orm.md \
  odoo-guidelines/guidelines/performance.md odoo-guidelines/guidelines/python.md \
  odoo-guidelines/guidelines/reports.md odoo-guidelines/guidelines/security.md \
  odoo-guidelines/guidelines/stable.md odoo-guidelines/guidelines/tests.md \
  odoo-guidelines/guidelines/xml.md \
  odoo-review/SKILL.md odoo-security/SKILL.md \
  odoo-web-guidelines/SKILL.md odoo-web-guidelines/AUTHORING.md \
  odoo-web-guidelines/guidelines/assets.md odoo-web-guidelines/guidelines/javascript.md \
  odoo-web-guidelines/guidelines/scss.md; do
  mkdir -p "skills/$(dirname "$f")"
  curl -fsS "$base/$f" -o "skills/$f"
done
```

Update the ref above when you sync. Do not edit the vendored files in place:
changes are lost on the next sync. Core Odoo specifics belong in
`odoo-module`, `odoo-frontend` and `odoo-deploy`, which link to the guideline
sections instead of copying them.
