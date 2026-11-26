"""PDF -> PowerPoint (.pptx) con motor propio.

Cada página del PDF es una diapositiva del mismo tamaño. Todo queda editable:
texto en cuadros de texto con su fuente/tamaño/color, rellenos y líneas como formas,
imágenes como imágenes. En páginas escaneadas se coloca la imagen de fondo y el texto
reconocido por OCR se guarda en las notas de la diapositiva.
Las páginas tabulares (estados financieros, facturas) se convierten en tablas
nativas de PowerPoint cuando es posible, en vez de cuadros de texto sueltos.
"""
from __future__ import annotations

from io import BytesIO

import pymupdf
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from pptx.util import Emu, Pt

from .extract import ConversionCancelled, extract_page, group_rows
from .numbers import parse_number
from .pdf_to_excel import _vertical_merges, build_layout

EMU = 12700


def _e(v: float) -> Emu:
    return Emu(int(round(v * EMU)))


def _normalize_rotation(angle: float) -> float:
    """Ángulo de rotación para PowerPoint (-90..90). 180° no lo soporta el
    cuadro de texto: se deja horizontal (caso raro, ver docs/LIMITES.md)."""
    while angle > 90:
        angle -= 180
    while angle < -90:
        angle += 180
    return angle


def _is_table_page(model) -> bool:
    """¿La página es una tabla/reporte (varias filas con varias columnas y cifras)?"""
    rows = group_rows(model.spans)
    if len(rows) < 5:
        return False
    multi = [r for r in rows if len(r.segments) >= 2]
    numeric = [r for r in multi if any(parse_number(s.text) for s in r.segments)]
    return len(multi) >= 0.4 * len(rows) and len(numeric) >= 3


def _add_native_table(slide, model) -> bool:
    """Tabla nativa de PowerPoint a partir de la cuadrícula visual. Devuelve True
    si se pudo crear (si no, el llamador usa cuadros de texto)."""
    lay = build_layout(model)
    rows, cols, bounds = lay.rows, lay.cols, lay.bounds
    if len(rows) < 2 or len(cols) < 2:
        return False
    left, top = _e(cols[0].left), _e(bounds[0])
    width, height = _e(cols[-1].right - cols[0].left), _e(bounds[-1] - bounds[0])
    try:
        graphic = slide.shapes.add_table(len(rows), len(cols), left, top, width, height)
    except Exception:
        return False
    table = graphic.table
    for j, c in enumerate(cols):
        table.columns[j].width = _e(c.right - c.left)
    for i in range(len(rows)):
        table.rows[i].height = _e(max(1.0, bounds[i + 1] - bounds[i]))
    for (i, j), color in lay.fills.items():
        cell = table.cell(i, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor.from_string(color)
    for pl in lay.placements:
        cell = table.cell(pl.row, pl.col)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = cell.margin_right = cell.margin_top = cell.margin_bottom = 0
        tf = cell.text_frame
        tf.word_wrap = True
        lines = pl.seg.text.split("\n")
        for k, line in enumerate(lines):
            para = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
            run = para.add_run()
            run.text = line
            run.font.name = pl.seg.font
            run.font.size = Pt(pl.seg.size)
            run.font.bold = pl.seg.bold
            run.font.italic = pl.seg.italic
            run.font.color.rgb = RGBColor.from_string(pl.seg.color)
        if pl.merge_to is not None and pl.merge_to > pl.col:
            try:
                cell.merge(table.cell(pl.row, pl.merge_to))
            except Exception:
                pass
    for top_i, j, bottom_i in _vertical_merges(model, lay):
        try:
            table.cell(top_i, j).merge(table.cell(bottom_i, j))
        except Exception:
            pass
    return True


def pdf_to_pptx(src: str, dst: str, ocr: bool = True, ocr_lang: str = "spa+eng",
                on_progress=None, is_cancelled=None) -> dict:
    doc = pymupdf.open(src)
    prs = Presentation()
    first = doc[0].rect
    prs.slide_width, prs.slide_height = _e(first.width), _e(first.height)
    blank = prs.slide_layouts[6]
    info = {"pages": doc.page_count, "ocr_pages": 0}

    for n, page in enumerate(doc, start=1):
        if is_cancelled is not None and is_cancelled():
            raise ConversionCancelled("Conversión cancelada por el usuario.")
        model = extract_page(doc, page, ocr=ocr, ocr_lang=ocr_lang)
        slide = prs.slides.add_slide(blank)
        rows = group_rows(model.spans)

        for img in model.images:
            slide.shapes.add_picture(BytesIO(img.png), _e(img.x0), _e(img.y0), _e(img.x1 - img.x0), _e(img.y1 - img.y0))

        if model.scanned and model.images:
            text = "\n".join("  ".join(s.text for s in r.segments) for r in rows)
            if text:
                slide.notes_slide.notes_text_frame.text = text
            info["ocr_pages"] += int(model.ocr_used)
            if on_progress is not None:
                on_progress(n, doc.page_count)
            continue

        if _is_table_page(model) and _add_native_table(slide, model):
            if on_progress is not None:
                on_progress(n, doc.page_count)
            continue

        for f in model.fills:
            shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, _e(f.x0), _e(f.y0), _e(f.x1 - f.x0), _e(f.y1 - f.y0))
            shp.fill.solid()
            shp.fill.fore_color.rgb = RGBColor.from_string(f.color)
            shp.line.fill.background()
            shp.shadow.inherit = False

        for ln in model.lines:
            if ln.orient == "h":
                c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, _e(ln.a), _e(ln.pos), _e(ln.b), _e(ln.pos))
            else:
                c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, _e(ln.pos), _e(ln.a), _e(ln.pos), _e(ln.b))
            c.line.color.rgb = RGBColor.from_string(ln.color)
            c.line.width = Pt(max(0.25, ln.width))

        for row in rows:
            for seg in row.segments:
                box = slide.shapes.add_textbox(_e(seg.x0), _e(seg.y0), _e(seg.x1 - seg.x0 + 6), _e(seg.y1 - seg.y0 + 2))
                if seg.rotation:
                    box.rotation = _normalize_rotation(seg.rotation)
                tf = box.text_frame
                # Texto largo o multilínea: se ajusta dentro del cuadro en vez de
                # desbordar; el resto conserva el ancho exacto del PDF.
                tf.word_wrap = "\n" in seg.text or len(seg.text) > 40
                tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                lines = seg.text.split("\n")
                for k, line in enumerate(lines):
                    para = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                    run = para.add_run()
                    run.text = line
                    run.font.name = seg.font
                    run.font.size = Pt(seg.size)
                    run.font.bold = seg.bold
                    run.font.italic = seg.italic
                    run.font.color.rgb = RGBColor.from_string(seg.color)
        if on_progress is not None:
            on_progress(n, doc.page_count)

    doc.close()
    prs.save(dst)
    return info
