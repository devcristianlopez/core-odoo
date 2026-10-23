# Generated frontend

For a new project:

```bash
core-odoo generate frontend <project> --stage dev
```

This copies `templates/agent-frontend`, writes:

- `src/schema.generated.ts` from `backend.yaml`,
- `src/api.generated.ts` using the SDK generator,
- a generic `App.tsx` with login, resource tabs, create/edit/delete forms.

The template uses nginx with `/api/` and `/auth/` proxies to the gateway.

Use `--force` only when you intentionally want to replace an existing frontend:
it removes `projects/<project>/frontend` first.

For an existing custom frontend, use only the SDK:

```bash
core-odoo generate sdk <project> --stage dev \
  --output frontend/src/api.generated.ts --force
```

Then validate:

```bash
core-odoo check <project> --catalog --frontend
```
