"""PDF -> Excel (.xlsx) con motor propio.

Idea central: no se "adivinan" tablas con heurísticas de librerías externas, sino que se
reconstruye la cuadrícula visual del PDF (filas = líneas de texto, columnas = franjas
verticales ocupadas) y se copia a Excel todo lo que se ve: valores numéricos reales,
fuentes, colores de relleno, bordes, anchos/altos, celdas combinadas e imágenes.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from io import BytesIO

import pymupdf
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties

from .extract import ConversionCancelled, PageModel, Row, Segment, extract_page, group_rows
from .numbers import parse_number
from .ocr import LOW_CONFIDENCE, ocr_warning

EMU_PER_PT = 12700
MIN_GAP = 4.0  # huecos menores se consideran la misma columna
SPACER_MIN = 12.0  # huecos mayores se conservan como columna vacía
MIN_ROW_H = 5.0
MIN_COL_W = 9.0  # ancho mínimo (pt) para que un símbolo como "$" no quede recortado
SPLIT_MIN_OFFSET = 10.0  # texto suelto que empieza más allá de esto parte la columna
EDGE_REACH = 30.0  # cuánto se estiran los bordes exteriores hasta marcos/rellenos cercanos


@dataclass
class Col:
    left: float
    right: float
    run_l: float  # extensión real del texto (para decidir alineación)
    run_r: float


# ----------------------------------------------------------------------------- cuadrícula

def _build_columns(rows: list[Row], model: PageModel) -> list[Col]:
    table_rows = [r for r in rows if len(r.segments) >= 2]
    use = table_rows if len(table_rows) >= 2 else rows
    # Perfil de proyección: cuántas filas ocupan cada punto horizontal. Los puntos ocupados por
    # muy pocas filas (firmas, notas al pie) se tratan como huecos, para que un texto largo y
    # aislado no fusione las columnas de la tabla principal.
    width = int(model.width) + 2
    diff = [0] * (width + 2)
    for r in use:
        for sg in r.segments:
            a, b = max(0, int(sg.x0)), min(width, int(sg.x1) + 1)
            diff[a] += 1
            diff[b] -= 1
    noise = int(0.06 * len(use))
    occupied, acc = [], 0
    for x in range(width + 1):
        acc += diff[x]
        occupied.append(acc > noise)
    runs: list[list[float]] = []
    x = 0
    while x <= width:
        if occupied[x]:
            start = x
            while x <= width and occupied[x]:
                x += 1
            a, b = float(start), float(x)
            if runs and a - runs[-1][1] < MIN_GAP:
                runs[-1][1] = b
            else:
                runs.append([a, b])
        else:
            x += 1
    # los números alineados a la derecha pueden empezar antes del tramo "ocupado": ampliar la columna
    for r in rows:
        for sg in r.segments:
            if not parse_number(sg.text):
                continue
            cx = (sg.x0 + sg.x1) / 2
            for run in runs:
                if run[0] - 2 <= cx <= run[1] + 2:
                    run[0], run[1] = min(run[0], sg.x0), max(run[1], sg.x1)
                    break
    merged_runs: list[list[float]] = []
    for run in sorted(runs):
        if merged_runs and run[0] - merged_runs[-1][1] < MIN_GAP:
            merged_runs[-1][1] = max(merged_runs[-1][1], run[1])
        else:
            merged_runs.append(run)
    runs = merged_runs
    if not runs:  # página sin estructura: una sola columna
        runs = [[min(sg.x0 for r in rows for sg in r.segments), max(sg.x1 for r in rows for sg in r.segments)]]

    cols: list[Col] = []
    left = runs[0][0] - 1.0
    for i, (a, b) in enumerate(runs):
        if i + 1 < len(runs):
            na = runs[i + 1][0]
            if na - b >= SPACER_MIN:
                cols.append(Col(left, b + 0.5, a, b))
                cols.append(Col(b + 0.5, na - 0.5, b + 0.5, na - 0.5))
                left = na - 0.5
            else:
                mid = (b + na) / 2
                cols.append(Col(left, mid, a, b))
                left = mid
        else:
            cols.append(Col(left, b + 1.0, a, b))

    cols = _split_columns(cols, rows)
    _widen_narrow(cols)

    # estirar los bordes exteriores hasta marcos y rellenos cercanos
    xs_left = [l.pos for l in model.lines if l.orient == "v"] + [f.x0 for f in model.fills]
    xs_right = [l.pos for l in model.lines if l.orient == "v"] + [f.x1 for f in model.fills]
    near_l = [x for x in xs_left if 0 <= cols[0].left - x <= EDGE_REACH]
    near_r = [x for x in xs_right if 0 <= x - cols[-1].right <= EDGE_REACH]
    if near_l:
        cols[0].left = min(near_l)
    if near_r:
        cols[-1].right = max(near_r)
    return cols


def _split_columns(cols: list[Col], rows: list[Row]) -> list[Col]:
    """Parte columnas en el punto donde empieza texto suelto desplazado a la derecha
    (p. ej. un texto que empieza a mitad de la columna), para conservar su posición."""
    content_left, content_right = cols[0].left, cols[-1].right
    ccx = (content_left + content_right) / 2
    splits: dict[int, list[float]] = {}
    for r in rows:
        single = len(r.segments) == 1
        for seg in r.segments:
            if parse_number(seg.text):
                continue
            cx = (seg.x0 + seg.x1) / 2
            if single:
                centered = abs(cx - ccx) <= 8 and seg.x0 - content_left > 12
                right = seg.x1 >= content_right - 8 and seg.x0 > ccx
                if centered or right:
                    continue
            j = max(0, min(len(cols) - 1, bisect_right([c.left for c in cols], seg.x0) - 1))
            c = cols[j]
            if seg.x0 - c.left > SPLIT_MIN_OFFSET and c.right - seg.x0 > 6:
                xs = splits.setdefault(j, [])
                if not any(abs(x - seg.x0) < 3 for x in xs):
                    xs.append(seg.x0)
    out: list[Col] = []
    for j, c in enumerate(cols):
        edges = [c.left, *sorted(splits.get(j, [])), c.right]
        for a, b in zip(edges, edges[1:]):
            out.append(Col(a, b, c.run_l, c.run_r))
    return out


def _widen_narrow(cols: list[Col]) -> None:
    for j, c in enumerate(cols):
        need = MIN_COL_W - (c.right - c.left)
        if need <= 0:
            continue
        for nb, side in ((j + 1, "r"), (j - 1, "l")):
            if 0 <= nb < len(cols) and (cols[nb].right - cols[nb].left) - need >= MIN_COL_W:
                if side == "r":
                    c.right += need
                    cols[nb].left += need
                else:
                    c.left -= need
                    cols[nb].right -= need
                break


def _merge_wrapped_rows(rows: list[Row], model: PageModel) -> list[Row]:
    """Celdas con texto en varias líneas dentro de un mismo relleno -> una sola fila con salto de línea."""
    if len(rows) < 3 or not model.fills:
        return rows
    heights = sorted(r.y1 - r.y0 for r in rows)
    med = heights[len(heights) // 2]
    group_of: dict[int, int] = {}
    groups: list[list[int]] = []
    for f in model.fills:
        h = f.y1 - f.y0
        if not (1.5 * med < h <= 3.2 * med):
            continue
        idx = [i for i, r in enumerate(rows) if f.y0 <= (r.y0 + r.y1) / 2 <= f.y1 and i not in group_of]
        numeric_rows = sum(1 for i in idx if any(parse_number(sg.text) for sg in rows[i].segments))
        if 2 <= len(idx) <= 3 and idx == list(range(idx[0], idx[-1] + 1)) and numeric_rows <= 1:
            for i in idx:
                group_of[i] = len(groups)
            groups.append(idx)
    if not groups:
        return rows

    out: list[Row] = []
    done: set[int] = set()
    for i, r in enumerate(rows):
        if i not in group_of:
            out.append(r)
            continue
        g = group_of[i]
        if g in done:
            continue
        done.add(g)
        stacks: list[list[Segment]] = []
        for k in groups[g]:
            for s in rows[k].segments:
                for st in stacks:
                    if abs(st[0].x0 - s.x0) <= 3 and st[-1].y1 <= s.y0 + 1:
                        st.append(s)
                        break
                else:
                    stacks.append([s])
        segs = []
        for st in stacks:
            first = st[0]
            segs.append(Segment("\n".join(x.text for x in st), first.x0, min(x.y0 for x in st), max(x.x1 for x in st), max(x.y1 for x in st), first.font, first.size, first.bold, first.italic, first.color))
        segs.sort(key=lambda s: s.x0)
        out.append(Row(segs, min(s.y0 for s in segs), max(s.y1 for s in segs)))
    return out


def _build_row_bounds(rows: list[Row], model: PageModel) -> list[float]:
    h_candidates = [l.pos for l in model.lines if l.orient == "h"]
    for f in model.fills:
        h_candidates += [f.y0, f.y1]

    bounds = [rows[0].y0 - 1.0]
    for a, b in zip(rows, rows[1:]):
        mid = (a.y1 + b.y0) / 2
        lo, hi = min(a.y1, b.y0) - 1.5, max(a.y1, b.y0) + 1.5
        snaps = [c for c in h_candidates if lo <= c <= hi]
        if snaps:
            mid = min(snaps, key=lambda c: abs(c - mid))
        bounds.append(max(mid, bounds[-1] + MIN_ROW_H))
    bounds.append(max(rows[-1].y1 + 1.0, bounds[-1] + MIN_ROW_H))

    near_top = [c for c in h_candidates if 0 <= bounds[0] - c <= EDGE_REACH]
    near_bot = [c for c in h_candidates if 0 <= c - bounds[-1] <= EDGE_REACH]
    if near_top:
        bounds[0] = min(near_top)
    if near_bot:
        bounds[-1] = max(near_bot)
    return bounds


def _col_index(cols: list[Col], x: float) -> int:
    lefts = [c.left for c in cols]
    return max(0, min(len(cols) - 1, bisect_right(lefts, x) - 1))


def _row_index(bounds: list[float], y: float) -> int:
    return max(0, min(len(bounds) - 2, bisect_right(bounds, y) - 1))


# ----------------------------------------------------------------------------- estilo

def _font(seg: Segment) -> Font:
    return Font(name=seg.font, sz=seg.size, b=seg.bold, i=seg.italic, color=seg.color)


def _side(line_width: float, color: str) -> Side:
    style = "thin" if line_width < 1.4 else "medium" if line_width < 2.6 else "thick"
    if line_width < 0.45:
        style = "hair"
    return Side(style=style, color=color)


def _compute_borders(model: PageModel, cols: list[Col], bounds: list[float]):
    """Asigna líneas del PDF a los bordes de las celdas más cercanos."""
    tol = 3.5
    h_by_bound: dict[int, list] = {}
    v_by_bound: dict[int, list] = {}
    col_edges = [c.left for c in cols] + [cols[-1].right]
    for ln in model.lines:
        if ln.orient == "h":
            k = min(range(len(bounds)), key=lambda i: abs(bounds[i] - ln.pos))
            if abs(bounds[k] - ln.pos) <= tol:
                h_by_bound.setdefault(k, []).append(ln)
        else:
            k = min(range(len(col_edges)), key=lambda i: abs(col_edges[i] - ln.pos))
            if abs(col_edges[k] - ln.pos) <= tol:
                v_by_bound.setdefault(k, []).append(ln)

    def covering(lines, lo, hi):
        best = None
        for ln in lines:
            overlap = min(ln.b, hi) - max(ln.a, lo)
            if overlap >= 0.5 * (hi - lo) and (best is None or ln.width > best.width):
                best = ln
        return best

    borders: dict[tuple[int, int], dict[str, Side]] = {}
    for i in range(len(bounds) - 1):
        for j, col in enumerate(cols):
            sides: dict[str, Side] = {}
            top = covering(h_by_bound.get(i, []), col.left, col.right)
            bottom = covering(h_by_bound.get(i + 1, []), col.left, col.right)
            left = covering(v_by_bound.get(j, []), bounds[i], bounds[i + 1])
            right = covering(v_by_bound.get(j + 1, []), bounds[i], bounds[i + 1])
            for name, ln in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
                if ln:
                    sides[name] = _side(ln.width, ln.color)
            if sides:
                borders[(i, j)] = sides
    return borders


def _compute_fills(model: PageModel, cols: list[Col], bounds: list[float]) -> dict[tuple[int, int], str]:
    centers_x = [(c.left + c.right) / 2 for c in cols]
    centers_y = [(bounds[i] + bounds[i + 1]) / 2 for i in range(len(bounds) - 1)]
    result: dict[tuple[int, int], str] = {}
    for f in model.fills:  # en orden de dibujo: el último queda encima
        for i, cy in enumerate(centers_y):
            if not (f.y0 - 0.2 <= cy <= f.y1 + 0.2):
                continue
            for j, cx in enumerate(centers_x):
                if f.x0 - 0.2 <= cx <= f.x1 + 0.2:
                    result[(i, j)] = f.color
    return result


# ----------------------------------------------------------------------------- hoja

def _vertical_merges(model: PageModel, lay: Layout) -> list[tuple[int, int, int]]:
    """Fusiones verticales: un relleno que abarca varias filas con texto solo en la
    primera (p. ej. la categoría "Ingresos" que agrupa 3 filas) se fusiona en Excel.

    Solo se fusiona cuando las filas de abajo están vacías en esa columna: nunca
    se borra texto para fusionar.
    """
    rows, cols, bounds = lay.rows, lay.cols, lay.bounds
    occupied = {(p.row, p.col) for p in lay.placements}
    merges: list[tuple[int, int, int]] = []
    centers_y = [(bounds[i] + bounds[i + 1]) / 2 for i in range(len(bounds) - 1)]
    centers_x = [(c.left + c.right) / 2 for c in cols]
    for f in model.fills:
        row_idx = [i for i, cy in enumerate(centers_y) if f.y0 - 0.2 <= cy <= f.y1 + 0.2]
        if len(row_idx) < 2:
            continue
        for j, cx in enumerate(centers_x):
            if not (f.x0 - 0.2 <= cx <= f.x1 + 0.2):
                continue
            top = row_idx[0]
            if (top, j) not in occupied:
                continue
            if any((i, j) in occupied for i in row_idx[1:]):
                continue
            merges.append((top, j, row_idx[-1]))
    return merges


def _total_formulas(ws, lay: Layout) -> list[str]:
    """Fórmulas de totales opcionales: solo si el PDF etiqueta la fila como TOTAL
    y la suma de la columna coincide con la cifra impresa (tolerancia 0,01).

    Nunca se inventa un total: si la suma no cuadra, la cifra impresa se queda
    como valor. Devuelve las referencias de las celdas convertidas a fórmula.
    """
    by_cell = {(p.row, p.col): p for p in lay.placements if p.parsed is not None}
    applied: list[str] = []
    for (r, c), pl in list(by_cell.items()):
        label = " ".join(p.seg.text for p in lay.placements if p.row == r)
        if "TOTAL" not in label.upper():
            continue
        above = sorted(rr for (rr, cc) in by_cell if cc == c and rr < r)
        if len(above) < 2 or above != list(range(above[0], r)):
            continue
        total = sum(by_cell[(rr, c)].parsed.value for rr in above)
        if abs(total - pl.parsed.value) > 0.01:
            continue
        letter = get_column_letter(c + 1)
        cell = ws.cell(row=r + 1, column=c + 1)
        cell.value = f"=SUM({letter}{above[0] + 1}:{letter}{above[-1] + 1})"
        applied.append(f"{letter}{r + 1}")
    return applied

@dataclass
class Placement:
    row: int
    col: int
    seg: Segment
    horizontal: str
    merge_to: int | None
    parsed: object | None


@dataclass
class Layout:
    rows: list[Row]
    cols: list[Col]
    bounds: list[float]
    fills: dict
    borders: dict
    placements: list[Placement]


def build_layout(model: PageModel) -> Layout:
    """Reconstruye la cuadrícula visual de la página. La usan Excel y Word."""
    rows = _merge_wrapped_rows(group_rows(model.spans), model)
    if not rows:
        cols = [Col(0, model.width, 0, model.width)]
        bounds = [0.0, model.height]
    else:
        cols = _build_columns(rows, model)
        bounds = _build_row_bounds(rows, model)

    fills = _compute_fills(model, cols, bounds)
    borders = _compute_borders(model, cols, bounds)

    content_left, content_right = cols[0].left, cols[-1].right
    content_cx = (content_left + content_right) / 2
    placements: list[Placement] = []
    for i, row in enumerate(rows):
        single = len(row.segments) == 1
        for seg in row.segments:
            parsed = parse_number(seg.text)
            cx = (seg.x0 + seg.x1) / 2
            horizontal = "left"
            merge_to = None
            if single:
                width = seg.x1 - seg.x0
                if abs(cx - content_cx) <= 8 and width < 0.95 * (content_right - content_left) and seg.x0 - content_left > 12:
                    j, merge_to, horizontal = 0, len(cols) - 1, "center"
                elif seg.x1 >= content_right - 8 and seg.x0 > content_cx:
                    j, horizontal = _col_index(cols, seg.x1 - 0.5), "right"
                else:
                    j = _col_index(cols, seg.x0 + 0.5)
            else:
                j = _col_index(cols, cx)
                col = cols[j]
                lm, rm = seg.x0 - col.run_l, col.run_r - seg.x1
                if parsed:
                    horizontal = "left" if lm + 1.5 < rm else "right"
                elif lm <= 3:
                    horizontal = "left"
                elif rm <= 3:
                    horizontal = "right"
                elif abs(lm - rm) <= 1.5:
                    horizontal = "center"
                if horizontal == "left":
                    j = _col_index(cols, seg.x0 + 0.5)
                elif horizontal == "right":
                    j = _col_index(cols, seg.x1 - 0.5)
            if merge_to is None and "\n" in seg.text and horizontal == "left":
                merge_to = _col_index(cols, seg.x1 - 0.5)
            placements.append(Placement(i, j, seg, horizontal, merge_to, parsed))
    return Layout(rows, cols, bounds, fills, borders, placements)


def _is_low_confidence(seg: Segment, model: PageModel) -> bool:
    """¿Coincide este segmento con una palabra de OCR de baja confianza?

    Solo por texto exacto: la coincidencia por posición marcaba celdas vecinas
    que no tenían nada que ver con la palabra dudosa.
    """
    text = seg.text.strip().casefold()
    return any(w["conf"] < LOW_CONFIDENCE and w["text"].strip().casefold() == text
               for w in model.ocr_confidences)


def _page_to_sheet(ws, model: PageModel, start_row: int = 0, formulas: bool = True) -> dict:
    """Escribe una página en la hoja a partir de `start_row` (0 = primera fila).

    Devuelve {'rows': filas escritas, 'formulas': [refs], 'low_confidence_cells': [refs]}.
    """
    lay = build_layout(model)
    rows, cols, bounds, fills, borders = lay.rows, lay.cols, lay.bounds, lay.fills, lay.borders
    off = start_row  # desplazamiento de fila dentro de la hoja

    # --- dimensiones (puntos -> unidades de Excel)
    for j, c in enumerate(cols, start=1):
        px = (c.right - c.left) / 0.75
        ws.column_dimensions[get_column_letter(j)].width = max(0.5, min(255, (px - 5) / 7))
    for i in range(len(bounds) - 1):
        ws.row_dimensions[off + i + 1].height = max(1.0, min(409.0, bounds[i + 1] - bounds[i]))

    # --- celdas con solo estilo (rellenos y bordes)
    for (i, j) in set(fills) | set(borders):
        cell = ws.cell(row=off + i + 1, column=j + 1)
        if (i, j) in fills:
            cell.fill = PatternFill("solid", start_color=fills[(i, j)], end_color=fills[(i, j)])
        if (i, j) in borders:
            cell.border = Border(**borders[(i, j)])

    # --- texto
    merges: list[tuple[int, int, int]] = []
    low_cells: list[str] = []
    for pl in lay.placements:
        seg, parsed = pl.seg, pl.parsed
        cell = ws.cell(row=off + pl.row + 1, column=pl.col + 1)
        if parsed:
            cell.value = parsed.value
            cell.number_format = parsed.number_format
        else:
            cell.value = seg.text
        cell.font = _font(seg)
        cell.alignment = Alignment(horizontal=pl.horizontal, vertical="center", wrap_text="\n" in seg.text)
        if _is_low_confidence(seg, model):
            cell.fill = PatternFill("solid", start_color="FFF2CC", end_color="FFF2CC")
            low_cells.append(f"{get_column_letter(pl.col + 1)}{off + pl.row + 1}")
        if pl.merge_to is not None:
            merges.append((off + pl.row + 1, pl.col + 1, pl.merge_to + 1))

    for r, c0, c1 in merges:
        if c1 > c0:
            ws.merge_cells(start_row=r, start_column=c0, end_row=r, end_column=c1)

    # --- fusiones verticales (categorías que agrupan varias filas)
    for top, j, bottom in _vertical_merges(model, lay):
        try:
            ws.merge_cells(start_row=off + top + 1, start_column=j + 1, end_row=off + bottom + 1, end_column=j + 1)
        except ValueError:
            pass  # ya fusionada por otra regla: se deja como está

    # --- fórmulas de totales (solo si la suma coincide con lo impreso)
    formula_refs: list[str] = []
    if formulas:
        formula_refs = _total_formulas(ws, lay) if off == 0 else _total_formulas_offset(ws, lay, off)

    # --- imágenes (el fondo de un escaneo con OCR no se copia: el texto ya está en las celdas)
    for img in model.images:
        if img.full_page and model.scanned and rows:
            continue
        try:
            xl = XLImage(BytesIO(img.png))
        except Exception:
            continue
        j = _col_index(cols, img.x0)
        i = _row_index(bounds, img.y0)
        col_off = max(0.0, img.x0 - cols[j].left) * EMU_PER_PT
        row_off = max(0.0, img.y0 - bounds[i]) * EMU_PER_PT
        w_emu = int((img.x1 - img.x0) * EMU_PER_PT)
        h_emu = int((img.y1 - img.y0) * EMU_PER_PT)
        xl.width, xl.height = (img.x1 - img.x0) / 0.75, (img.y1 - img.y0) / 0.75
        xl.anchor = OneCellAnchor(
            _from=AnchorMarker(col=j, colOff=int(col_off), row=off + i, rowOff=int(row_off)),
            ext=XDRPositiveSize2D(w_emu, h_emu),
        )
        ws.add_image(xl)

    # --- vista e impresión
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.orientation = "landscape" if model.width > model.height else "portrait"
    ws.page_setup.paperSize = 9 if abs(model.width - 595) < 20 else 1
    ws.page_margins.left = ws.page_margins.right = 0.25
    ws.page_margins.top = ws.page_margins.bottom = 0.25
    return {"rows": len(bounds) - 1, "formulas": formula_refs, "low_confidence_cells": low_cells}


def _total_formulas_offset(ws, lay: Layout, off: int) -> list[str]:
    """Variante de _total_formulas para hojas continuas (filas desplazadas)."""
    by_cell = {(p.row + off, p.col): p for p in lay.placements if p.parsed is not None}
    applied: list[str] = []
    for (r, c), pl in list(by_cell.items()):
        label = " ".join(p.seg.text for p in lay.placements if p.row + off == r)
        if "TOTAL" not in label.upper():
            continue
        above = sorted(rr for (rr, cc) in by_cell if cc == c and rr < r)
        if len(above) < 2 or above != list(range(above[0], r)):
            continue
        total = sum(by_cell[(rr, c)].parsed.value for rr in above)
        if abs(total - pl.parsed.value) > 0.01:
            continue
        letter = get_column_letter(c + 1)
        ws.cell(row=r + 1, column=c + 1).value = f"=SUM({letter}{above[0] + 1}:{letter}{above[-1] + 1})"
        applied.append(f"{letter}{r + 1}")
    return applied


# ----------------------------------------------------------------------------- API pública

def pdf_to_excel(src: str, dst: str, ocr: bool = True, ocr_lang: str = "spa+eng",
                 layout: str = "pages", formulas: bool = True,
                 on_progress=None, is_cancelled=None) -> dict:
    """Convierte `src` (PDF) a `dst` (.xlsx). Devuelve metadatos de la conversión.

    `layout="pages"` (una hoja por página) o `"continuous"` (una sola hoja con
    todas las páginas seguidas). `on_progress(n, total)` se llama tras cada página;
    `is_cancelled()` aborta la conversión si devuelve True.
    """
    if layout not in ("pages", "continuous"):
        raise ValueError("layout debe ser 'pages' o 'continuous'")
    doc = pymupdf.open(src)
    wb = Workbook()
    wb.remove(wb.active)
    info = {"pages": doc.page_count, "ocr_pages": 0, "scanned_pages": 0,
            "layout": layout, "formulas": [], "low_confidence_cells": [], "ocr_warning": None}
    try:
        if layout == "continuous":
            ws = wb.create_sheet("Documento")
            start_row = 0
        for n, page in enumerate(doc, start=1):
            if is_cancelled is not None and is_cancelled():
                raise ConversionCancelled("Conversión cancelada por el usuario.")
            model = extract_page(doc, page, ocr=ocr, ocr_lang=ocr_lang)
            if layout == "continuous":
                result = _page_to_sheet(ws, model, start_row=start_row, formulas=formulas)
                start_row += result["rows"] + 1  # una fila en blanco entre páginas
            else:
                ws = wb.create_sheet(f"Página {n}")
                result = _page_to_sheet(ws, model, formulas=formulas)
            info["ocr_pages"] += int(model.ocr_used)
            info["scanned_pages"] += int(model.scanned)
            info["formulas"].extend(result["formulas"])
            info["low_confidence_cells"].extend(result["low_confidence_cells"])
            if model.ocr_confidences:
                warning = ocr_warning(model.ocr_confidences)
                if warning:
                    info["ocr_warning"] = warning
            if on_progress is not None:
                on_progress(n, doc.page_count)
    finally:
        doc.close()
    wb.save(dst)
    return info
