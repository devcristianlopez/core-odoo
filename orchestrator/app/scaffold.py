"""Project scaffolding helpers.

Sprint 1 uses local directories as project sources (``CORE_PROJECTS_DIR``).
A project always gets ``odoo/addons`` and a ``frontend`` build context so the
compose renderer can bind-mount / build it deterministically.

A project starts **empty** (``template="empty"``): just ``odoo/addons`` and a
frontend context. The first module comes from the generator, so the project name
and the module name never collide.

Templates are optional and come in two flavours:

- ``odoo-module`` — an Odoo addon skeleton with ``__MODULE__`` /
  ``__MODULE_TITLE__`` placeholders. It is installed inside the project's addons
  directory (``odoo/addons/<slug>``) because that is the only directory the
  provider mounts into Odoo.
- plain project templates — copied verbatim to the project root.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .config import Settings

_EMPTY_TEMPLATES = {"", "empty", "none"}
_MANIFEST_FILENAME = "__manifest__.py"
_MODULE_TOKEN = "__MODULE__"
_MODULE_TITLE_TOKEN = "__MODULE_TITLE__"
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9_]")
_SLUG_SEPARATORS = re.compile(r"_+")
_TITLE_SEPARATORS = re.compile(r"[^A-Za-z0-9]+")

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
    <title>Kizuku</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 0; display: grid;
             place-items: center; min-height: 100vh; background: #0f172a; color: #e2e8f0; }
      main { text-align: center; }
      code { background: #1e293b; padding: .2rem .4rem; border-radius: .25rem; }
    </style>
  </head>
  <body>
    <main>
      <h1>Kizuku environment</h1>
      <p>This is the placeholder frontend. Replace <code>projects/&lt;name&gt;/frontend</code>.</p>
    </main>
  </body>
</html>
"""


def ensure_project_layout(settings: Settings, name: str, template: str = "empty") -> Path:
    """Create the minimum project tree required by the Docker provider."""
    project_dir = settings.core_projects_dir / name
    source = None if template.strip().lower() in _EMPTY_TEMPLATES else _resolve_template(
        settings, template
    )

    if source is not None and (source / _MANIFEST_FILENAME).is_file():
        _install_module_template(project_dir, source, name)
    elif not project_dir.exists():
        if source is not None:
            shutil.copytree(source, project_dir)
        else:
            project_dir.mkdir(parents=True)

    (project_dir / "odoo" / "addons").mkdir(parents=True, exist_ok=True)
    _ensure_frontend(settings, project_dir / "frontend")
    _adopt_ownership(project_dir, settings.core_projects_dir)
    return project_dir


def _adopt_ownership(path: Path, reference: Path) -> None:
    """Hand ``path`` and everything below it to the owner of ``reference``.

    The orchestrator runs as root inside its container while the projects
    directory is a bind mount owned by the host user. Files created here would
    otherwise be root-owned and uneditable from the host, so the tree is
    re-owned to match the projects root (or its parent when the root is not
    there yet).

    Ownership is a convenience, never a deploy precondition: a failed ``chown``
    must not abort a deploy, so ``OSError`` is swallowed per entry. Entries that
    already carry the reference uid/gid are left alone, which makes redeploys
    cheap on an already adopted tree. The walk is *not* skipped when only
    ``path`` matches, because a module directory installed as root below a
    correctly owned project root would silently keep the wrong owner.
    """
    if os.geteuid() != 0:
        return

    owner = _reference_owner(reference)
    if owner is None:
        return

    uid, gid = owner
    for current, _dirnames, filenames in os.walk(path):
        _chown(Path(current), uid, gid)
        for filename in filenames:
            _chown(Path(current) / filename, uid, gid)


def _reference_owner(reference: Path) -> tuple[int, int] | None:
    """Return the uid/gid that ``path`` should be handed to, if any."""
    for candidate in (reference, reference.parent):
        try:
            stat = candidate.stat()
        except OSError:
            continue
        return stat.st_uid, stat.st_gid
    return None


def _chown(path: Path, uid: int, gid: int) -> None:
    """Give ``path`` to ``uid``/``gid`` unless it already belongs to them."""
    try:
        current = path.lstat()
        if current.st_uid == uid and current.st_gid == gid:
            return
        os.chown(path, uid, gid, follow_symlinks=False)
    except OSError:
        return


def _resolve_template(settings: Settings, template: str) -> Path | None:
    """Return the template directory, or ``None`` when it is missing or unsafe."""
    templates_root = settings.core_templates_dir.resolve()
    source = (settings.core_templates_dir / template).resolve()
    if source.is_dir() and source.is_relative_to(templates_root):
        return source
    return None


def _module_slug(name: str) -> str:
    """Convert a project name into an Odoo technical module name."""
    normalized = _SLUG_SEPARATORS.sub("_", _NON_SLUG_CHARS.sub("_", name.lower()))
    return normalized.strip("_") or "module"


def _module_title(name: str) -> str:
    """Convert a project name into a human-readable title (``my-app`` → ``My App``)."""
    words = [word for word in _TITLE_SEPARATORS.split(name) if word]
    return " ".join(word[:1].upper() + word[1:] for word in words) or name


def _substitute_placeholders(module_dir: Path, *, slug: str, title: str) -> None:
    """Replace the module placeholders in every UTF-8 file of the new module."""
    for path in module_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rendered = text.replace(_MODULE_TITLE_TOKEN, title).replace(_MODULE_TOKEN, slug)
        if rendered != text:
            path.write_text(rendered, encoding="utf-8")


def _install_module_template(project_dir: Path, source: Path, name: str) -> None:
    """Copy a module template into ``<project>/odoo/addons/<slug>``.

    An existing module directory is never touched: generated code belongs to
    the developer, and re-running the layout must stay idempotent.
    """
    slug = _module_slug(name)
    module_dir = project_dir / "odoo" / "addons" / slug
    if module_dir.exists():
        return

    module_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, module_dir)
    _substitute_placeholders(module_dir, slug=slug, title=_module_title(name))


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
