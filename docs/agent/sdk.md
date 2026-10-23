# TypeScript SDK

```bash
core-odoo generate sdk <project> --stage dev \
  --output frontend/src/api.generated.ts --force
```

The generator reads `backend.yaml` and, when the environment is running, the Odoo
catalogue for field types and required flags. It emits:

- `login(login, password)`
- `apiRequest<T>(path, options)`
- one interface + input type per BFF resource
- resource clients with the operations declared in `backend.yaml`
- an `api` object grouping the clients

If the catalogue is unavailable, field types fall back to `unknown`; the SDK is
still generated so frontend work can start offline. Regenerate after changing
`backend.yaml`.

The SDK does not replace the gateway: it is a typed client for the browser path
`nginx → /api|/auth → gateway → Odoo`.
