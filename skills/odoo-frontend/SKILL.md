---
name: odoo-frontend
description: >-
  Build or modify a Kizuku frontend against the declarative BFF: resources
  in backend.yaml, the generated TypeScript SDK, login and JWT, list and form
  screens, error states and i18n. Use for files under
  projects/<project>/frontend/.
---

# Odoo frontend

## The contract

```
browser -> frontend nginx -> gateway (BFF) -> Odoo JSON-2
```

- The browser never talks to Odoo and never sees Odoo credentials. The gateway
  holds the API key and calls Odoo server-side.
- The gateway exposes only the resources, fields, operations and domains
  declared in `projects/<project>/backend.yaml`.
- On a deployed environment, `GET /openapi.json` is the live contract.

## backend.yaml

```yaml
auth:
  mode: jwt
  jwt_secret: ${GATEWAY_JWT_SECRET}
  issuer: core-odoo
resources:
  - name: appointments
    model: salon.appointment
    fields: [name, partner_id, scheduled_at, state]
    operations: [list, read, create, update, delete]
    domain: []
    search_fields: [name]
```

Add a resource with the generator; it edits `backend.yaml` and preserves the
rest of the file:

```bash
core-odoo generate resource <project> appointments \
  --model salon.appointment \
  --fields name,partner_id,scheduled_at,state \
  --search-fields name
```

Then deploy: the gateway rebuilds its routes from the contract.

## Endpoints the gateway generates

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/login` | `{login, password}` returns `{access_token}` |
| `GET` | `/api/<resource>` | `limit` (1-200, default 20), `offset`, `order`, `q` |
| `GET` | `/api/<resource>/<id>` | 404 `record not found` |
| `POST` | `/api/<resource>` | 201 `{id}` |
| `PATCH` | `/api/<resource>/<id>` | partial update |
| `DELETE` | `/api/<resource>/<id>` | `{deleted: true, id}` |

`q` searches the declared `search_fields`; `order` only accepts declared
fields. Undeclared fields are rejected, so do not send them "just in case".

Status codes to handle separately:

| Code | Meaning | UI |
|---|---|---|
| 400 | unknown field, search disabled, invalid order | show the message |
| 401 | missing or expired token | clear it and go to login |
| 403 | Odoo ACL denies the record | "no permission" state |
| 404 | record gone | remove it from the list |
| 405 | operation not declared | hide the action instead |
| 422 | payload does not match the schema | show the field error |

## SDK

```bash
core-odoo generate sdk <project> --stage dev \
  --output frontend/src/api.generated.ts --force
```

It exports `login`, `apiRequest`, one interface per resource (`Client`,
`ClientInput`, ...) and typed clients (`api.clients.list(token)`,
`api.clients.create(token, values)`, ...). Regenerate after every
`backend.yaml` change and never edit generated files by hand.

`core-odoo generate frontend <project> --stage dev` writes a working login +
CRUD app (including the SDK) for a new project; use it as the starting point
instead of writing auth again.

## Screens

- Keep the token in `localStorage` (the generated app uses `core_odoo_token`)
  and pass it through `apiRequest`; never in a query string.
- 401 means "session expired": clear the token and render the login screen, do
  not retry in a loop.
- Treat loading, empty and error as three separate states. A failed request
  must not look like an empty table.
- Build forms from the declared fields and send only those fields.
- Odoo stores datetimes in UTC: send ISO strings and format for display.
- Paginate with `limit`/`offset` and keep search in the URL when it matters.
- Copy follows `AGENTS.md`: neutral Spanish with tuteo, or US English.

## Verify

1. `core-odoo check <project> --frontend` (type-check and build).
2. Deploy dev and open `http://<project>-dev.core-odoo.<suffix>`.
3. Without a token, `/api/<resource>` answers 401.
4. Login, list, create, edit and delete through the UI.
5. The browser network tab shows only frontend and gateway calls, never Odoo.

## Never

- No Odoo URL, database name or API key in frontend code, env vars or build
  args.
- No direct `/json/2` calls from the browser.
- No endpoint outside `backend.yaml`: extend the contract and deploy.
- No second authentication stack next to the gateway.
