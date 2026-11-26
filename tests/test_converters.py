"""Pruebas de aceptación. El PDF real de Punta Esmeralda es el caso de referencia."""
from pathlib import Path

import pymupdf
import pytest
from openpyxl import load_workbook

from app.converters import convert
from app.converters.numbers import parse_number

FIX = Path(__file__).parent / "fixtures" / "estado_ingresos_octubre_2026.pdf"


def test_parse_number():
    assert parse_number("28,949.40").value == 28949.40
    assert parse_number("1.234,56").value == 1234.56
    assert parse_number("(1,500.00)").value == -1500.0
    assert parse_number("$ 30,570.51").value == 30570.51
    assert parse_number("0993132977001") is None  # RUC: se queda como texto
    assert parse_number("0418-2018") is None
    assert parse_number("01-Octubre-26") is None


def test_excel_values_match_pdf(tmp_path):
    out = tmp_path / "o.xlsx"
    info = convert(str(FIX), str(out), "excel")
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0
    ws = load_workbook(out).active
    values = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, (int, float))]
    assert 30570.51 in values and 27948.96 in values and 2621.55 in values
    assert 28949.4 in values
    # el saldo del documento = ingresos - egresos
    assert round(30570.51 - 27948.96, 2) == 2621.55
    assert len(ws._images) >= 1  # logo y QR


def test_excel_keeps_fills_and_merges(tmp_path):
    out = tmp_path / "o.xlsx"
    convert(str(FIX), str(out), "excel")
    ws = load_workbook(out).active
    fills = {c.fill.start_color.rgb[-6:] for row in ws.iter_rows() for c in row if c.fill.fill_type == "solid"}
    assert "8ED973" in fills
    assert ws.merged_cells.ranges


@pytest.mark.parametrize("target,ext", [("word", "docx"), ("pptx", "pptx")])
def test_word_and_pptx_full_coverage(tmp_path, target, ext):
    out = tmp_path / f"o.{ext}"
    info = convert(str(FIX), str(out), target)
    assert info["quality"]["number_coverage"] == 1.0
    assert info["quality"]["text_coverage"] >= 0.99


def _make_scan(tmp_path) -> Path:
    """Convierte el PDF de referencia en un escaneo (solo imagen, sin texto)."""
    src = pymupdf.open(FIX)
    pix = src[0].get_pixmap(dpi=200)
    scan = pymupdf.open()
    page = scan.new_page(width=src[0].rect.width, height=src[0].rect.height)
    page.insert_image(page.rect, pixmap=pix)
    path = tmp_path / "scan.pdf"
    scan.save(path)
    return path


def test_scanned_pdf_uses_ocr(tmp_path):
    scan = _make_scan(tmp_path)
    out = tmp_path / "s.xlsx"
    info = convert(str(scan), str(out), "excel")
    assert info["ocr_pages"] == 1
    ws = load_workbook(out).active
    values = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, (int, float))]
    # El OCR debe recuperar las cifras principales
    for expected in (30570.51, 27948.96, 2621.55):
        assert expected in values, f"OCR no recuperó {expected}"


def test_scanned_accuracy_vs_original(tmp_path):
    """Mide la precisión del OCR: cuántas cifras del original se recuperan en el escaneo."""
    from app.converters.verify import pdf_tokens, xlsx_tokens

    scan = _make_scan(tmp_path)
    out = tmp_path / "s.xlsx"
    convert(str(scan), str(out), "excel")
    expected = {k: v for k, v in pdf_tokens(str(FIX)).items() if k[0] == "n"}
    got = xlsx_tokens(str(out))
    hit = sum(min(v, got.get(k, 0)) for k, v in expected.items())
    ratio = hit / sum(expected.values())
    print(f"precisión numérica OCR: {ratio:.1%}")
    assert ratio >= 0.97
