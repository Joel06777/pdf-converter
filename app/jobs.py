"""Estado de los trabajos en disco (compartido entre API y workers por un volumen)."""
from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import time
import uuid
from pathlib import Path

from .config import settings


def job_dir(job_id: str) -> Path:
    if not job_id.isalnum():
        raise ValueError("id inválido")
    return settings.storage_dir / job_id


def new_job(target: str, filename: str) -> str:
    job_id = uuid.uuid4().hex
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    write_state(job_id, status="queued", target=target, filename=filename, created=time.time())
    return job_id


def write_state(job_id: str, **fields) -> dict:
    path = job_dir(job_id) / "state.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    state.update(fields)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(path)  # escritura atómica
    return state


def read_state(job_id: str) -> dict | None:
    try:
        return json.loads((job_dir(job_id) / "state.json").read_text())
    except (FileNotFoundError, ValueError):
        return None


def is_cancelled(job_id: str) -> bool:
    """¿Pidió el usuario cancelar este trabajo? (lo consultan los conversores)."""
    state = read_state(job_id)
    return bool(state and state.get("status") == "cancelled")


def download_token(job_id: str, ttl_seconds: int = 900) -> str:
    """Enlace firmado temporal: '<expiración>.<firma HMAC>' (15 min por defecto)."""
    exp = int(time.time()) + ttl_seconds
    sig = hmac.new(settings.download_secret.encode(), f"{job_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{sig}"


def verify_download_token(job_id: str, token: str) -> bool:
    """Valida un enlace firmado. False si falta, venció o la firma no coincide."""
    if not settings.download_secret or not token or "." not in token:
        return False
    exp, _, sig = token.partition(".")
    try:
        if int(exp) < time.time():
            return False
    except ValueError:
        return False
    expected = hmac.new(settings.download_secret.encode(), f"{job_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(expected, sig)


def cleanup_expired() -> int:
    """Borra trabajos más viejos que JOB_TTL_MINUTES (privacidad: los archivos no se conservan)."""
    removed = 0
    limit = time.time() - settings.job_ttl_minutes * 60
    if not settings.storage_dir.exists():
        return 0
    for d in settings.storage_dir.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        except OSError:
            pass
    return removed
