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
    rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "60"))
    ocr_lang = os.getenv("OCR_LANG", "spa+eng")
    task_time_limit = int(os.getenv("TASK_TIME_LIMIT", "600"))


settings = Settings()
