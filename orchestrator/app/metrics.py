"""Minimal Prometheus metrics for the control plane.

The Sprint 1 process is single-worker, so plain in-process counters are enough.
The exposition is hand-written to avoid pulling a client library into the
container image; the alert rules only need these three families.
"""

from __future__ import annotations

import threading
from collections import Counter

_lock = threading.Lock()
_deploy_total: Counter[tuple[str, str, str]] = Counter()
_backup_last_success: dict[tuple[str, str], float] = {}
_cron_lag: dict[tuple[str, str, str], float] = {}


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(**values: str) -> str:
    if not values:
        return ""
    inner = ",".join(f'{key}="{_esc(value)}"' for key, value in values.items())
    return "{" + inner + "}"


def record_deploy(project: str, stage: str, status: str) -> None:
    with _lock:
        _deploy_total[(project, stage, status)] += 1


def record_backup_success(project: str, stage: str, timestamp: float) -> None:
    with _lock:
        _backup_last_success[(project, stage)] = timestamp


def record_cron_lag(project: str, stage: str, cron: str, seconds: float) -> None:
    with _lock:
        _cron_lag[(project, stage, cron)] = seconds


def render(environment_count: int) -> str:
    lines = [
        "# HELP core_odoo_up Control plane is running.",
        "# TYPE core_odoo_up gauge",
        "core_odoo_up 1",
        "# HELP core_odoo_environments_total Number of managed environments.",
        "# TYPE core_odoo_environments_total gauge",
        f"core_odoo_environments_total {int(environment_count)}",
        "# HELP core_deploy_total Environment deploy attempts by result.",
        "# TYPE core_deploy_total counter",
    ]
    with _lock:
        deploys = dict(_deploy_total)
        backups = dict(_backup_last_success)
        crons = dict(_cron_lag)

    for (project, stage, status), value in sorted(deploys.items()):
        labels = _labels(project=project, stage=stage, status=status)
        lines.append(f"core_deploy_total{labels} {value}")

    lines.extend(
        [
            "# HELP core_backup_last_success_timestamp_seconds Last successful backup timestamp.",
            "# TYPE core_backup_last_success_timestamp_seconds gauge",
        ]
    )
    for (project, stage), value in sorted(backups.items()):
        labels = _labels(project=project, stage=stage)
        lines.append(f"core_backup_last_success_timestamp_seconds{labels} {value:.0f}")

    lines.extend(
        [
            "# HELP core_odoo_cron_lag_seconds Seconds since the last successful cron run.",
            "# TYPE core_odoo_cron_lag_seconds gauge",
        ]
    )
    for (project, stage, cron), value in sorted(crons.items()):
        labels = _labels(project=project, stage=stage, cron=cron)
        lines.append(f"core_odoo_cron_lag_seconds{labels} {value:.0f}")

    return "\n".join(lines) + "\n"
