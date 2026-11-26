"""OCR propio: mejora escaneos (enderezado, rotación) y mapa de confianza por palabra.

No llama a ningún servicio externo. Usa Tesseract (binario local) a través de
PyMuPDF para el texto y, cuando está disponible, el TSV de `tesseract` para la
confianza de cada palabra. Si OCRmyPDF está instalado se usa como mejora previa
opcional; si no, se omite sin error. Si Tesseract no está instalado, todo el OCR
se degrada de forma visible: las conversiones de escaneos quedan sin texto y el
informe de calidad lo indica (ver `app/converters/verify.py`).
"""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pymupdf

# Confianza de Tesseract por debajo de este valor => palabra "dudosa".
LOW_CONFIDENCE = 60


def needs_ocr(src: str) -> bool:
    doc = pymupdf.open(src)
    try:
        return all(len(p.get_text().strip()) < 20 for p in doc) and doc.page_count > 0
    finally:
        doc.close()


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def deskew_angle(img) -> float:
    """Ángulo de corrección (grados) de una imagen en escala de grises: girar la
    imagen ese ángulo (PIL, antihorario positivo) la endereza.

    Busca el ángulo entre -5° y +5° que maximiza la varianza del perfil de
    proyección horizontal: el texto enderezado concentra tinta en pocas filas.
    Devuelve 0.0 si no hay suficiente texto para estimarlo.
    """
    import numpy as np
    from PIL import Image

    gray = img.convert("L") if img.mode != "L" else img
    small = gray.resize((min(gray.width, 800), int(gray.height * min(gray.width, 800) / gray.width)))
    arr = np.asarray(small, dtype=np.float32)
    black = (arr < 128).astype(np.float32)
    if black.sum() < 500:  # casi en blanco: nada que enderezar
        return 0.0
    best_angle, best_score = 0.0, -1.0
    for angle in [a * 0.5 for a in range(-10, 11)]:
        rotated = np.asarray(Image.fromarray((black * 255).astype("uint8")).rotate(angle, fillcolor=0), dtype=np.float32)
        profile = rotated.sum(axis=1)
        score = float(profile.var())
        if score > best_score:
            best_score, best_angle = score, angle
    return best_angle


def rotate_page_image(page: pymupdf.Page, angle_deg: float) -> bytes:
    """Renderiza la página girada `angle_deg` (ángulo de corrección de
    `deskew_angle`: girar ese ángulo endereza la página) y devuelve PNG."""
    from io import BytesIO

    from PIL import Image

    pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    if abs(angle_deg) >= 0.5:
        img = img.rotate(angle_deg, fillcolor=255)
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def word_confidences(png_bytes: bytes, lang: str = "spa+eng") -> list[dict]:
    """Confianza por palabra con `tesseract ... tsv` (binario local).

    Devuelve [{'text': str, 'x0','y0','x1','y1': float (0-1, relativo a la imagen),
    'conf': float}]. Vacío si Tesseract no está disponible.
    """
    import csv
    import tempfile

    if not tesseract_available():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / "page.png"
        img_path.write_bytes(png_bytes)
        try:
            proc = subprocess.run(
                ["tesseract", str(img_path), str(Path(tmp) / "out"), "-l", lang, "tsv"],
                capture_output=True, timeout=120, check=False,
            )
            tsv_path = Path(tmp) / "out.tsv"
            if proc.returncode != 0 or not tsv_path.exists():
                return []
            words = []
            with tsv_path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
                    if row.get("level") != "5" or not (row.get("text") or "").strip():
                        continue
                    try:
                        conf = float(row["conf"])
                        x0, y0 = int(row["left"]), int(row["top"])
                        w, h = int(row["width"]), int(row["height"])
                    except (KeyError, ValueError):
                        continue
                    words.append({"text": row["text"], "x0": x0, "y0": y0, "x1": x0 + w, "y1": y0 + h, "conf": conf})
            return words
        except Exception:
            return []


def low_confidence_words(confidences: list[dict], threshold: int = LOW_CONFIDENCE) -> list[str]:
    """Palabras con confianza baja, en español y sin duplicados (para la advertencia)."""
    seen: list[str] = []
    for w in confidences:
        if w["conf"] < threshold and w["text"] not in seen:
            seen.append(w["text"])
    return seen


def ocr_warning(confidences: list[dict]) -> str | None:
    """Advertencia en español si el OCR tiene palabras dudosas, o None."""
    low = low_confidence_words(confidences)
    if not low:
        return None
    muestra = ", ".join(low[:8])
    extra = f" y {len(low) - 8} más" if len(low) > 8 else ""
    return (f"El reconocimiento de texto (OCR) tiene baja confianza en algunas palabras "
            f"({muestra}{extra}). Revisa esas celdas antes de usar el archivo.")


def detect_rotation(page: pymupdf.Page) -> int:
    """Rotación de la página en grados (0/90/180/270) según sus metadatos y su texto.

    Las fotos de celular a veces llegan con la página girada 90° o 180°: si el
    texto nativo está girado, `page.rotation` ya lo refleja; si no hay texto,
    se devuelve 0 y el enderezado fino lo hace `deskew_angle`.
    """
    return int(page.rotation or 0) % 360


def improve_scan(src: str, workdir: str, lang: str = "spa+eng", timeout: int = 600) -> str:
    """Devuelve la ruta de un PDF con capa de texto mejorada, o `src` si no se pudo.

    Solo se usa OCRmyPDF cuando alguna página viene girada 90°/180°/270° (foto
    de celular de lado): su `--rotate-pages` endereza esos casos, que el OCR
    propio (enderezado fino de ±5°) no puede corregir. En escaneos normales NO
    se usa: su OCR sin binarización ni limpieza de líneas lee peor las cifras
    que el OCR propio de `extract.py` (medido: 65% frente a 100% de precisión
    numérica en el documento de referencia).
    """
    if not shutil.which("ocrmypdf") or not needs_ocr(src):
        return src
    doc = pymupdf.open(src)
    try:
        rotated = any((p.rotation or 0) % 360 in (90, 180, 270) for p in doc)
    finally:
        doc.close()
    if not rotated:
        return src
    out = str(Path(workdir) / "ocr.pdf")
    try:
        subprocess.run(
            ["ocrmypdf", "--skip-text", "--deskew", "--rotate-pages", "--optimize", "0", "-l", lang, src, out],
            check=True, capture_output=True, timeout=timeout,
        )
        return out
    except Exception:
        return src
