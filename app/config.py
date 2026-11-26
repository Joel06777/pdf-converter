"""Configuración por variables de entorno (ver .env.example)."""
from __future__ import annotations

import os
from pathlib import Path


class Settings:
    storage_dir = Path(os.getenv("STORAGE_DIR", "/data/jobs"))
    redis_url = os.getenv("REDIS_URL", "")  # vacío = modo "inline" (sin cola, para desarrollo)
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "50"))
    max_pages = int(os.getenv("MAX_PAGES", "200"))
    job_ttl_minutes = int(os.getenv("JOB_TTL_MINUTES", "60"))
    allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
    api_key = os.getenv("API_KEY", "")  # si se define, el sitio web debe enviarla en X-API-Key
    download_secret = os.getenv("DOWNLOAD_SECRET", "")  # si se define, las descargas exigen enlace firmado
    upload_secret = os.getenv("UPLOAD_SECRET", "")  # si se define, habilita la subida directa con token firmado
    upload_token_ttl_seconds = int(os.getenv("UPLOAD_TOKEN_TTL_SECONDS", "300"))  # validez del token de subida (5 min)
    rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "60"))
    ocr_lang = os.getenv("OCR_LANG", "spa+eng")
    task_time_limit = int(os.getenv("TASK_TIME_LIMIT", "600"))
    # Tope de cola: nº máximo de trabajos en queued/processing; por encima, la
    # API responde 503 "Estamos con mucha demanda..." (ver app/main.py).
    max_queue_jobs = int(os.getenv("MAX_QUEUE_JOBS", "50"))
    # Máximo de páginas con OCR por trabajo: el OCR (Tesseract a 300 dpi) es
    # el paso más caro; por encima, el trabajo termina en error con un mensaje
    # claro (ver app/processing.py). El convertidor aplica OCR por página solo
    # cuando la página es un escaneo sin capa de texto.
    max_ocr_pages = int(os.getenv("MAX_OCR_PAGES", "20"))


settings = Settings()
