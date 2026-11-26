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
