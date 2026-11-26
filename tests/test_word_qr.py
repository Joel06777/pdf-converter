"""QR solapado con texto en el Word del estado de ingresos (zona de firmas).

Reproduce el fallo: en el .docx del fixture de referencia, el texto de las
firmas caía sobre los códigos QR. Causas corregidas en pdf_to_word.py:
la cuadrícula de la tabla usaba columnas iguales (el layout fijo ignora
cell.width) y el "desbordar" de un texto alineado a la derecha se tragaba
la celda fusionada vecina, metiendo dos textos en un mismo párrafo.
"""
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pymupdf
import pytest
from docx import Document
from docx.oxml.ns import qn

from app.converters import convert
from app.converters.extract import extract_page
from app.converters.pdf_to_excel import build_layout

FIX = Path(__file__).parent / "fixtures" / "estado_ingresos_octubre_2026.pdf"
SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
needs_soffice = pytest.mark.skipif(not SOFFICE, reason="LibreOffice no instalado")


def _convert(tmp_path):
    out = tmp_path / "estado.docx"
    info = convert(str(FIX), str(out), "word")
    return out, info


def _paragraphs_with_images(docx_path):
    """Párrafos (cuerpo y celdas) que contienen una imagen, con su texto."""
    doc = Document(docx_path)
    paras = list(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                paras.extend(cell.paragraphs)
    return [(p.text, "blip" in p._p.xml or "wp:anchor" in p._p.xml) for p in paras]


def test_word_qr_sin_solape_estructural(tmp_path):
    out, info = _convert(tmp_path)
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0

    doc = Document(out)
    section = doc.sections[0]
    content_w = section.page_width.pt - section.left_margin.pt - section.right_margin.pt

    # 1) Las 5 imágenes están ancladas en un párrafo propio y vacío (sin texto).
    # Comparten un único párrafo vacío tras la tabla: lo que importa es que
    # ninguna comparte párrafo con texto.
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert len(re.findall(r"<wp:anchor", xml)) == 5, "se esperaban 5 imágenes ancladas"
    with_images = [(t, has) for t, has in _paragraphs_with_images(out) if has]
    assert with_images, "no hay ningún párrafo con imágenes"
    assert all(not text.strip() for text, _ in with_images), "una imagen comparte párrafo con texto"

    # 2) Ninguna imagen excede el ancho disponible de la página.
    for cx, cy in re.findall(r"<wp:extent cx=\"(\d+)\" cy=\"(\d+)\"", xml):
        assert int(cx) / 12700 <= content_w + 0.5, f"imagen de {int(cx) / 12700:.1f} pt en {content_w:.1f} pt"

    # 3) La cuadrícula de la tabla usa los anchos reales de columna del PDF
    # (sin esto el texto se desplaza y cae sobre los QR).
    pymu_doc = pymupdf.open(FIX)
    model = extract_page(pymu_doc, pymu_doc[0])
    cols = build_layout(model).cols
    grid = [int(gc.get(qn("w:w"))) for gc in doc.tables[0]._tbl.find(qn("w:tblGrid"))]
    assert len(grid) == len(cols)
    for got, col in zip(grid, cols):
        assert abs(got - (col.right - col.left) * 20) <= 2, f"columna {got} twips != {(col.right - col.left) * 20:.0f}"


@needs_soffice
def test_word_qr_sin_solape_renderizado(tmp_path):
    """Render real con LibreOffice: ningún QR de firmas se solapa con texto."""
    out, info = _convert(tmp_path)
    assert info["quality"]["text_coverage"] == 1.0
    pdf_dir = tmp_path / "render"
    pdf_dir.mkdir()
    subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf",
                    "--outdir", str(pdf_dir), str(out)],
                   check=True, capture_output=True, timeout=120)
    rendered = pymupdf.open(pdf_dir / "estado.pdf")
    assert rendered.page_count == 1
    page = rendered[0]

    images = [r for img in page.get_images(full=True) for r in page.get_image_rects(img[0])]
    qr = [r for r in images if r.y0 >= 690 and abs(r.width - 36) < 1 and abs(r.height - 36) < 1]
    assert len(qr) == 3, f"se esperaban 3 QR de 36x36 pt en firmas, hay {len(qr)}: {qr}"

    spans = [s["bbox"] for b in page.get_text("dict")["blocks"] if b["type"] == 0
             for line in b["lines"] for s in line["spans"]]
    for r in qr:
        for bbox in spans:
            ox = max(0.0, min(r.x1, bbox[2]) - max(r.x0, bbox[0]))
            oy = max(0.0, min(r.y1, bbox[3]) - max(r.y0, bbox[1]))
            assert not (ox > 1 and oy > 1), (
                f"QR en {[round(v, 1) for v in (r.x0, r.y0, r.x1, r.y1)]} se solapa "
                f"{ox:.1f}x{oy:.1f} pt con texto en {[round(v, 1) for v in bbox]}")
