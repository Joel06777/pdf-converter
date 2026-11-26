"""Estado de los trabajos en disco (compartido entre API y workers por un volumen)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
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


# --------------------------------------------------------------------- token de subida
# Subida directa al backend (sin pasar por Vercel, que limita el cuerpo a 4,5 MB):
# la función serverless pide un token con la API key y el navegador sube el PDF
# directo al backend con ese token. El token se crea ANTES de subir el PDF, así
# que no puede llevar job_id: lleva expiración, tamaño máximo, un nonce de un
# solo uso y el tipo "upload". El nonce solo se marca como usado cuando la
# subida se acepta, para que un reintento de red con el mismo token no falle
# si la primera petición no llegó.

_UPLOAD_NONCE_FILE = "upload_tokens.json"


def _upload_nonce_path() -> Path:
    return settings.storage_dir / _UPLOAD_NONCE_FILE


def _redis_client():
    import redis

    return redis.Redis.from_url(settings.redis_url)


def _nonce_is_consumed(nonce: str) -> bool:
    """¿Ya se usó este nonce? (True = el token ya no vale)."""
    if settings.redis_url:
        return bool(_redis_client().exists(f"upload_nonce:{nonce}"))
    path = _upload_nonce_path()
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return False
    exp = data.get(nonce)
    return isinstance(exp, (int, float)) and exp > time.time()


def _nonce_consume(nonce: str, exp: int) -> bool:
    """Marca el nonce como usado. Devuelve False si ya estaba usado."""
    if settings.redis_url:
        ttl = max(1, int(exp - time.time()))
        return bool(_redis_client().set(f"upload_nonce:{nonce}", "1", nx=True, ex=ttl))
    path = _upload_nonce_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    now = time.time()
    data = {n: e for n, e in data.items() if isinstance(e, (int, float)) and e > now}
    if nonce in data:
        return False
    data[nonce] = exp
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(path)  # escritura atómica
    return True


def create_upload_token(max_mb: int | None = None, ttl_seconds: int | None = None) -> str:
    """Crea un token de subida firmado HMAC-SHA256 con UPLOAD_SECRET.

    Formato: base64url(json {typ, exp, max_mb, nonce}) + "." + firma[:32].
    """
    if not settings.upload_secret:
        raise ValueError("La subida directa no está configurada en el servidor (falta UPLOAD_SECRET).")
    ttl = settings.upload_token_ttl_seconds if ttl_seconds is None else int(ttl_seconds)
    mb = settings.max_upload_mb if max_mb is None else min(int(max_mb), settings.max_upload_mb)
    if mb <= 0:
        raise ValueError("El tamaño máximo permitido debe ser mayor que 0 MB.")
    payload = {
        "typ": "upload",
        "exp": int(time.time()) + ttl,
        "max_mb": mb,
        "nonce": secrets.token_urlsafe(24),
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(settings.upload_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{raw}.{sig}"


def validate_upload_token(token: str) -> dict:
    """Valida un token de subida sin consumir el nonce.

    Comprueba firma HMAC, expiración, tipo, max_mb y que el nonce no esté ya
    consumido. Devuelve el payload. Lanza ValueError con mensaje en español.
    """
    if not settings.upload_secret:
        raise ValueError("La subida directa no está configurada en el servidor (falta UPLOAD_SECRET).")
    if not token or token.count(".") != 1:
        raise ValueError("Falta el token de subida o tiene un formato inválido.")
    raw, _, sig = token.partition(".")
    expected = hmac.new(settings.upload_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        raise ValueError("El token de subida es inválido o fue manipulado.")
    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError):
        raise ValueError("El token de subida es inválido o fue manipulado.")
    if not isinstance(payload, dict) or payload.get("typ") != "upload":
        raise ValueError("El token de subida es inválido o fue manipulado.")
    try:
        exp = int(payload["exp"])
        max_mb = int(payload["max_mb"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("El token de subida es inválido o fue manipulado.")
    if exp < time.time():
        raise ValueError("El token de subida caducó. Pide uno nuevo e inténtalo de nuevo.")
    if max_mb <= 0 or max_mb > settings.max_upload_mb:
        raise ValueError("El token de subida no permite este tamaño de archivo.")
    if not isinstance(payload.get("nonce"), str) or not payload["nonce"]:
        raise ValueError("El token de subida es inválido o fue manipulado.")
    if _nonce_is_consumed(payload["nonce"]):
        raise ValueError("El token de subida ya fue usado. Pide uno nuevo.")
    return payload


def consume_upload_token(token: str) -> dict:
    """Valida el token y marca su nonce como usado. Lanza ValueError si no vale."""
    payload = validate_upload_token(token)
    if not _nonce_consume(payload["nonce"], payload["exp"]):
        raise ValueError("El token de subida ya fue usado. Pide uno nuevo.")
    return payload


def count_active_jobs() -> int:
    """Nº de trabajos en estado queued/processing (leen su state.json en disco).

    Lo usa el tope de cola de app/main.py. Incluye trabajos encolados por
    una API caída o un worker caído hasta que los borre cleanup_expired()
    (JOB_TTL_MINUTES); es una aproximación suficiente para proteger la cola.
    No es atómico: dos peticiones simultáneas pueden pasar el tope a la vez.
    """
    if not settings.storage_dir.exists():
        return 0
    n = 0
    for d in settings.storage_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            state = json.loads((d / "state.json").read_text())
        except (FileNotFoundError, ValueError, OSError):
            continue
        if state.get("status") in ("queued", "processing"):
            n += 1
    return n


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
