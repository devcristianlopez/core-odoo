"""Project scaffolding helpers.

Sprint 1 uses local directories as project sources (``CORE_PROJECTS_DIR``).
A project always gets ``odoo/addons`` and a ``frontend`` build context so the
compose renderer can bind-mount / build it deterministically.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import Settings

_FALLBACK_DOCKERFILE = """FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
"""

_FALLBACK_NGINX = """server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://gateway:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /auth/ {
        proxy_pass http://gateway:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location = /health {
        proxy_pass http://gateway:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location = /openapi.json {
        proxy_pass http://gateway:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location = /healthz {
        access_log off;
        add_header Content-Type text/plain;
        return 200 "ok\\n";
    }
}
"""

_FALLBACK_INDEX = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Core Odoo</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 0; display: grid;
             place-items: center; min-height: 100vh; background: #0f172a; color: #e2e8f0; }
      main { text-align: center; }
      code { background: #1e293b; padding: .2rem .4rem; border-radius: .25rem; }
    </style>
  </head>
  <body>
    <main>
      <h1>Core Odoo environment</h1>
      <p>This is the placeholder frontend. Replace <code>projects/&lt;name&gt;/frontend</code>.</p>
    </main>
  </body>
</html>
"""


def ensure_project_layout(settings: Settings, name: str, template: str) -> Path:
    """Create the minimum project tree required by the Docker provider."""
    project_dir = settings.core_projects_dir / name
    if not project_dir.exists():
        templates_root = settings.core_templates_dir.resolve()
        source = (settings.core_templates_dir / template).resolve()
        if source.is_dir() and source.is_relative_to(templates_root):
            shutil.copytree(source, project_dir)
        else:
            project_dir.mkdir(parents=True)

    (project_dir / "odoo" / "addons").mkdir(parents=True, exist_ok=True)
    _ensure_frontend(settings, project_dir / "frontend")
    return project_dir


def _ensure_frontend(settings: Settings, frontend_dir: Path) -> None:
    if (frontend_dir / "Dockerfile").is_file():
        return

    starter = settings.core_templates_dir / "frontend-starter"
    if (starter / "Dockerfile").is_file():
        frontend_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(starter, frontend_dir, dirs_exist_ok=True)
        return

    frontend_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dir / "Dockerfile").write_text(_FALLBACK_DOCKERFILE, encoding="utf-8")
    (frontend_dir / "nginx.conf").write_text(_FALLBACK_NGINX, encoding="utf-8")
    (frontend_dir / "index.html").write_text(_FALLBACK_INDEX, encoding="utf-8")
