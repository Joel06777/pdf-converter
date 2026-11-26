"""Pruebas de la batería ampliada de fixtures (ver scripts/generate_fixtures.py).

Criterios medibles: cobertura de texto y de números (sección 3 del prompt).
Las pruebas de OCR se omiten si Tesseract no está instalado en el entorno.
"""
import shutil
from pathlib import Path

import pymupdf
import pytest
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from app.converters import convert
from app.converters.extract import extract_page
from app.converters.ocr import deskew_angle
from app.converters.verify import pdf_tokens, xlsx_tokens

FIX = Path(__file__).parent / "fixtures"
TESSERACT = shutil.which("tesseract") is not None
needs_tesseract = pytest.mark.skipif(not TESSERACT, reason="Tesseract no instalado")


def _numeric_values(path):
    """Valores numéricos del .xlsx, resolviendo las fórmulas =SUM(...) (openpyxl
    no guarda valores en caché al escribir)."""
    return [k[1] for k in xlsx_tokens(path) if k[0] == "n"]


def _all_text_xlsx(path):
    ws = load_workbook(path).active
    return [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]


# --------------------------------------------------------------------- factura

def test_factura_excel_numeros_reales_y_formula(tmp_path):
    out = tmp_path / "f.xlsx"
    info = convert(str(FIX / "factura.pdf"), str(out), "excel")
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0
    values = _numeric_values(out)
    assert 335.0 in values and 50.0 in values and 160.0 in values
    # El TOTAL es una fórmula real solo si la suma coincide con lo impreso.
    ws = load_workbook(out).active
    formulas = [c.value for row in ws.iter_rows() for c in row
                if isinstance(c.value, str) and c.value.startswith("=SUM(")]
    assert formulas, "se esperaba una fórmula =SUM(...) en la fila TOTAL"
    # El RUC se queda como texto, no como número.
    assert any("0993132977001" in t for t in _all_text_xlsx(out))


def test_factura_pptx_tabla_nativa(tmp_path):
    out = tmp_path / "f.pptx"
    info = convert(str(FIX / "factura.pdf"), str(out), "pptx")
    assert info["quality"]["text_coverage"] == 1.0
    prs = Presentation(out)
    tables = [sh for s in prs.slides for sh in s.shapes if sh.has_table]
    assert tables, "se esperaba una tabla nativa de PowerPoint"
    cells = [c.text for t in tables for row in t.table.rows for c in row.cells]
    assert any("335" in c for c in cells)


# ------------------------------------------------------- estado de cuenta (3 págs)

def test_estado_cuenta_tres_hojas_y_continuo(tmp_path):
    out = tmp_path / "e.xlsx"
    info = convert(str(FIX / "estado_cuenta_multipagina.pdf"), str(out), "excel")
    assert info["pages"] == 3
    assert info["quality"]["number_coverage"] == 1.0
    wb = load_workbook(out)
    assert len(wb.worksheets) == 3

    out2 = tmp_path / "e2.xlsx"
    info2 = convert(str(FIX / "estado_cuenta_multipagina.pdf"), str(out2), "excel", layout="continuous")
    assert info2["layout"] == "continuous"
    assert info2["quality"]["number_coverage"] == 1.0
    wb2 = load_workbook(out2)
    assert len(wb2.worksheets) == 1
    assert wb2.active.max_row > 25  # las 3 páginas seguidas en una sola hoja


def test_estado_cuenta_word_encabezado(tmp_path):
    out = tmp_path / "e.docx"
    info = convert(str(FIX / "estado_cuenta_multipagina.pdf"), str(out), "word")
    assert info["quality"]["text_coverage"] == 1.0
    doc = Document(out)
    assert len(doc.sections) == 3  # una sección (salto de página) por página
    assert "ESTADO DE CUENTA" in doc.sections[0].header.paragraphs[0].text


# ------------------------------------------------------------- tabla sin líneas

def test_tabla_sin_lineas_excel(tmp_path):
    out = tmp_path / "s.xlsx"
    info = convert(str(FIX / "tabla_sin_lineas.pdf"), str(out), "excel")
    assert info["quality"]["number_coverage"] == 1.0
    assert info["quality"]["text_coverage"] >= 0.99
    values = _numeric_values(out)
    assert 1950.50 in values and 1680.0 in values


# ------------------------------------------------------------ celdas combinadas

def test_celdas_combinadas_verticales(tmp_path):
    out = tmp_path / "c.xlsx"
    info = convert(str(FIX / "celdas_combinadas.pdf"), str(out), "excel")
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0
    ws = load_workbook(out).active
    vertical = [str(r) for r in ws.merged_cells.ranges if r.min_row != r.max_row]
    assert vertical, "se esperaba al menos una fusión vertical (Ingresos/Egresos)"

    out2 = tmp_path / "c.docx"
    convert(str(FIX / "celdas_combinadas.pdf"), str(out2), "word")
    table = Document(out2).tables[0]
    assert "vMerge" in table._tbl.xml  # fusión vertical real en el .docx


# --------------------------------------------------------------- dos columnas

def test_dos_columnas_word_no_pierde_texto(tmp_path):
    out = tmp_path / "d.docx"
    info = convert(str(FIX / "dos_columnas.pdf"), str(out), "word")
    assert info["quality"]["text_coverage"] >= 0.99, info["quality"]
    assert info["quality"]["number_coverage"] == 1.0


# --------------------------------------------------------------------- acentos

@pytest.mark.parametrize("target,ext", [("excel", "xlsx"), ("word", "docx"), ("pptx", "pptx")])
def test_acentos_y_simbolos(tmp_path, target, ext):
    out = tmp_path / f"a.{ext}"
    info = convert(str(FIX / "acentos.pdf"), str(out), target)
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0


def test_acentos_ruc_como_texto(tmp_path):
    out = tmp_path / "a.xlsx"
    convert(str(FIX / "acentos.pdf"), str(out), "excel")
    texts = _all_text_xlsx(out)
    assert any("0993132977001" in t for t in texts)
    # ...y ningún número gigante (el RUC no se convirtió a cifra).
    assert not any(v > 10**12 for v in _numeric_values(out))


# ------------------------------------------------- factura real (logo + sello)

@pytest.mark.parametrize("target,ext", [("excel", "xlsx"), ("word", "docx"), ("pptx", "pptx")])
def test_factura_real_logo_sello_cobertura_total(tmp_path, target, ext):
    """Factura con logo dibujado y sello circular: cobertura 1,0 en los 3 destinos."""
    out = tmp_path / f"r.{ext}"
    info = convert(str(FIX / "factura_real_logo_sello.pdf"), str(out), target)
    assert info["quality"]["text_coverage"] == 1.0, info["quality"]
    assert info["quality"]["number_coverage"] == 1.0, info["quality"]


def test_factura_real_logo_sello_cifras_y_iva(tmp_path):
    out = tmp_path / "r.xlsx"
    info = convert(str(FIX / "factura_real_logo_sello.pdf"), str(out), "excel")
    values = _numeric_values(out)
    # Subtotal 335 + IVA 15% (50.25) = total 385.25 (aritmética consistente).
    assert 335.0 in values and 50.25 in values and 385.25 in values
    assert round(335.0 + 50.25, 2) == 385.25
    texts = _all_text_xlsx(out)
    assert any("PAGADO" in t for t in texts)  # texto del sello
    assert any("EL TORNILLO" in t for t in texts)  # texto del logo
    assert info["quality"]["missing_sample"] == []


# -------------------------------------------- tabla combinada compleja

def test_tabla_combinada_compleja_fusiones(tmp_path):
    out = tmp_path / "t.xlsx"
    info = convert(str(FIX / "tabla_combinada_compleja.pdf"), str(out), "excel")
    assert info["quality"]["text_coverage"] == 1.0, info["quality"]
    assert info["quality"]["number_coverage"] == 1.0, info["quality"]
    ws = load_workbook(out).active
    ranges = list(ws.merged_cells.ranges)
    vertical = [r for r in ranges if r.min_row != r.max_row]
    horizontal = [r for r in ranges if r.min_col != r.max_col]
    assert len(vertical) >= 2, "se esperaban ≥2 fusiones verticales (Norte/Sur)"
    assert horizontal, "se esperaba ≥1 fusión horizontal (encabezado VENTAS 2026)"
    assert 520.0 in _numeric_values(out)  # TOTAL (fórmula =SUM resuelta)

    out2 = tmp_path / "t.docx"
    convert(str(FIX / "tabla_combinada_compleja.pdf"), str(out2), "word")
    table = Document(out2).tables[0]
    assert "vMerge" in table._tbl.xml
    assert "gridSpan" in table._tbl.xml  # fusión horizontal real en el .docx


@pytest.mark.parametrize("target,ext", [("word", "docx"), ("pptx", "pptx")])
def test_tabla_combinada_compleja_otros_destinos(tmp_path, target, ext):
    out = tmp_path / f"t.{ext}"
    info = convert(str(FIX / "tabla_combinada_compleja.pdf"), str(out), target)
    assert info["quality"]["text_coverage"] == 1.0, info["quality"]
    assert info["quality"]["number_coverage"] == 1.0, info["quality"]


# -------------------------------------------- dos columnas con tablas

@pytest.mark.parametrize("target,ext", [("excel", "xlsx"), ("word", "docx"), ("pptx", "pptx")])
def test_dos_columnas_tablas_cobertura_total(tmp_path, target, ext):
    """Cada columna trae su propia tabla: ninguna cifra de ninguna tabla se pierde."""
    out = tmp_path / f"d.{ext}"
    info = convert(str(FIX / "dos_columnas_tablas.pdf"), str(out), target)
    assert info["quality"]["text_coverage"] == 1.0, info["quality"]
    assert info["quality"]["number_coverage"] == 1.0, info["quality"]


def test_dos_columnas_tablas_cifras_de_ambas(tmp_path):
    out = tmp_path / "d.xlsx"
    convert(str(FIX / "dos_columnas_tablas.pdf"), str(out), "excel")
    values = _numeric_values(out)
    assert 100.50 in values  # TOTAL gastos (izquierda)
    assert 1545.50 in values  # TOTAL ingresos (derecha)
    texts = _all_text_xlsx(out)
    assert any("Internet" in t for t in texts) and any("Alquiler" in t for t in texts)


# ------------------------------------------------------------------- progreso

def test_progreso_por_pagina_y_cancelacion(tmp_path):
    seen = []
    out = tmp_path / "p.xlsx"
    convert(str(FIX / "estado_cuenta_multipagina.pdf"), str(out), "excel",
            on_progress=lambda n, total: seen.append((n, total)))
    assert seen == [(1, 3), (2, 3), (3, 3)]

    from app.converters import ConversionCancelled

    with pytest.raises(ConversionCancelled):
        convert(str(FIX / "estado_cuenta_multipagina.pdf"), str(tmp_path / "x.xlsx"),
                "excel", is_cancelled=lambda: True)


def test_deskew_angle_sintetico():
    """Enderezado: una imagen inclinada 3° se estima en ±3° (sin Tesseract)."""
    from PIL import Image, ImageDraw

    img = Image.new("L", (800, 600), 255)
    draw = ImageDraw.Draw(img)
    for y in range(60, 560, 40):
        for x in range(60, 740, 30):
            draw.rectangle([x, y, x + 18, y + 8], fill=0)
    assert abs(deskew_angle(img)) < 0.5
    assert abs(deskew_angle(img.rotate(3, fillcolor=255)) + 3) <= 0.5


# ------------------------------------------------------------------------ OCR

@needs_tesseract
def test_escaneado_ocr_recupera_cifras(tmp_path):
    out = tmp_path / "s.xlsx"
    info = convert(str(FIX / "escaneado.pdf"), str(out), "excel")
    assert info["ocr_pages"] == 1
    expected = {k: v for k, v in pdf_tokens(str(FIX / "factura.pdf")).items() if k[0] == "n"}
    got = xlsx_tokens(str(out))
    hit = sum(min(v, got.get(k, 0)) for k, v in expected.items())
    ratio = hit / sum(expected.values())
    print(f"precisión numérica OCR (escaneado): {ratio:.1%}")
    assert ratio >= 0.97


@needs_tesseract
def test_foto_inclinada_ocr_con_enderezado(tmp_path):
    doc = pymupdf.open(FIX / "foto_inclinada.pdf")
    model = extract_page(doc, doc[0])
    assert model.scanned and model.ocr_used
    assert 0.5 <= abs(model.deskew_degrees) <= 5.0, f"enderezado: {model.deskew_degrees}°"
    out = tmp_path / "f.xlsx"
    info = convert(str(FIX / "foto_inclinada.pdf"), str(out), "excel")
    assert info["ocr_pages"] == 1
    expected = {k: v for k, v in pdf_tokens(str(FIX / "factura.pdf")).items() if k[0] == "n"}
    got = xlsx_tokens(str(out))
    hit = sum(min(v, got.get(k, 0)) for k, v in expected.items())
    ratio = hit / sum(expected.values())
    print(f"precisión numérica OCR (foto inclinada 3°): {ratio:.1%}")
    assert ratio >= 0.90  # umbral menor: la foto inclinada es un caso más difícil


def _ocr_ratios(scan: Path, original: Path, out: Path):
    """(precisión de cifras, precisión de texto solo) del OCR contra el original."""
    convert(str(scan), str(out), "excel")
    expected = pdf_tokens(str(original))
    got = xlsx_tokens(str(out))
    ratios = {}
    for kind in ("n", "t"):
        exp = {k: v for k, v in expected.items() if k[0] == kind}
        hit = sum(min(v, got.get(k, 0)) for k, v in exp.items())
        ratios[kind] = hit / sum(exp.values())
    return ratios["n"], ratios["t"]


@needs_tesseract
def test_escaneado_color_sello_ocr(tmp_path):
    """Escaneo en color con sello rojo y marca de agua diagonal: las cifras
    (lo crítico) deben sobrevivir; el texto pierde algo por la marca de agua.

    Medido antes de las mejoras de OCR: cifras 100 %, texto 83,3 %.
    Umbrales con margen por debajo de lo medido.
    """
    out = tmp_path / "s.xlsx"
    info = convert(str(FIX / "escaneado_color_sello.pdf"), str(out), "excel")
    assert info["ocr_pages"] == 1
    num, txt = _ocr_ratios(FIX / "escaneado_color_sello.pdf", FIX / "factura.pdf", out)
    print(f"OCR escaneado color+sello: cifras {num:.1%}, texto {txt:.1%}")
    assert num >= 0.97
    assert txt >= 0.75


@needs_tesseract
def test_foto_celular_perspectiva_ocr(tmp_path):
    """Foto con perspectiva leve + inclinación 2°: el enderezado debe actuar
    y las cifras deben recuperarse.

    Medido antes de las mejoras de OCR: cifras 100 %, texto 89,6 %.
    """
    doc = pymupdf.open(FIX / "foto_celular_perspectiva.pdf")
    model = extract_page(doc, doc[0])
    assert model.scanned and model.ocr_used
    assert 0.5 <= abs(model.deskew_degrees) <= 5.0, f"enderezado: {model.deskew_degrees}°"
    out = tmp_path / "f.xlsx"
    info = convert(str(FIX / "foto_celular_perspectiva.pdf"), str(out), "excel")
    assert info["ocr_pages"] == 1
    num, txt = _ocr_ratios(FIX / "foto_celular_perspectiva.pdf", FIX / "factura.pdf", out)
    print(f"OCR foto perspectiva: cifras {num:.1%}, texto {txt:.1%}")
    assert num >= 0.90
    assert txt >= 0.80


# ------------------------------------------------- validación de totales (OCR)

def _scan_con_totales(tmp_path, total_impreso: float) -> Path:
    """Escaneo de una factura mínima con SUBTOTAL 100 + IVA 15 = TOTAL dado."""
    from io import BytesIO

    from PIL import Image

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((40, 60), "FACTURA PRUEBA", fontsize=16, fontname="hebo")
    page.insert_text((40, 110), "SUBTOTAL $ 100.00", fontsize=14)
    page.insert_text((40, 140), "IVA 15% $ 15.00", fontsize=14)
    page.insert_text((40, 170), f"TOTAL $ {total_impreso:,.2f}", fontsize=14)
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    scan = pymupdf.open()
    new = scan.new_page(width=595, height=842)
    new.insert_image(new.rect, stream=buf.getvalue())
    path = tmp_path / "totales.pdf"
    scan.save(path)
    return path


@needs_tesseract
def test_totales_inconsistentes_avisan_y_no_corrigen(tmp_path):
    """100 + 15 != 999: la conversión avisa en español, marca las celdas en
    amarillo y NO cambia el total impreso (999.00 se queda como está).

    Este documento mínimo (4 líneas) también es la regresión del bug de
    binarización: con autocontrast cutoff=1 el OCR lo leía ilegible y no
    había aviso; con el guarda por densidad de tinta se lee bien.
    """
    scan = _scan_con_totales(tmp_path, 999.00)
    out = tmp_path / "t.xlsx"
    info = convert(str(scan), str(out), "excel")
    assert info["ocr_pages"] == 1
    assert info.get("ocr_warning") and "no coincide" in info["ocr_warning"], info
    assert info.get("totals_warning") and "999" in info["totals_warning"]
    ws = load_workbook(out).active
    all_vals = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    # El total impreso sigue ahí (en este documento mínimo va como texto de
    # la fila, no como cifra suelta) y no aparece ningún 115 corregido.
    assert any("999" in str(v) for v in all_vals), "el total impreso no debe desaparecer"
    assert not any(v == 115.0 for v in all_vals), "no se inventa un total corregido"
    total_cell = next(c for row in ws.iter_rows() for c in row
                      if c.value is not None and "999" in str(c.value))
    assert total_cell.fill.start_color.rgb.endswith("FFF2CC"), "la celda TOTAL va en amarillo"


@needs_tesseract
def test_totales_consistentes_sin_falso_aviso(tmp_path):
    """100 + 15 = 115: el escaneo de una factura con totales correctos no avisa."""
    scan = _scan_con_totales(tmp_path, 115.00)
    out = tmp_path / "t.xlsx"
    info = convert(str(scan), str(out), "excel")
    assert info.get("totals_warning") is None, info
    assert not (info.get("ocr_warning") or "").count("no coincide")


def test_check_totals_unidad():
    """check_totals solo, sin OCR: cuadra -> None; no cuadra -> aviso con valores."""
    from app.converters.extract import Segment
    from app.converters.numbers import parse_number
    from app.converters.pdf_to_excel import Placement, check_totals

    def pls(rows):
        out = []
        for r, (label, val) in enumerate(rows):
            out.append(Placement(r, 0, Segment(label, 0, 0, 10, 10, "Calibri", 10.0, False, False, "000000"), "left", None, None))
            out.append(Placement(r, 1, Segment(f"$ {val:,.2f}", 0, 0, 10, 10, "Calibri", 10.0, False, False, "000000"),
                                 "right", None, parse_number(f"$ {val:,.2f}")))
        return out

    assert check_totals(pls([("SUBTOTAL", 335.0), ("IVA 15%", 50.25), ("TOTAL", 385.25)])) is None
    bad = check_totals(pls([("SUBTOTAL", 335.0), ("IVA 15%", 50.25), ("TOTAL", 400.0)]))
    assert bad is not None and "no coincide" in bad["message"]
    assert bad["subtotal"] == 335.0 and bad["iva"] == 50.25 and bad["total"] == 400.0
    assert len(bad["cells"]) == 3
    assert check_totals(pls([("TOTAL", 385.25)])) is None  # sin SUBTOTAL/IVA no se valida


def test_merge_currency_with_number_unidad():
    """'$' suelto + cifra en la misma celda -> una sola celda '$ 0.50' (sin
    cambiar el valor); en celdas distintas no se tocan."""
    from app.converters.extract import Segment
    from app.converters.numbers import parse_number
    from app.converters.pdf_to_excel import Placement, _merge_currency_with_number

    cur = Placement(0, 1, Segment("$", 0, 0, 5, 10, "Calibri", 10.0, False, False, "000000"), "left", None, None)
    num = Placement(0, 1, Segment("0.50", 6, 0, 20, 10, "Calibri", 10.0, False, False, "000000"), "right", None, parse_number("0.50"))
    merged = _merge_currency_with_number([cur, num])
    assert len(merged) == 1
    assert merged[0].seg.text == "$ 0.50" and merged[0].parsed.value == 0.5
    assert merged[0].parsed.number_format.startswith('"$"')

    other = Placement(0, 2, Segment("0.50", 6, 0, 20, 10, "Calibri", 10.0, False, False, "000000"), "right", None, parse_number("0.50"))
    assert len(_merge_currency_with_number([cur, other])) == 2


# ------------------------------------------------------- quality: qué falta

@pytest.mark.parametrize("target,ext", [("excel", "xlsx"), ("word", "docx"), ("pptx", "pptx")])
def test_quality_missing_sample_nombra_las_palabras_que_faltan(tmp_path, target, ext):
    """Si falta una palabra en la salida, quality.missing_sample la nombra en
    los tres destinos (la API devuelve info['quality'] tal cual)."""
    from app.converters.verify import verify

    out = tmp_path / f"q.{ext}"
    info = convert(str(FIX / "factura.pdf"), str(out), target)
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["missing_sample"] == []
    # Borrar "Pintura" de la salida y volver a verificar.
    if target == "excel":
        wb = load_workbook(out)
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if c.value == "Pintura blanca 1 galón":
                        c.value = None
        wb.save(out)
    elif target == "word":
        doc = Document(out)
        for t in doc.tables:
            for r in t.rows:
                for cell in r.cells:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            if "Pintura" in run.text:
                                run.text = run.text.replace("Pintura", "")
        doc.save(out)
    else:
        prs = Presentation(out)
        for s in prs.slides:
            for sh in s.shapes:
                if sh.has_table:
                    for r in sh.table.rows:
                        for cell in r.cells:
                            for p in cell.text_frame.paragraphs:
                                for run in p.runs:
                                    if "Pintura" in run.text:
                                        run.text = run.text.replace("Pintura", "")
        prs.save(out)
    q = verify(str(FIX / "factura.pdf"), str(out), target)
    assert q["text_coverage"] < 1.0
    assert "pintura" in q["missing_sample"], q
