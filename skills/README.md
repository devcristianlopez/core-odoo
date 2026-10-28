# Skills

On-demand playbooks for agents working in this repository. They are plain
Markdown with YAML frontmatter and are loaded only when a task matches, so they
cost nothing until an agent needs them.

## Layout

```
skills/<skill-id>/SKILL.md   source of truth
.opencode/skills/<id>        symlink for OpenCode
.agents/skills/<id>          symlink for other harnesses
.claude/skills/<id>          symlink for Claude Code
```

A skill may ship extra files (guidelines, templates); every link is relative to
its `SKILL.md`. Run `python3 scripts/check_skills.py` after editing: it checks
the frontmatter, the directory name, the symlinks and every relative link.

## Which skill to load

| Task | Skill |
|---|---|
| add or change models, fields, views, ACL, tests in an addon | `odoo-module` + `odoo-guidelines` |
| audit an addon for `sudo`, SQL, routes, XSS or ACL mistakes | `odoo-security` |
| review a diff, commit or module | `odoo-review` (+ `odoo-guidelines`, `odoo-security`, and `odoo-web-guidelines` for `static/`) |
| build screens against the BFF | `odoo-frontend` |
| deploy, promote, roll back or read logs | `odoo-deploy` |
| Odoo core JavaScript, Owl templates or SCSS | `odoo-web-guidelines` |

The platform rules (golden path, boundaries, copy and language) live in
`AGENTS.md`; the skills assume them.

## Upstream set

`odoo-guidelines`, `odoo-review`, `odoo-security` and `odoo-web-guidelines` are
copied verbatim from Odoo 20 and keep Odoo's LGPL-3.0 license
(`ODOO-LICENSE.txt`); the rest of the repository stays Apache-2.0. Keep them
untouched; `UPSTREAM.md` records the ref and the sync command. Kizuku
specifics live in `odoo-module`, `odoo-frontend` and `odoo-deploy`.

## Adding a skill

1. Create `skills/<id>/SKILL.md` with `name` equal to the directory and a
   `description` that says **when** to use it.
2. Link it in all three harnesses:
   `ln -s ../../skills/<id> .opencode/skills/<id>` (same for `.agents/skills`
   and `.claude/skills`).
3. Add a row to the table above.
4. Run `python3 scripts/check_skills.py`.
