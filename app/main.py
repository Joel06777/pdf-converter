"""API HTTP del convertidor. El sitio web (Vercel) sube el PDF, consulta el estado y descarga."""
from __future__ import annotations

import shutil
import time

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from . import jobs
from .config import settings
from .converters import TARGETS
from .jsonlog import logger
from .metrics import collect, render_prometheus
from .processing import run_job

app = FastAPI(title="Convertidor PDF", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_redis = None
_hits: dict[str, list[float]] = {}  # respaldo de límite de uso en modo inline


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _check_rate_limit(request: Request) -> None:
    """Límite de peticiones por IP y hora (Redis si hay, memoria si no).

    Se usa tanto en las rutas con API key (check_access) como en la subida
    directa, que no lleva API key pero sí token firmado.
    """
    ip, limit = _client_ip(request), settings.rate_limit_per_hour
    if settings.redis_url:
        global _redis
        if _redis is None:
            import redis

            _redis = redis.Redis.from_url(settings.redis_url)
        key = f"rl:{ip}:{int(time.time() // 3600)}"
        n = _redis.incr(key)
        if n == 1:
            _redis.expire(key, 3700)
        if n > limit:
            raise HTTPException(429, "Demasiadas conversiones por hora. Intenta más tarde.")
    else:
        now = time.time()
        hits = [t for t in _hits.get(ip, []) if now - t < 3600]
        if len(hits) >= limit:
            raise HTTPException(429, "Demasiadas conversiones por hora. Intenta más tarde.")
        hits.append(now)
        _hits[ip] = hits


def _check_queue_capacity(extra: int = 0) -> None:
    """Tope de cola: si hay demasiados trabajos en curso, rechazar con 503.

    `extra` cuenta los trabajos que esta misma petición va a crear
    (convert-many). Responde 503 con mensaje en español, sin consumir el
    token de subida ni leer el archivo, para que el cliente pueda reintentar.
    """
    if jobs.count_active_jobs() + extra >= settings.max_queue_jobs:
        raise HTTPException(503, "Estamos con mucha demanda, intenta en unos minutos")


# Anti-abuso (opcional, no implementado): Cloudflare Turnstile es gratis
# (plan Free: 0 $/mes, retos ilimitados, hasta 20 widgets, sin tarjeta —
# verificado en cloudflare.com/products/turnstile el 26 nov 2026). Si el
# abuso persiste pese al límite por IP y al tope de cola, el camino es
# añadir el widget de Turnstile en web-example/ y verificar el token en el
# servidor contra https://challenges.cloudflare.com/turnstile/v0/siteverify
# antes de aceptar el trabajo. No se activa aquí: exige cuenta de
# Cloudflare y claves (TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY).


def check_access(request: Request, x_api_key: str = Header(default="")):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(401, "API key inválida.")
    _check_rate_limit(request)


def _download_url(job_id: str) -> str:
    """URL de descarga: firmada (15 min) si hay DOWNLOAD_SECRET, directa si no."""
    if settings.download_secret:
        return f"/api/v1/jobs/{job_id}/download?token={jobs.download_token(job_id)}"
    return f"/api/v1/jobs/{job_id}/download"


def _validate_pdf(data: bytes) -> None:
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"El archivo supera {settings.max_upload_mb} MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(400, "El archivo no es un PDF válido.")


def _start_job(background: BackgroundTasks, data: bytes, filename: str, target: str,
               layout: str = "pages", formulas: bool = True) -> str:
    job_id = jobs.new_job(target, filename)
    jobs.write_state(job_id, layout=layout, formulas=formulas)
    (jobs.job_dir(job_id) / "input.pdf").write_bytes(data)
    if settings.redis_url:
        from .worker import convert_job

        convert_job.delay(job_id)
    else:
        background.add_task(run_job, job_id)
    logger.info("trabajo creado", extra={"job_id": job_id, "target": target, "archivo": filename})
    return job_id


@app.get("/health")
def health():
    """Salud del servicio: Redis (si está configurado) y espacio en disco."""
    redis_ok: bool | None = None
    if settings.redis_url:
        try:
            import redis

            redis_ok = bool(redis.Redis.from_url(settings.redis_url).ping())
        except Exception:
            redis_ok = False
    usage = shutil.disk_usage(settings.storage_dir) if settings.storage_dir.exists() else None
    free_mb = round(usage.free / 1024 / 1024) if usage else 0
    ok = (redis_ok is not False) and free_mb > 100
    return {"ok": ok, "redis": redis_ok, "disco_libre_mb": free_mb}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Métricas Prometheus: trabajos por estado, duración y disco (sin datos del documento)."""
    return render_prometheus(collect())


@app.post("/api/v1/upload-token", dependencies=[Depends(check_access)])
async def create_upload_token_endpoint(request: Request):
    """Token de subida directa: lo pide la función serverless de Vercel con la
    API key (la clave nunca llega al navegador) y el navegador sube el PDF
    directo al backend con ese token (ver POST /api/v1/upload)."""
    if not settings.upload_secret:
        raise HTTPException(503, "La subida directa no está configurada en el servidor (falta UPLOAD_SECRET).")
    try:
        body = await request.json()
    except Exception:
        body = {}
    max_mb = body.get("max_mb") if isinstance(body, dict) else None
    if max_mb is not None:
        try:
            max_mb = int(max_mb)
        except (TypeError, ValueError):
            raise HTTPException(400, "max_mb debe ser un número entero de megabytes.")
    try:
        token = jobs.create_upload_token(max_mb=max_mb)
        payload = jobs.validate_upload_token(token)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {
        "upload_token": token,
        "expires_in": settings.upload_token_ttl_seconds,
        "max_mb": payload["max_mb"],
        "upload_url": "/api/v1/upload",
    }


@app.post("/api/v1/upload", status_code=202)
async def upload_direct(background: BackgroundTasks, request: Request, file: UploadFile = File(...),
                        target: str = Form(...), layout: str = Form("pages"),
                        formulas: bool = Form(True), x_upload_token: str = Header(default="")):
    """Subida directa al backend con token firmado (sin API key).

    El PDF viene directo del navegador, sin pasar por Vercel (límite 4,5 MB).
    El nonce del token solo se consume cuando la subida se acepta, para que
    un reintento de red con el mismo token no falle si la primera petición
    no llegó.
    """
    try:
        payload = jobs.validate_upload_token(x_upload_token)
    except ValueError as exc:
        raise HTTPException(401, str(exc))
    _check_rate_limit(request)
    _check_queue_capacity()
    if target not in TARGETS:
        raise HTTPException(400, f"target debe ser uno de: {', '.join(TARGETS)}")
    if layout not in ("pages", "continuous"):
        raise HTTPException(400, "layout debe ser 'pages' o 'continuous'")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > payload["max_mb"] * 1024 * 1024:
        raise HTTPException(413, f"El archivo supera el máximo de {payload['max_mb']} MB permitido por el token de subida.")
    _validate_pdf(data)
    try:
        jobs.consume_upload_token(x_upload_token)
    except ValueError as exc:
        raise HTTPException(401, str(exc))
    job_id = _start_job(background, data, file.filename or "documento.pdf", target, layout, formulas)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/v1/convert", status_code=202, dependencies=[Depends(check_access)])
async def create_job(background: BackgroundTasks, file: UploadFile = File(...), target: str = Form(...),
                     layout: str = Form("pages"), formulas: bool = Form(True)):
    _check_queue_capacity()
    if target not in TARGETS:
        raise HTTPException(400, f"target debe ser uno de: {', '.join(TARGETS)}")
    if layout not in ("pages", "continuous"):
        raise HTTPException(400, "layout debe ser 'pages' o 'continuous'")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    _validate_pdf(data)
    job_id = _start_job(background, data, file.filename or "documento.pdf", target, layout, formulas)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/v1/convert-many", status_code=202, dependencies=[Depends(check_access)])
async def create_jobs(background: BackgroundTasks, files: list[UploadFile] = File(...),
                      target: str = Form(...), layout: str = Form("pages"),
                      formulas: bool = Form(True)):
    """Subida de varios archivos: crea un trabajo por PDF y devuelve sus ids."""
    _check_queue_capacity(extra=len(files))
    if target not in TARGETS:
        raise HTTPException(400, f"target debe ser uno de: {', '.join(TARGETS)}")
    if layout not in ("pages", "continuous"):
        raise HTTPException(400, "layout debe ser 'pages' o 'continuous'")
    if not files:
        raise HTTPException(400, "Envía al menos un archivo PDF.")
    if len(files) > 20:
        raise HTTPException(400, "Máximo 20 archivos por petición.")
    created = []
    for f in files:
        data = await f.read(settings.max_upload_mb * 1024 * 1024 + 1)
        _validate_pdf(data)
        job_id = _start_job(background, data, f.filename or "documento.pdf", target, layout, formulas)
        created.append({"job_id": job_id, "filename": f.filename or "documento.pdf", "status": "queued"})
    return {"jobs": created}


@app.get("/api/v1/jobs/{job_id}")
def job_status(job_id: str):
    state = jobs.read_state(job_id) if job_id.isalnum() else None
    if not state:
        raise HTTPException(404, "Trabajo no encontrado o expirado.")
    public = {k: state[k] for k in ("status", "target", "error", "info", "pages_done", "pages_total", "progress")
              if k in state}
    public["job_id"] = job_id
    if state.get("status") == "done":
        public["download_url"] = _download_url(job_id)
    return public


@app.get("/api/v1/jobs/{job_id}/progress")
def job_progress(job_id: str):
    """Progreso por página: {pages_done, pages_total, progress (0..1), status}."""
    state = jobs.read_state(job_id) if job_id.isalnum() else None
    if not state:
        raise HTTPException(404, "Trabajo no encontrado o expirado.")
    return {
        "job_id": job_id,
        "status": state.get("status"),
        "pages_done": state.get("pages_done", 0),
        "pages_total": state.get("pages_total", 0),
        "progress": state.get("progress", 0.0),
    }


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Cancela un trabajo en cola o en proceso. El worker lo detiene entre páginas."""
    state = jobs.read_state(job_id) if job_id.isalnum() else None
    if not state:
        raise HTTPException(404, "Trabajo no encontrado o expirado.")
    if state.get("status") in ("done", "error", "cancelled"):
        raise HTTPException(409, f"El trabajo ya está {state.get('status')}; no se puede cancelar.")
    jobs.write_state(job_id, status="cancelled", error="Conversión cancelada por el usuario.",
                     finished_at=time.time())
    logger.info("trabajo cancelado por API", extra={"job_id": job_id})
    return {"job_id": job_id, "status": "cancelled"}


@app.get("/api/v1/jobs/{job_id}/download")
def download(job_id: str, token: str = ""):
    state = jobs.read_state(job_id) if job_id.isalnum() else None
    if not state or state.get("status") != "done":
        raise HTTPException(404, "El archivo aún no está listo o expiró.")
    if settings.download_secret and not jobs.verify_download_token(job_id, token):
        raise HTTPException(401, "Enlace de descarga inválido o vencido. Vuelve a pedir el estado del trabajo.")
    path = jobs.job_dir(job_id) / state["output"]
    ext = path.suffix.lstrip(".")
    stem = state["filename"].rsplit(".", 1)[0] or "documento"
    return FileResponse(path, media_type=MEDIA[ext], filename=f"{stem}.{ext}")
