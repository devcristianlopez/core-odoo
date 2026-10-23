"""Project source paths used by generators and checks."""

from __future__ import annotations

from pathlib import Path

from .errors import CliError
from .i18n import t
from .settings import RuntimeSettings


def projects_root(settings: RuntimeSettings) -> Path:
    raw = settings.values.get("CORE_PROJECTS_DIR", "./projects")
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (settings.repo_root / path).resolve()


def project_dir(settings: RuntimeSettings, project: str) -> Path:
    root = projects_root(settings)
    path = root / project
    if not path.is_dir():
        raise CliError(
            t("error.project_missing", project=project, projects=str(root)),
            code="project_missing",
        )
    return path
