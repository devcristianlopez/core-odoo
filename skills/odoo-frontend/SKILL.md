---
name: odoo-frontend
description: Build or modify a Core Odoo frontend against the declarative BFF. Use for React/Vue/Svelte screens, login flows and CRUD UI that must never call Odoo directly.
---

# Odoo frontend

## Contract

Browser → frontend nginx → gateway → Odoo.

- The gateway exposes only `backend.yaml` resources/fields/operations.
- Login: `POST /auth/login` with `{login, password}` → JWT.
- Protect requests with `Authorization: Bearer <token>`.
- Nginx must proxy `/api/` and `/auth/` to `gateway:8000`.

## Workflow

1. Read the project `backend.yaml`.
2. For each resource, use only declared fields/operations.
3. Use the generated OpenAPI at `/openapi.json` as the source of truth.
4. Handle 401 (expired token), 403, 404 and 422 as distinct states.
5. Never send Odoo credentials or API keys to the browser.

## Generate a frontend

For a new project, generate a login + generic CRUD app (includes the SDK):

```bash
core-odoo generate frontend <project> --stage dev
```

For an existing custom frontend, generate only the typed SDK:

```bash
core-odoo generate sdk <project> --stage dev \
  --output frontend/src/api.generated.ts --force
```

The SDK reads `backend.yaml`, resolves field types from the running Odoo
catalogue when available, and exports `login`, `apiRequest`, resource types and
resource clients. Regenerate it when the contract changes. `generate frontend`
writes `src/schema.generated.ts`, `src/api.generated.ts` and a generic
login/table/form app.
