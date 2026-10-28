"""Scheduled backups for environments and the control plane."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import select

from .config import Settings
from .metrics import record_backup_success
from .models import Environment, Project
from .providers.base import EnvironmentProvider, ProviderError
from .services import build_spec

logger = logging.getLogger(__name__)

SCHEDULED_PREFIX = "scheduled-"
CONTROL_PREFIX = "control-"
CONTROL_DIR = "control-plane"


def prune(paths: list[Path], *, retention_days: int, now: datetime) -> list[Path]:
    """Delete files older than the retention window."""
    cutoff = now - timedelta(days=retention_days)
    removed: list[Path] = []
    for path in paths:
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if modified >= cutoff:
            continue
        try:
            path.unlink()
        except OSError:
            logger.warning("could not prune %s", path)
            continue
        removed.append(path)
    return removed


def prune_backups(settings: Settings, *, now: datetime) -> list[Path]:
    removed = prune(
        list(settings.backups_dir.rglob(f"{SCHEDULED_PREFIX}*.sql")),
        retention_days=settings.core_backup_retention_days,
        now=now,
    )
    removed += prune(
        list((settings.backups_dir / CONTROL_DIR).glob(f"{CONTROL_PREFIX}*.db")),
        retention_days=settings.core_backup_retention_days,
        now=now,
    )
    return removed


def backup_control_plane(settings: Settings, *, now: datetime) -> Path | None:
    """Consistent copy of the SQLite control plane (projects, users, audit)."""
    source = settings.core_data_dir / "core.db"
    if not source.is_file():
        return None
    destination = (
        settings.backups_dir
        / CONTROL_DIR
        / f"{CONTROL_PREFIX}{now.strftime('%Y%m%dT%H%M%S')}.db"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    return destination


def mirror_offsite(
    settings: Settings, created: list[Path], *, now: datetime
) -> list[Path]:
    """Copy fresh dumps to the mounted offsite path and prune the mirror."""
    root = settings.core_backup_offsite_dir
    if root is None:
        return []
    copied: list[Path] = []
    for source in created:
        try:
            relative = source.relative_to(settings.backups_dir)
        except ValueError:
            continue
        destination = root / relative
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        except OSError:
            logger.warning("could not mirror %s offsite", source)
            continue
        copied.append(destination)
    prune(
        list(root.rglob(f"{SCHEDULED_PREFIX}*.sql")),
        retention_days=settings.core_backup_retention_days,
        now=now,
    )
    prune(
        list((root / CONTROL_DIR).glob(f"{CONTROL_PREFIX}*.db")),
        retention_days=settings.core_backup_retention_days,
        now=now,
    )
    return copied


def run_backups_once(
    settings: Settings,
    session_factory: Any,
    provider: EnvironmentProvider,
    *,
    now: datetime | None = None,
) -> list[Path]:
    """Dump every deployed environment, copy the control plane and prune."""
    moment = now or datetime.now(UTC)
    stamp = moment.strftime("%Y%m%dT%H%M%S")
    created: list[Path] = []

    with session_factory() as session:
        projects = session.exec(select(Project)).all()
        for project in projects:
            environments = session.exec(
                select(Environment).where(Environment.project_id == project.id)
            ).all()
            for environment in environments:
                spec = build_spec(settings, project, environment)
                if not spec.compose_file.is_file():
                    continue
                destination = (
                    settings.backups_dir
                    / f"{project.name}-{environment.stage}"
                    / f"{SCHEDULED_PREFIX}{stamp}.sql"
                )
                try:
                    created.append(provider.backup(spec, destination))
                except ProviderError as exc:
                    logger.warning(
                        "scheduled backup failed for %s/%s: %s",
                        project.name,
                        environment.stage,
                        exc.message,
                    )
                    continue
                record_backup_success(project.name, environment.stage, moment.timestamp())

    control = backup_control_plane(settings, now=moment)
    if control is not None:
        created.append(control)
    mirror_offsite(settings, created, now=moment)
    prune_backups(settings, now=moment)
    return created


async def backup_loop(
    settings: Settings,
    session_factory: Any,
    provider: EnvironmentProvider,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Run the scheduled backups forever, once per configured interval."""
    interval = settings.core_backup_interval_hours * 3600
    while True:
        await sleep(interval)
        try:
            await asyncio.to_thread(run_backups_once, settings, session_factory, provider)
        except Exception:  # noqa: BLE001 - the loop must survive a bad night
            logger.exception("scheduled backups failed")
