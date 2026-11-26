"""Logs en JSON (una línea por evento) sin contenido de los documentos.

Solo se registran identificadores (job_id), destino, estado y duraciones. Nunca
el texto ni las cifras del PDF: los logs no deben filtrar datos del usuario.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = {"ts": datetime.now(timezone.utc).isoformat(), "level": record.levelname.lower(),
                 "msg": record.getMessage()}
        for key, value in record.__dict__.items():
            if key not in _STANDARD and not key.startswith("_"):
                event[key] = value
        return json.dumps(event, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("converter")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False
    return root


logger = setup_logging()
