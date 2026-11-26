"""Ejecuta una conversión (la usan el worker de Celery y el modo inline)."""
from __future__ import annotations

import time
import traceback

import pymupdf

from . import jobs
from .config import settings
from .converters import TARGETS, ConversionCancelled, convert
from .jsonlog import logger


def _has_xfa(doc: pymupdf.Document) -> bool:
    """¿El PDF es un formulario dinámico XFA (no convertible con este motor)?"""
    try:
        _, value = doc.xref_get_key(-1, "Root/AcroForm/XFA")
        return value not in ("null", "[]", "")
    except Exception:
        return False


def run_job(job_id: str) -> None:
    d = jobs.job_dir(job_id)
    state = jobs.read_state(job_id) or {}
    if state.get("status") == "cancelled":
        return  # cancelado antes de empezar
    target = state["target"]
    layout = state.get("layout", "pages")
    formulas = state.get("formulas", True)
    src = str(d / "input.pdf")
    dst = str(d / f"output.{TARGETS[target][0]}")
    started = time.time()
    jobs.write_state(job_id, status="processing", pages_done=0, pages_total=0, progress=0.0)
    try:
        with pymupdf.open(src) as doc:
            if doc.needs_pass:
                raise ValueError("El PDF está protegido con contraseña.")
            if doc.page_count > settings.max_pages:
                raise ValueError(f"El PDF supera el máximo de {settings.max_pages} páginas.")
            if _has_xfa(doc):
                raise ValueError(
                    "El PDF es un formulario dinámico (XFA) y no se puede convertir. "
                    "Guárdalo como PDF normal (imprimir a PDF) e inténtalo de nuevo.")
        info = convert(
            src, dst, target, ocr=True, lang=settings.ocr_lang, layout=layout, formulas=formulas,
            on_progress=lambda n, total: jobs.write_state(
                job_id, pages_done=n, pages_total=total, progress=round(n / total, 4)),
            is_cancelled=lambda: jobs.is_cancelled(job_id),
        )
        jobs.write_state(job_id, status="done", info=info, output=f"output.{TARGETS[target][0]}",
                         finished_at=time.time(), pages_done=info.get("pages", 0),
                         pages_total=info.get("pages", 0), progress=1.0)
        logger.info("trabajo terminado", extra={"job_id": job_id, "target": target,
                                                "duracion_s": round(time.time() - started, 2),
                                                "paginas": info.get("pages")})
    except ConversionCancelled:
        jobs.write_state(job_id, status="cancelled", error="Conversión cancelada por el usuario.",
                         finished_at=time.time())
        logger.info("trabajo cancelado", extra={"job_id": job_id, "target": target})
    except Exception as exc:  # el usuario recibe un mensaje claro, el detalle queda en el log
        traceback.print_exc()
        jobs.write_state(job_id, status="error", error=str(exc) or exc.__class__.__name__,
                         finished_at=time.time())
        logger.info("trabajo con error", extra={"job_id": job_id, "target": target,
                                                "error": exc.__class__.__name__})
    finally:
        try:
            (d / "input.pdf").unlink()  # el PDF original no se conserva
        except FileNotFoundError:
            pass
