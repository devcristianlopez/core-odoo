# Frontend starter

Minimal Vite + React + TypeScript application for a Kizuku environment.

- License: Apache-2.0
- Node 24 build stage → `nginx:1.30.6-alpine` runtime
- `/api/*` is proxied by nginx to `http://gateway:8000` (BFF contract §6)
- SPA fallback (`try_files … /index.html`)
- `GET /healthz` for container health checks

## Local development

```bash
npm install
npm run dev        # http://localhost:5173, /api proxied to localhost:8000
```

In development, run the gateway locally on port 8000 (or change the proxy target
in `vite.config.ts`).

## Build

```bash
npm run build      # tsc --noEmit && vite build
docker build -t my-frontend .
```

The environment Compose template builds this directory automatically:

```yaml
frontend:
  build:
    context: ${CORE_PROJECT_DIR}/frontend
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VITE_RESOURCE` | `contacts` | Resource declared in `backend.yaml` |
| `VITE_API_BASE` | *(empty)* | Optional absolute gateway URL |

Keep all HTTP calls in `src/api.ts`: the gateway is the only backend the browser
is allowed to talk to. Never call Odoo directly.

## Layout

```
src/
├── api.ts          # typed fetch wrapper + resource client
├── App.tsx         # list + create example
├── main.tsx
└── styles.css
```
