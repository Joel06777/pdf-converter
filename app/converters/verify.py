"""Verificación automática de fidelidad: ¿todo el texto y todas las cifras del PDF llegaron al archivo?

Compara las "palabras" del PDF contra las del archivo convertido. Es la base de la métrica de
calidad que se devuelve en cada conversión y que se usa en las pruebas de aceptación.
"""
from __future__ import annotations

from collections import Counter

import pymupdf

from .numbers import parse_number


def _norm(token: str):
    p = parse_number(token)
    return ("n", round(p.value, 4)) if p else ("t", token.casefold())


def pdf_tokens(path: str) -> Counter | None:
    """Tokens del texto nativo del PDF. None si no tiene texto (escaneo): no se puede verificar."""
    doc = pymupdf.open(path)
    tokens: Counter = Counter()
    for page in doc:
        for w in page.get_text("words"):
            tokens[_norm(w[4])] += 1
    doc.close()
    return tokens if sum(tokens.values()) >= 5 else None


def xlsx_tokens(path: str) -> Counter:
    """Tokens de un .xlsx. Las celdas con fórmula =SUM(...) se evalúan con los
    valores de su rango (openpyxl no guarda valores en caché al escribir)."""
    import re

    from openpyxl import load_workbook
    from openpyxl.utils import column_index_from_string

    tokens: Counter = Counter()
    wb = load_workbook(path)
    for ws in wb.worksheets:
        numeric: dict[tuple[int, int], float] = {}
        formulas: list[tuple[int, int, str]] = []
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                if isinstance(c.value, (int, float)):
                    numeric[(c.row, c.column)] = float(c.value)
                    tokens[("n", round(float(c.value), 4))] += 1
                    if c.number_format.startswith('"'):
                        tokens[("t", c.number_format.split('"')[1].casefold())] += 1
                elif isinstance(c.value, str) and c.value.startswith("=SUM("):
                    formulas.append((c.row, c.column, c.value))
                else:
                    for t in str(c.value).split():
                        tokens[_norm(t)] += 1
        for r, col, formula in formulas:
            m = re.fullmatch(r"=SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)", formula.strip())
            if not m:
                continue
            c0, r0, c1, r1 = column_index_from_string(m.group(1)), int(m.group(2)), column_index_from_string(m.group(3)), int(m.group(4))
            total = sum(v for (rr, cc), v in numeric.items() if r0 <= rr <= r1 and c0 <= cc <= c1)
            numeric[(r, col)] = total
            tokens[("n", round(total, 4))] += 1
            # La fórmula conserva el formato de la cifra impresa (p. ej. "$").
            fmt = ws.cell(row=r, column=col).number_format or ""
            if fmt.startswith('"'):
                tokens[("t", fmt.split('"')[1].casefold())] += 1
    return tokens


def docx_tokens(path: str) -> Counter:
    from docx import Document

    doc = Document(path)
    texts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                texts.append(cell.text)
    return Counter(_norm(t) for text in texts for t in text.split())


def pptx_tokens(path: str) -> Counter:
    from pptx import Presentation

    tokens: Counter = Counter()
    for slide in Presentation(path).slides:
        parts = []
        for sh in slide.shapes:
            if sh.has_text_frame:
                parts.append(sh.text_frame.text)
            if sh.has_table:
                for row in sh.table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
        if slide.has_notes_slide:
            parts.append(slide.notes_slide.notes_text_frame.text)
        for text in parts:
            for t in text.split():
                tokens[_norm(t)] += 1
    return tokens


_READERS = {"excel": xlsx_tokens, "word": docx_tokens, "pptx": pptx_tokens}


def verify(src_pdf: str, out_path: str, target: str) -> dict:
    expected = pdf_tokens(src_pdf)
    if expected is None:
        return {"verifiable": False, "reason": "El PDF no tiene texto nativo (documento escaneado)."}
    got = _READERS[target](out_path)

    def cov(kind: str | None):
        items = {k: v for k, v in expected.items() if kind is None or k[0] == kind}
        total = sum(items.values())
        hit = sum(min(v, got.get(k, 0)) for k, v in items.items())
        return (hit / total if total else 1.0), items

    text_cov, _ = cov(None)
    num_cov, num_items = cov("n")
    missing = [str(k[1]) for k, v in expected.items() if got.get(k, 0) < v][:20]
    return {
        "verifiable": True,
        "text_coverage": round(text_cov, 4),
        "number_coverage": round(num_cov, 4),
        "missing_sample": missing,
    }
