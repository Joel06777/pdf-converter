"""PDF -> Word (.docx) con motor propio.

Tres rutas, elegidas automáticamente (o forzadas con `mode`):

* ``grid``  – documentos tipo tabla/estado financiero: se reconstruye la cuadrícula visual y se
  escribe una tabla de Word de ancho fijo con rellenos, bordes, celdas combinadas e imágenes
  ancladas en su posición exacta. Es la ruta más fiel para formularios y reportes.
* ``flow``  – documentos de texto corrido (cartas, contratos, artículos): pdf2docx reconstruye
  párrafos, columnas, tablas e imágenes.
* ``ocr``   – PDF escaneado: OCR propio y documento editable con el texto reconocido.
"""
from __future__ import annotations

from io import BytesIO

import pymupdf
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Pt, RGBColor

from .extract import ConversionCancelled, PageModel, extract_page, group_rows
from .numbers import parse_number
from .pdf_to_excel import _col_index, _vertical_merges, build_layout
from .verify import verify

_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
}
_BORDER_STYLE = {"hair": 2, "thin": 4, "medium": 12, "thick": 18}


# ----------------------------------------------------------------------------- detección

def _is_scanned(doc: pymupdf.Document) -> bool:
    return doc.page_count > 0 and all(len(p.get_text().strip()) < 20 for p in doc)


def _repeated_lines(models: list[PageModel]) -> tuple[list[str], list[str]]:
    """Textos que se repiten en todas las páginas arriba (encabezado) o abajo (pie).

    Sirven para el encabezado/pie de página de Word: no se repiten como tabla
    en cada página, sino una sola vez como encabezado del documento.
    """
    if len(models) < 2:
        return [], []
    from collections import Counter

    def zone(spans, top: bool):
        seen = Counter()
        for m in models:
            limit = 90 if top else m.height - 90
            texts = {s.text.strip() for s in spans(m) if (s.y0 < limit if top else s.y1 > limit)}
            seen.update(texts)
        return [t for t, n in seen.items() if n == len(models) and len(t) >= 3]

    headers = zone(lambda m: m.spans, top=True)
    footers = zone(lambda m: m.spans, top=False)
    return headers, footers


def _list_style(text: str) -> str | None:
    """Estilo de lista de Word para una línea que parece ítem de lista, o None."""
    import re

    t = text.strip()
    if re.match(r"^[•\-–\*]\s+\S", t):
        return "List Bullet"
    if re.match(r"^\d+[.)]\s+\S", t):
        return "List Number"
    return None


def _table_like(models: list[PageModel]) -> bool:
    for m in models:
        rows = group_rows(m.spans)
        multi = [r for r in rows if len(r.segments) >= 2]
        numeric_rows = [r for r in multi if any(parse_number(s.text) for s in r.segments)]
        if len(rows) < 5 or len(multi) < 0.4 * len(rows) or len(numeric_rows) < 5:
            return False
    return bool(models)


# ----------------------------------------------------------------------------- utilidades XML

def _set_cell_borders(cell, sides: dict):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    borders = OxmlElement("w:tcBorders")
    for name in ("top", "left", "bottom", "right"):
        side = sides.get(name)
        el = OxmlElement(f"w:{name}")
        if side is None:
            el.set(qn("w:val"), "nil")
        else:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(_BORDER_STYLE.get(side.style, 4)))
            el.set(qn("w:color"), (side.color.rgb if side.color and side.color.rgb else "000000")[-6:])
        borders.append(el)
    tcPr.append(borders)


def _shade(cell, color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def _valign_center(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    el = OxmlElement("w:vAlign")
    el.set(qn("w:val"), "center")
    tcPr.append(el)


def _fixed_table(table):
    tblPr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    mar = OxmlElement("w:tblCellMar")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), "0")
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblPr.append(mar)


_ANCHOR = (
    '<wp:anchor {ns} distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="251658240" '
    'behindDoc="0" locked="0" layoutInCell="0" allowOverlap="0">'
    '<wp:simplePos x="0" y="0"/>'
    '<wp:positionH relativeFrom="page"><wp:posOffset>{x}</wp:posOffset></wp:positionH>'
    '<wp:positionV relativeFrom="page"><wp:posOffset>{y}</wp:posOffset></wp:positionV>'
    '<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
    '<wp:docPr id="{id}" name="Imagen {id}"/><wp:cNvGraphicFramePr/></wp:anchor>'
)


def _anchored_picture(paragraph, png: bytes, x: float, y: float, w: float, h: float):
    """Inserta una imagen anclada a la página en coordenadas absolutas (puntos)."""
    run = paragraph.add_run()
    shape = run.add_picture(BytesIO(png), width=Pt(w), height=Pt(h))
    inline = shape._inline
    anchor = parse_xml(
        _ANCHOR.format(
            ns=nsdecls("wp"), x=int(x * 12700), y=int(y * 12700),
            cx=int(w * 12700), cy=int(h * 12700), id=inline.docPr.id,
        )
    )
    anchor.append(inline.graphic)
    inline.getparent().replace(inline, anchor)


# ----------------------------------------------------------------------------- ruta "grid"

def _grid_to_docx(src: str, dst: str, models: list[PageModel], on_progress=None, is_cancelled=None) -> dict:
    out = Document()
    headers, footers = _repeated_lines(models)
    for n, model in enumerate(models):
        if is_cancelled is not None and is_cancelled():
            raise ConversionCancelled("Conversión cancelada por el usuario.")
        lay = build_layout(model)
        cols, bounds = lay.cols, lay.bounds
        section = out.sections[0] if n == 0 else out.add_section(WD_SECTION.NEW_PAGE)
        section.page_width, section.page_height = Pt(model.width), Pt(model.height)
        section.left_margin = Pt(max(0.0, cols[0].left))
        section.right_margin = Pt(max(0.0, model.width - cols[-1].right))
        section.top_margin = Pt(max(0.0, bounds[0]))
        section.bottom_margin = Pt(max(0.0, model.height - bounds[-1] - 4))
        section.header_distance = section.footer_distance = Pt(0)
        if n == 0:
            if headers:
                section.header.paragraphs[0].text = "  |  ".join(headers)
            if footers:
                section.footer.paragraphs[0].text = "  |  ".join(footers)

        table = out.add_table(rows=len(bounds) - 1, cols=len(cols))
        table.autofit = False
        _fixed_table(table)
        for i, row in enumerate(table.rows):
            row.height = Pt(max(1.0, bounds[i + 1] - bounds[i]))
            row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            for j, cell in enumerate(row.cells):
                cell.width = Pt(cols[j].right - cols[j].left)
                _valign_center(cell)
                if (i, j) in lay.fills:
                    _shade(cell, lay.fills[(i, j)])
                _set_cell_borders(cell, lay.borders.get((i, j), {}))
                para = cell.paragraphs[0]
                para.paragraph_format.space_before = para.paragraph_format.space_after = Pt(0)

        # (las fusiones verticales se aplican tras escribir el texto: si se hacen
        # antes, las fusiones horizontales posteriores crean rangos no rectangulares)

        # En Word el texto no "desborda" a la celda vecina como en Excel: se combinan las celdas
        # libres que el texto ocupa en el PDF.
        occupied = {(p.row, p.col) for p in lay.placements}
        vmerges = _vertical_merges(model, lay)
        vmerge_tops = {(top, j) for top, j, _ in vmerges}
        for pl in lay.placements:
            j0 = j1 = pl.col
            if pl.merge_to is not None:
                j1 = pl.merge_to
            elif not pl.parsed:
                if pl.horizontal == "left":
                    j1 = _col_index(cols, pl.seg.x1 - 0.5)
                elif pl.horizontal == "right":
                    j0 = _col_index(cols, pl.seg.x0 + 0.5)
            n_cols = len(cols)
            shrunk = False
            while j1 > pl.col and any((pl.row, c) in occupied for c in range(pl.col + 1, j1 + 1)):
                j1 -= 1
                shrunk = True
            while j0 < pl.col and any((pl.row, c) in occupied for c in range(j0, pl.col)):
                j0 += 1
                shrunk = True
            if not shrunk and pl.merge_to is None and not pl.parsed:
                # "desbordar" como en Excel: usar también las celdas libres que siguen
                if pl.horizontal == "left":
                    while j1 + 1 < n_cols and (pl.row, j1 + 1) not in occupied:
                        j1 += 1
                elif pl.horizontal == "right":
                    while j0 - 1 >= 0 and (pl.row, j0 - 1) not in occupied:
                        j0 -= 1
            if (pl.row, pl.col) in vmerge_tops:
                # Inicio de una fusión vertical: no se fusiona en horizontal, o el
                # rango vertical posterior dejaría de ser rectangular.
                j0 = j1 = pl.col
            cell = table.cell(pl.row, j0)
            if j1 > j0:
                cell = cell.merge(table.cell(pl.row, j1))
                sides = dict(lay.borders.get((pl.row, j0), {}))
                right = lay.borders.get((pl.row, j1), {}).get("right")
                if right:
                    sides["right"] = right
                else:
                    sides.pop("right", None)
                _set_cell_borders(cell, sides)
            para = cell.paragraphs[0]
            para.alignment = _ALIGN[pl.horizontal]
            for k, line in enumerate(pl.seg.text.split("\n")):
                if k:
                    para.add_run().add_break()
                run = para.add_run(line)
                run.font.name = pl.seg.font
                run.font.size = Pt(pl.seg.size)
                run.bold, run.italic = pl.seg.bold, pl.seg.italic
                run.font.color.rgb = RGBColor.from_string(pl.seg.color)

        # Fusiones verticales (categorías que agrupan varias filas), tras el texto.
        for top, j, bottom in vmerges:
            try:
                table.cell(top, j).merge(table.cell(bottom, j))
            except Exception:
                pass

        first_para = table.cell(0, 0).paragraphs[0]
        for img in model.images:
            if img.full_page and model.scanned and lay.rows:
                continue
            _anchored_picture(first_para, img.png, img.x0, img.y0, img.x1 - img.x0, img.y1 - img.y0)

        tail = out.add_paragraph()  # Word exige un párrafo tras la tabla: lo dejamos mínimo
        tail.paragraph_format.space_before = tail.paragraph_format.space_after = Pt(0)
        tail.paragraph_format.line_spacing = Pt(1)
        tail.add_run().font.size = Pt(1)
        if on_progress is not None:
            on_progress(n + 1, len(models))
    out.save(dst)
    return {"pages": len(models), "engine": "grid"}


# ----------------------------------------------------------------------------- ruta "ocr"

def _scanned_to_docx(src: str, dst: str, ocr_lang: str, on_progress=None, is_cancelled=None) -> dict:
    doc = pymupdf.open(src)
    out = Document()
    for n, page in enumerate(doc):
        if is_cancelled is not None and is_cancelled():
            raise ConversionCancelled("Conversión cancelada por el usuario.")
        model = extract_page(doc, page, ocr=True, ocr_lang=ocr_lang)
        section = out.sections[0] if n == 0 else out.add_section(WD_SECTION.NEW_PAGE)
        section.page_width, section.page_height = Pt(model.width), Pt(model.height)
        section.left_margin = section.right_margin = Pt(36)
        section.top_margin = section.bottom_margin = Pt(36)
        rows = group_rows(model.spans)
        for row in rows:
            text = "   ".join(s.text for s in row.segments)
            para = out.add_paragraph()
            style = _list_style(text)
            if style:
                try:
                    para.style = style
                except Exception:
                    pass
            first = row.segments[0]
            run = para.add_run(text)
            run.font.size = Pt(first.size)
            run.bold = first.bold
        if not rows:
            out.add_paragraph("")
        if on_progress is not None:
            on_progress(n + 1, doc.page_count)
    out.save(dst)
    return {"pages": doc.page_count, "engine": "ocr"}


# ----------------------------------------------------------------------------- API pública

def pdf_to_word(src: str, dst: str, ocr: bool = True, ocr_lang: str = "spa+eng", mode: str = "auto",
                on_progress=None, is_cancelled=None) -> dict:
    doc = pymupdf.open(src)
    try:
        if mode == "auto" and _is_scanned(doc):
            mode = "ocr"
        if mode == "ocr":
            return _scanned_to_docx(src, dst, ocr_lang, on_progress, is_cancelled)
        models = [extract_page(doc, p, ocr=ocr, ocr_lang=ocr_lang) for p in doc]
        pages = doc.page_count
    finally:
        doc.close()

    if mode == "grid" or (mode == "auto" and _table_like(models)):
        return _grid_to_docx(src, dst, models, on_progress, is_cancelled)

    # Ruta de texto corrido (pdf2docx). Si pierde demasiado texto (p. ej. dos
    # columnas), se reintenta con la cuadrícula propia y se queda el mejor.
    import shutil
    import tempfile
    from pathlib import Path as _Path

    from pdf2docx import Converter

    tmp = _Path(tempfile.mkdtemp()) / "flow.docx"
    cv = Converter(src)
    try:
        cv.convert(str(tmp), start=0, end=None)
    finally:
        cv.close()
    flow_quality = verify(src, str(tmp), "word")
    if flow_quality.get("verifiable") and flow_quality.get("text_coverage", 1.0) >= 0.99:
        shutil.copyfile(tmp, dst)
        if on_progress is not None:
            on_progress(pages, pages)
        return {"pages": pages, "engine": "flow"}
    grid_info = _grid_to_docx(src, dst, models, on_progress, is_cancelled)
    grid_quality = verify(src, dst, "word")
    if flow_quality.get("text_coverage", 0) > grid_quality.get("text_coverage", 0):
        shutil.copyfile(tmp, dst)
        return {"pages": pages, "engine": "flow"}
    grid_info["engine"] = "grid (respaldo por cobertura)"
    return grid_info
