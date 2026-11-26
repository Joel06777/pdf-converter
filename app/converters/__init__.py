"""Dispatcher de conversiones."""
from __future__ import annotations

from pathlib import Path

from .extract import ConversionCancelled
from .ocr import improve_scan
from .pdf_to_excel import pdf_to_excel
from .pdf_to_pptx import pdf_to_pptx
from .pdf_to_word import pdf_to_word
from .verify import verify

__all__ = ["TARGETS", "convert", "ConversionCancelled"]

TARGETS = {
    "excel": ("xlsx", pdf_to_excel),
    "word": ("docx", pdf_to_word),
    "pptx": ("pptx", pdf_to_pptx),
}


def convert(src: str, dst: str, target: str, ocr: bool = True, lang: str = "spa+eng",
            layout: str = "pages", formulas: bool = True,
            on_progress=None, is_cancelled=None) -> dict:
    """Convierte y verifica. Devuelve metadatos + métricas de calidad.

    `layout` solo afecta a Excel ("pages" o "continuous"). `on_progress(n, total)`
    se llama tras cada página; `is_cancelled()` aborta si devuelve True.
    """
    if target not in TARGETS:
        raise ValueError(f"Destino no soportado: {target}")
    work = str(Path(dst).parent)
    source = improve_scan(src, work, lang) if ocr else src
    kwargs = {"ocr": ocr, "ocr_lang": lang, "on_progress": on_progress, "is_cancelled": is_cancelled}
    if target == "excel":
        kwargs["layout"] = layout
        kwargs["formulas"] = formulas
    info = TARGETS[target][1](source, dst, **kwargs)
    if source != src and info.get("scanned_pages"):
        # El OCR lo hizo el pre-proceso (OCRmyPDF): las páginas escaneadas cuentan.
        info["ocr_pages"] = max(info.get("ocr_pages", 0), info["scanned_pages"])
    info["quality"] = verify(src, dst, target)
    return info
