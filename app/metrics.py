"""Métricas Prometheus calculadas desde el estado en disco (replicas seguras).

Los trabajos viven en archivos state.json dentro de STORAGE_DIR, un volumen
compartido entre API y workers: contar ahí funciona con varias réplicas, sin
estado en memoria de la API.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from .config import settings
from .jobs import read_state


def collect() -> dict:
    """Devuelve contadores por estado, duraciones y espacio en disco."""
    counts: dict[str, int] = {}
    durations: list[float] = []
    if settings.storage_dir.exists():
        for d in settings.storage_dir.iterdir():
            if not d.is_dir():
                continue
            state = read_state(d.name)
            if not state:
                continue
            status = state.get("status", "?")
            counts[status] = counts.get(status, 0) + 1
            created, finished = state.get("created"), state.get("finished_at")
            if status in ("done", "error", "cancelled") and created and finished:
                durations.append(max(0.0, finished - created))
    usage = shutil.disk_usage(settings.storage_dir) if settings.storage_dir.exists() else None
    return {
        "counts": counts,
        "durations": durations,
        "disk_free": usage.free if usage else 0,
        "disk_total": usage.total if usage else 0,
    }


def render_prometheus(m: dict) -> str:
    lines = [
        "# HELP converter_jobs_total Trabajos por estado",
        "# TYPE converter_jobs_total gauge",
    ]
    for status in ("queued", "processing", "done", "error", "cancelled"):
        lines.append(f'converter_jobs_total{{status="{status}"}} {m["counts"].get(status, 0)}')
    total_dur = sum(m["durations"])
    lines += [
        "# HELP converter_job_duration_seconds_sum Suma de duraciones de trabajos terminados",
        "# TYPE converter_job_duration_seconds_sum gauge",
        f"converter_job_duration_seconds_sum {total_dur:.3f}",
        "# HELP converter_job_duration_seconds_count Trabajos terminados medidos",
        "# TYPE converter_job_duration_seconds_count gauge",
        f"converter_job_duration_seconds_count {len(m['durations'])}",
        "# HELP converter_disk_free_bytes Espacio libre en el volumen de trabajos",
        "# TYPE converter_disk_free_bytes gauge",
        f"converter_disk_free_bytes {m['disk_free']}",
        "# HELP converter_disk_total_bytes Espacio total del volumen de trabajos",
        "# TYPE converter_disk_total_bytes gauge",
        f"converter_disk_total_bytes {m['disk_total']}",
    ]
    return "\n".join(lines) + "\n"
