"""Paridad entre motores de conversión sobre el conjunto de oro (Fase 2).

Uso:
    python scripts/parity.py [--targets excel,word,pptx] [--limit N]
                             [--visual] [--visual-limit N] [--compare]
                             [--out scripts/parity]

Compara, para cada PDF de tests/fixtures/gold_manifest.json:

- Motor Python (app/converters, vía app.converters.convert): cobertura de
  texto y de cifras contra el manifiesto, valores de celda, rellenos,
  bordes, celdas combinadas e imágenes.
- Motor del navegador (web/engine/): existe como librería ESM con API
  pública (src/index.js → convertPdf, destinos excel/word/pptx) y Web
  Worker (src/worker.js), pero sin CLI. parity.py lo maneja con un
  harness Node temporal que llama a convertPdf con ocr: false.

Métrica visual (con --visual): renderiza el PDF original y el archivo
convertido (vía LibreOffice a PDF) a 100 dpi y compara con Pillow + NumPy:
diferencia media absoluta por píxel (0-1) y por regiones de una rejilla 4x4.
No hay SSIM disponible gratis en este entorno (scikit-image no instalado):
se usa diferencia por regiones con Pillow y se dice así.

Comparación con otros convertidores (con --compare): pdf2docx, pdfplumber,
LibreOffice y camelot sobre el mismo conjunto de oro; escribe
scripts/parity/COMPARACION.md. Solo se afirma superioridad si los números
lo demuestran; lo que no se puede ejecutar aquí queda como "no medido" con
el motivo.

Resultados: scripts/parity/parity_results.json y parity_results.csv
(directorio ignorado por git: ver .gitignore). Solo se reporta lo medido.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402
from app.converters import convert  # noqa: E402
from app.converters.numbers import parse_number  # noqa: E402
from app.converters.verify import docx_tokens, pptx_tokens, xlsx_tokens  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
MANIFEST = FIXTURES / "gold_manifest.json"
DEFAULT_OUT = ROOT / "scripts" / "parity"
EXT = {"excel": "xlsx", "word": "docx", "pptx": "pptx"}
TOKEN_READERS = {"excel": xlsx_tokens, "word": docx_tokens, "pptx": pptx_tokens}

TESSERACT = shutil.which("tesseract") is not None
SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")


def _norm_str(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().casefold())


def _manifest_counters(entry: dict):
    nums = Counter(("n", round(float(v), 4)) for v in entry["numbers"])
    texts = Counter(("t", w) for w in entry["texts"])
    return nums, texts


def _coverage(expected: Counter, got: Counter) -> float:
    total = sum(expected.values())
    if not total:
        return 1.0
    hit = sum(min(v, got.get(k, 0)) for k, v in expected.items())
    return round(hit / total, 4)


def _cell_values_xlsx(path: Path):
    from openpyxl import load_workbook

    wb = load_workbook(path)
    values: list = []
    merged = 0
    fills = 0
    borders = 0
    images = 0
    for ws in wb.worksheets:
        merged += len(list(ws.merged_cells.ranges))
        images += len(getattr(ws, "_images", []))
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                values.append(c.value)
                fill = c.fill
                if fill is not None and fill.patternType not in (None, "none"):
                    fills += 1
                border = c.border
                if border is not None and any(
                        (s is not None and s.style)
                        for s in (border.left, border.right,
                                  border.top, border.bottom)):
                    borders += 1
    return values, {"merged_ranges": merged, "filled_cells": fills,
                    "bordered_cells": borders, "images": images}


def _cell_values_docx(path: Path):
    from docx import Document

    doc = Document(path)
    texts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                texts.append(cell.text)
    images = len(doc.inline_shapes)
    images += sum(1 for p in doc.part.package.iter_parts()
                  if p.content_type.startswith("image/"))
    # Imágenes dibujadas: nº de <a:blip> en document.xml. La suma de arriba
    # contaba dos veces cada imagen en línea (una como forma y otra como
    # parte) aunque solo se dibujara una vez; por ejemplo, un escaneo daba
    # 2/1 tras el arreglo de duplicados, cuando en el documento aparece
    # una sola vez. El nº de dibujos es la medida correcta.
    import zipfile

    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    images = xml.count("<a:blip")
    return texts, {"images": images}


def _cell_values_pptx(path: Path):
    from pptx import Presentation

    prs = Presentation(path)
    texts = []
    images = 0
    for slide in prs.slides:
        for sh in slide.shapes:
            if sh.has_text_frame:
                texts.append(sh.text_frame.text)
            if sh.has_table:
                for row in sh.table.rows:
                    for cell in row.cells:
                        texts.append(cell.text)
            if sh.shape_type == 13:  # PICTURE
                images += 1
    return texts, {"images": images}


def _norm_cell(value) -> tuple[str, float | None]:
    """Normaliza un valor de celda: (texto normalizado, número o None).

    La interpretación de cifras es la del conversor (parse_number): "12.5%"
    vale 0.125 y los códigos como el RUC se quedan como texto.
    """
    if isinstance(value, (int, float)):
        return "", float(value)
    s = str(value).strip()
    p = parse_number(s)
    if p is not None:
        return "", p.value
    return _norm_str(s), None


def _check_cells(entry: dict, values: list) -> dict:
    """¿Cuántos valores de celda del manifiesto aparecen en la salida?"""
    have_nums: Counter = Counter()
    have_strs: set[str] = set()
    for v in values:
        text, num = _norm_cell(v)
        if num is not None:
            have_nums[round(num, 4)] += 1
        elif text:
            for tok in text.split():
                have_strs.add(tok)
            have_strs.add(text)
    total = 0
    found = 0
    missing: list[str] = []
    for table in entry.get("tables", []):
        for row in table:
            for cell in row:
                if not str(cell).strip():
                    continue
                total += 1
                text, num = _norm_cell(cell)
                if num is not None:
                    ok = have_nums.get(round(num, 4), 0) > 0
                    if ok:
                        have_nums[round(num, 4)] -= 1
                else:
                    ok = text in have_strs or all(
                        tok in have_strs for tok in text.split())
                if ok:
                    found += 1
                elif len(missing) < 5:
                    missing.append(str(cell))
    return {"cells_total": total, "cells_found": found,
            "cell_coverage": round(found / total, 4) if total else None,
            "missing_sample": missing}


def _check_merged(entry: dict, values: list, merged_ranges: int) -> dict:
    expected = entry.get("merged", [])
    if not expected:
        return {"merged_expected": 0, "merged_ranges_out": merged_ranges,
                "merged_values_once": None}
    once = 0
    for m in expected:
        val = str(m.get("value", ""))
        text, num = _norm_cell(val)
        count = 0
        for v in values:
            t2, n2 = _norm_cell(v)
            if num is not None and n2 is not None and round(n2, 4) == round(num, 4):
                count += 1
            elif num is None and t2 == text and text:
                count += 1
        if count == 1:
            once += 1
    return {"merged_expected": len(expected),
            "merged_ranges_out": merged_ranges,
            "merged_values_once": f"{once}/{len(expected)}"}


# ------------------------------------------------------------ métrica visual

def _render_pdf_pages(pdf_path: Path, dpi: int = 100):
    """Páginas como arrays grises (0-1) con PyMuPDF."""
    import numpy as np

    doc = pymupdf.open(pdf_path)
    pages = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            arr = np.asarray(bytearray(pix.samples), dtype=np.float32)
            arr = arr.reshape(pix.height, pix.width) / 255.0
            pages.append(arr)
    finally:
        doc.close()
    return pages


def _visual_compare(src_pdf: Path, out_path: Path, tmp: Path) -> dict:
    """Diferencia por regiones (Pillow/NumPy) entre el PDF original y el
    archivo convertido renderizado vía LibreOffice. Sin SSIM en este entorno."""
    import numpy as np

    if not SOFFICE:
        return {"visual": "no_medido", "reason": "LibreOffice no disponible"}
    rendered = tmp / (out_path.stem + ".pdf")  # soffice conserva el nombre base
    try:
        subprocess.run(
            [SOFFICE, "--headless", "--convert-to", "pdf", "--outdir",
             str(tmp), str(out_path)],
            check=True, capture_output=True, timeout=180)
    except Exception as exc:  # noqa: BLE001
        return {"visual": "no_medido", "reason": f"LibreOffice falló: {exc}"}
    if not rendered.exists():
        return {"visual": "no_medido",
                "reason": "LibreOffice no generó el PDF renderizado"}
    try:
        src_pages = _render_pdf_pages(src_pdf)
        out_pages = _render_pdf_pages(rendered)
    except Exception as exc:  # noqa: BLE001
        return {"visual": "no_medido", "reason": f"render falló: {exc}"}
    n = min(len(src_pages), len(out_pages))
    if n == 0:
        return {"visual": "no_medido", "reason": "sin páginas para comparar"}
    diffs = []
    region_max = 0.0
    for i in range(n):
        a, b = src_pages[i], out_pages[i]
        h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        d = np.abs(a[:h, :w] - b[:h, :w])
        diffs.append(float(d.mean()))
        # Rejilla 4x4 de regiones.
        rh, rw = h // 4, w // 4
        for r in range(4):
            for c in range(4):
                region = d[r * rh:(r + 1) * rh, c * rw:(c + 1) * rw]
                if region.size:
                    region_max = max(region_max, float(region.mean()))
    return {"visual": "medido",
            "pages_compared": n,
            "pages_src": len(src_pages),
            "pages_out": len(out_pages),
            "mean_abs_diff": round(sum(diffs) / len(diffs), 4),
            "max_region_mean_diff": round(region_max, 4),
            "method": "diferencia por regiones con Pillow/NumPy (sin SSIM)"}


# ------------------------------------------------------- motor del navegador

BROWSER_HARNESS = """\
// Harness temporal generado por scripts/parity.py. Maneja el motor del
// navegador (web/engine) desde Node con su API pública (src/index.js):
// convertPdf(pdfBytes, target, { ocr: false }).
// Uso: node browser_harness.mjs <pdf> <excel|word|pptx> <salida>
// Sin OCR (ocr: false): los escaneados salen sin texto, igual que el motor
// Python sin Tesseract en este entorno.
import { readFileSync, writeFileSync } from "node:fs";
import { convertPdf } from "{ENGINE}/src/index.js";

const [, , src, target, dst] = process.argv;
const { buffer, info, quality } = await convertPdf(readFileSync(src), target, {
  ocr: false,
});
writeFileSync(dst, buffer);
console.log(JSON.stringify({ info, quality }));
"""


def detect_browser_engine() -> dict:
    """Detecta web/engine/ y cómo manejarlo.

    El motor existe como librería ESM con API pública (src/index.js →
    convertPdf, destinos excel/word/pptx) y Web Worker (src/worker.js),
    pero no tiene CLI. parity.py lo maneja con un harness Node temporal
    (ver BROWSER_HARNESS) que llama a convertPdf con ocr: false.
    """
    engine = ROOT / "web" / "engine"
    if not engine.exists():
        return {"status": "no_existe",
                "reason": "web/engine/ no existe en el repo todavía"}
    missing = [f for f in ("src/index.js", "src/convert.js", "src/word.js")
               if not (engine / f).exists()]
    if missing:
        return {"status": "incompleto",
                "reason": f"web/engine/ existe pero faltan: {', '.join(missing)}"}
    if not (engine / "node_modules" / "mupdf").exists():
        return {"status": "sin_dependencias",
                "reason": "web/engine/ existe pero sin node_modules "
                          "(falta npm install en web/engine)"}
    return {"status": "orquestador",
            "engine": str(engine),
            "reason": "API pública src/index.js (convertPdf); sin CLI, se "
                      "maneja con harness Node temporal"}


def convert_with_browser(engine_dir: str, src: Path, target: str,
                         dst: Path, tmp: Path) -> dict:
    harness = tmp / "browser_harness.mjs"
    harness.write_text(BROWSER_HARNESS.replace("{ENGINE}", engine_dir),
                       encoding="utf-8")
    try:
        proc = subprocess.run(
            ["node", str(harness), str(src.resolve()), target,
             str(dst.resolve())],
            capture_output=True, text=True, timeout=300, cwd=engine_dir)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"no se pudo ejecutar el motor: {exc}"}
    if proc.returncode != 0 or not dst.exists():
        return {"ok": False,
                "reason": f"el motor devolvió {proc.returncode}: "
                          f"{(proc.stderr or proc.stdout).strip()[:300]}"}
    return {"ok": True, "info": proc.stdout.strip()[:300]}


def _inspect_output(entry: dict, target: str, out: Path, src: Path,
                    tmp: Path, visual: bool) -> dict:
    """Cobertura, celdas, combinadas, rellenos, bordes, imágenes y visual
    de un archivo ya convertido (sirve para ambos motores)."""
    result: dict = {}
    nums, texts = _manifest_counters(entry)
    try:
        got = TOKEN_READERS[target](str(out))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error",
                "error": f"no se pudo leer la salida: {exc}"}
    result["text_coverage"] = _coverage(nums | texts, got)
    result["number_coverage"] = _coverage(nums, got)
    try:
        if target == "excel":
            values, extra = _cell_values_xlsx(out)
        elif target == "word":
            values, extra = _cell_values_docx(out)
        else:
            values, extra = _cell_values_pptx(out)
    except Exception as exc:  # noqa: BLE001
        result["cells"] = {"error": f"no se pudo inspeccionar: {exc}"}
        return result
    result["cells"] = _check_cells(entry, values)
    result["merged"] = _check_merged(entry, values,
                                     extra.get("merged_ranges", 0))
    result["fills"] = {"filled_cells_out": extra.get("filled_cells"),
                       "fills_expected_regions": len(entry.get("fills", []))}
    result["borders"] = {"bordered_cells_out": extra.get("bordered_cells")}
    result["images"] = {"images_out": extra.get("images"),
                        "images_expected": entry.get("images", 0)}
    if visual:
        result["visual"] = _visual_compare(src, out, tmp)
    return result


# ------------------------------------------------------------- ejecución

def run_python_engine(entry: dict, target: str, tmp: Path, visual: bool,
                      ocr: bool = True) -> dict:
    src = FIXTURES / entry["file"]
    out = tmp / f"{src.stem}.{EXT[target]}"
    result: dict = {"file": entry["file"], "kind": entry["kind"],
                    "engine": "python", "target": target}
    if not ocr:
        result["ocr"] = "desactivado_por_flag"
    elif entry.get("scanned") and not TESSERACT:
        # Sin Tesseract no hay OCR en este entorno: la conversión se ejecuta
        # igual (el motor lo degrada sin error), pero la cobertura de texto
        # no es medible contra el manifiesto con OCR.
        result["ocr"] = "no_disponible_en_entorno"
    t0 = time.time()
    try:
        info = convert(str(src), str(out), target, ocr=ocr)
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["error"] = str(exc)[:300]
        result["seconds"] = round(time.time() - t0, 2)
        return result
    result["seconds"] = round(time.time() - t0, 2)
    result["status"] = "ok"
    result["info_quality"] = info.get("quality", {})
    if not out.exists():
        result["status"] = "error"
        result["error"] = "el motor no generó el archivo de salida"
        return result
    result.update(_inspect_output(entry, target, out, src, tmp, visual))
    return result


def run_browser_engine(entry: dict, target: str, tmp: Path,
                       detection: dict) -> dict:
    src = FIXTURES / entry["file"]
    out = tmp / f"{src.stem}.browser.{EXT[target]}"
    result: dict = {"file": entry["file"], "kind": entry["kind"],
                    "engine": "browser", "target": target}
    if detection["status"] != "orquestador":
        result["status"] = "no_medido"
        result["reason"] = detection["reason"]
        return result
    t0 = time.time()
    conv = convert_with_browser(detection["engine"], src, target, out, tmp)
    result["seconds"] = round(time.time() - t0, 2)
    if not conv["ok"]:
        result["status"] = "error"
        result["error"] = conv["reason"]
        return result
    result["status"] = "ok"
    result["browser_info"] = conv.get("info")
    result.update(_inspect_output(entry, target, out, src, tmp, False))
    return result


# ------------------------------------------------- comparación con terceros

def _tokens_from_text(text: str) -> Counter:
    tokens: Counter = Counter()
    for tok in text.split():
        p = parse_number(tok)
        if p is not None:
            tokens[("n", round(p.value, 4))] += 1
        elif tok != "$":
            tokens[("t", tok.casefold())] += 1
    return tokens


def _compare_pdf2docx(entry: dict, tmp: Path) -> dict:
    try:
        from pdf2docx import Converter
    except ImportError:
        return {"tool": "pdf2docx", "status": "no_medido",
                "reason": "pdf2docx no instalado"}
    src = FIXTURES / entry["file"]
    out = tmp / f"{src.stem}.pdf2docx.docx"
    try:
        conv = Converter(str(src))
        try:
            conv.convert(str(out))
        finally:
            conv.close()
    except Exception as exc:  # noqa: BLE001
        return {"tool": "pdf2docx", "status": "error", "error": str(exc)[:200]}
    if not out.exists():
        return {"tool": "pdf2docx", "status": "error",
                "error": "no generó el .docx"}
    nums, texts = _manifest_counters(entry)
    got = docx_tokens(str(out))
    return {"tool": "pdf2docx", "status": "ok",
            "text_coverage": _coverage(nums | texts, got),
            "number_coverage": _coverage(nums, got)}


def _compare_pdfplumber(entry: dict) -> dict:
    try:
        import pdfplumber
    except ImportError:
        return {"tool": "pdfplumber", "status": "no_medido",
                "reason": "pdfplumber no instalado"}
    src = FIXTURES / entry["file"]
    try:
        text = ""
        with pdfplumber.open(src) as pdf:
            for page in pdf.pages:
                text += "\n" + (page.extract_text() or "")
    except Exception as exc:  # noqa: BLE001
        return {"tool": "pdfplumber", "status": "error", "error": str(exc)[:200]}
    nums, texts = _manifest_counters(entry)
    got = _tokens_from_text(text)
    return {"tool": "pdfplumber", "status": "ok",
            "text_coverage": _coverage(nums | texts, got),
            "number_coverage": _coverage(nums, got)}


def _compare_libreoffice(entry: dict, tmp: Path) -> dict:
    if not SOFFICE:
        return {"tool": "libreoffice", "status": "no_medido",
                "reason": "LibreOffice no disponible"}
    src = FIXTURES / entry["file"]
    outdir = tmp / "lo"
    outdir.mkdir(exist_ok=True)
    out = outdir / f"{src.stem}.docx"
    try:
        subprocess.run([SOFFICE, "--headless", "--convert-to", "docx",
                        "--outdir", str(outdir), str(src)],
                       check=True, capture_output=True, timeout=180)
    except Exception as exc:  # noqa: BLE001
        return {"tool": "libreoffice", "status": "no_medido",
                "reason": f"soffice falló: {exc}"[:300]}
    if not out.exists():
        return {"tool": "libreoffice", "status": "no_medido",
                "reason": "LibreOffice no generó el .docx desde el PDF "
                          "(Draw no exporta a Word en esta versión/entorno)"}
    nums, texts = _manifest_counters(entry)
    got = docx_tokens(str(out))
    return {"tool": "libreoffice", "status": "ok",
            "text_coverage": _coverage(nums | texts, got),
            "number_coverage": _coverage(nums, got)}


def _compare_camelot(entry: dict, tmp: Path) -> dict:
    try:
        import camelot  # noqa: F401
    except ImportError:
        return {"tool": "camelot", "status": "no_medido",
                "reason": "camelot no instalado (requiere Ghostscript, "
                          "no disponible en esta VM)"}
    src = FIXTURES / entry["file"]
    try:
        import camelot
        tables = camelot.read_pdf(str(src), pages="all", flavor="lattice")
        text = "\n".join(tables[i].df.to_string()
                         for i in range(len(tables)))
    except Exception as exc:  # noqa: BLE001
        return {"tool": "camelot", "status": "error", "error": str(exc)[:200]}
    nums, texts = _manifest_counters(entry)
    got = _tokens_from_text(text)
    return {"tool": "camelot", "status": "ok",
            "text_coverage": _coverage(nums | texts, got),
            "number_coverage": _coverage(nums, got)}


def run_comparison(entries: list[dict], tmp: Path) -> list[dict]:
    rows: list[dict] = []
    for entry in entries:
        for fn in (_compare_pdf2docx, _compare_pdfplumber,
                   _compare_libreoffice, _compare_camelot):
            if fn is _compare_pdfplumber:
                r = fn(entry)
            else:
                r = fn(entry, tmp)
            r["file"] = entry["file"]
            r["kind"] = entry["kind"]
            rows.append(r)
    return rows


def write_comparison_md(rows: list[dict], python_rows: list[dict],
                        entries: list[dict], path: Path) -> None:
    """Tabla comparativa. Solo afirma superioridad si los números la muestran."""
    tools = ["python", "pdf2docx", "pdfplumber", "libreoffice", "camelot"]
    scanned = {e["file"] for e in entries if e.get("scanned")}
    by_tool: dict[str, list[dict]] = {t: [] for t in tools}
    for r in rows:
        by_tool[r["tool"]].append(r)
    for r in python_rows:
        if r.get("engine") == "python" and r.get("target") == "word" \
                and r.get("status") == "ok":
            by_tool["python"].append({
                "tool": "python", "status": "ok", "file": r.get("file"),
                "text_coverage": r.get("text_coverage"),
                "number_coverage": r.get("number_coverage")})

    def mean(tool: str, key: str, native_only: bool = False):
        vals = [r[key] for r in by_tool[tool]
                if r.get("status") == "ok" and r.get(key) is not None
                and (not native_only or r.get("file") not in scanned)]
        return (round(sum(vals) / len(vals), 4), len(vals)) if vals else (None, 0)

    def table(native_only: bool) -> list[str]:
        lines = [
            "| Herramienta | Texto (media) | Cifras (media) | Medidos | Estado |",
            "|---|---|---|---|---|",
        ]
        for tool in tools:
            mt, nt = mean(tool, "text_coverage", native_only)
            mn, _nn = mean(tool, "number_coverage", native_only)
            measured = [r for r in by_tool[tool] if r.get("status") == "ok"
                        and (not native_only or r.get("file") not in scanned)]
            state = "medido" if measured else "no medido"
            lines.append(f"| {tool} | {mt if mt is not None else '—'} | "
                         f"{mn if mn is not None else '—'} | {nt} | {state} |")
        return lines

    lines = [
        "# Comparación con otros convertidores (conjunto de oro)",
        "",
        "Generado por `scripts/parity.py --compare`. Solo se reporta lo medido "
        "en este entorno; lo no medido indica el motivo.",
        "",
        "## Media sobre los 42 PDFs (9 escaneados/fotos sin OCR dan 0 en las "
        "herramientas sin OCR y bajan la media)",
        "",
        *table(native_only=False),
        "",
        "## Media solo sobre los 33 PDFs con texto nativo",
        "",
        *table(native_only=True),
        "",
        "## Notas por herramienta",
        "",
    ]
    notes: dict[str, str] = {}
    for tool in tools:
        not_measured = [r for r in by_tool[tool]
                        if r.get("status") == "no_medido"]
        if not_measured:
            notes[tool] = not_measured[0].get("reason", "")
    for tool in tools:
        if tool in notes:
            lines.append(f"- **{tool}**: {notes[tool]}")
    lines += [
        "- **python** (motor propio, destino Word): medido con `scripts/parity.py` "
        "sobre el mismo manifiesto.",
        "- **pdfplumber**: extracción directa de texto del PDF (sin convertir a "
        "Office); la cobertura mide cuánto texto/cifras recupera del PDF.",
        "- **camelot**: extracción de tablas; la cobertura se mide sobre el texto "
        "de las tablas extraídas.",
        "",
        "## Lectura",
        "",
        "No se afirma superioridad de ninguna herramienta: las tablas muestran "
        "las medias medidas y cada lector puede compararlas. Si una herramienta "
        "queda como «no medido», es porque no se pudo ejecutar en este entorno, "
        "no porque sea peor.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", default="excel,word,pptx")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--visual", action="store_true")
    ap.add_argument("--visual-limit", type=int, default=8)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--ocr", choices=["auto", "off"], default="auto",
                    help="auto: OCR según el motor; off: sin OCR (rápido, "
                         "los escaneados dan cobertura 0)")
    ap.add_argument("--files", default="",
                    help="solo estos PDFs del manifiesto, separados por comas")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest[: args.limit] if args.limit else manifest
    if args.files:
        wanted = {f.strip() for f in args.files.split(",") if f.strip()}
        entries = [e for e in entries if e["file"] in wanted]
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    detection = detect_browser_engine()
    print(f"Motor Python: app/converters | Motor navegador: {detection['status']} "
          f"({detection['reason']})")
    print(f"Tesseract (OCR): {'sí' if TESSERACT else 'no — escaneados sin OCR'} | "
          f"LibreOffice: {'sí' if SOFFICE else 'no'}")

    results: list[dict] = []
    visual_done = 0
    with tempfile.TemporaryDirectory(prefix="parity-") as td:
        tmp = Path(td)
        for entry in entries:
            for target in targets:
                do_visual = bool(args.visual) and visual_done < args.visual_limit \
                    and target == "word"
                r = run_python_engine(entry, target, tmp, do_visual,
                                      ocr=(args.ocr != "off"))
                if do_visual and r.get("visual", {}).get("visual") == "medido":
                    visual_done += 1
                results.append(r)
                print(f"{entry['file']} [{target}] python: "
                      f"texto={r.get('text_coverage')} "
                      f"cifras={r.get('number_coverage')} "
                      f"celdas={r.get('cells', {}).get('cell_coverage')} "
                      f"{r.get('status')}")
                rb = run_browser_engine(entry, target, tmp, detection)
                results.append(rb)
        comparison_rows: list[dict] = []
        if args.compare:
            comparison_rows = run_comparison(entries, tmp)
            write_comparison_md(comparison_rows, results, entries,
                                outdir / "COMPARACION.md")
            print(f"Comparación escrita en {outdir / 'COMPARACION.md'}")

    (outdir / "parity_results.json").write_text(
        json.dumps({"browser_engine": detection,
                    "tesseract": TESSERACT,
                    "libreoffice": bool(SOFFICE),
                    "visual_method": "diferencia por regiones con Pillow/NumPy "
                                     "(sin SSIM: scikit-image no instalado)",
                    "results": results,
                    "comparison": comparison_rows},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with open(outdir / "parity_results.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "kind", "engine", "target", "status",
                    "text_coverage", "number_coverage", "cell_coverage",
                    "cells_found", "cells_total", "merged_expected",
                    "merged_ranges_out", "merged_values_once",
                    "filled_cells_out", "bordered_cells_out",
                    "images_out", "images_expected",
                    "visual_mean_abs_diff", "visual_max_region_diff",
                    "seconds", "error"])
        for r in results:
            cells = r.get("cells", {}) or {}
            merged = r.get("merged", {}) or {}
            fills = r.get("fills", {}) or {}
            borders = r.get("borders", {}) or {}
            images = r.get("images", {}) or {}
            visual = r.get("visual", {}) or {}
            w.writerow([r.get("file"), r.get("kind"), r.get("engine"),
                        r.get("target"), r.get("status"),
                        r.get("text_coverage"), r.get("number_coverage"),
                        cells.get("cell_coverage"), cells.get("cells_found"),
                        cells.get("cells_total"),
                        merged.get("merged_expected"),
                        merged.get("merged_ranges_out"),
                        merged.get("merged_values_once"),
                        fills.get("filled_cells_out"),
                        borders.get("bordered_cells_out"),
                        images.get("images_out"),
                        images.get("images_expected"),
                        visual.get("mean_abs_diff"),
                        visual.get("max_region_mean_diff"),
                        r.get("seconds"),
                        r.get("error") or r.get("reason") or ""])
    print(f"\nResultados en {outdir / 'parity_results.json'} y "
          f"{outdir / 'parity_results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
