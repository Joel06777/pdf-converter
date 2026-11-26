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


# ----------------------------------------------------------------- generalización

def _es_escaneado(doc: pymupdf.Document) -> bool:
    """¿Alguna página es un escaneo sin capa de texto? Misma condición que
    app/converters/extract.py (imagen >=80 % de la página y <20 caracteres
    nativos), pero sin ejecutar el OCR: solo decide si el fixture usa la
    ruta OCR de Word, que no inserta imágenes ancladas.
    """
    for page in doc:
        rect = page.rect
        if len(page.get_text().strip()) >= 20:
            continue
        for info in page.get_image_info(xrefs=True):
            bbox = pymupdf.Rect(info["bbox"]) & rect
            if not bbox.is_empty and bbox.width * bbox.height >= 0.80 * rect.width * rect.height:
                return True
    return False


def _all_fixtures():
    return sorted((Path(__file__).parent / "fixtures").glob("*.pdf"))


@pytest.mark.parametrize("pdf", _all_fixtures(), ids=lambda p: p.name)
def test_word_imagenes_ancladas_sin_solape_estructural_todos(tmp_path, pdf):
    """Generalización a todos los fixtures: ninguna imagen anclada comparte
    párrafo con texto ni excede el ancho disponible de la página.

    El caso que lo motivó es el QR de firmas del documento de referencia
    (test_word_qr_sin_solape_estructural), pero la invariante vale para
    cualquier fixture con imágenes (logos, sellos, QR). Los escaneos no se
    convierten: su ruta OCR no inserta imágenes en el .docx, así que la
    invariante se cumple por construcción y convertirlos aquí solo sumaría
    minutos de Tesseract a la suite.
    """
    doc = pymupdf.open(pdf)
    try:
        if _es_escaneado(doc):
            return
    finally:
        doc.close()
    out = tmp_path / "o.docx"
    convert(str(pdf), str(out), "word")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    if "<wp:anchor" not in xml:
        return
    doc = Document(out)
    content_w = doc.sections[0].page_width.pt - doc.sections[0].left_margin.pt - doc.sections[0].right_margin.pt
    with_images = [(t, has) for t, has in _paragraphs_with_images(out) if has]
    assert with_images, f"{pdf.name}: hay anclas pero ningún párrafo con imagen"
    assert all(not text.strip() for text, _ in with_images), (
        f"{pdf.name}: una imagen comparte párrafo con texto: {[t for t, _ in with_images if t.strip()][:2]}")
    for cx, cy in re.findall(r"<wp:extent cx=\"(\d+)\" cy=\"(\d+)\"", xml):
        assert int(cx) / 12700 <= content_w + 0.5, f"{pdf.name}: imagen de {int(cx) / 12700:.1f} pt en {content_w:.1f} pt"


def _fixtures_con_imagenes_ancladas():
    """Fixtures cuyo .docx lleva imágenes ancladas (logos, sellos, QR).

    Detección barata por el modelo de extracción (sin convertir): página con
    imágenes y texto nativo. Los escaneos (ruta OCR) no anclan imágenes y la
    ruta flow de pdf2docx no usa wp:anchor; en la práctica son los 3 fixtures
    de la ruta grid con imágenes.
    """
    out = []
    for pdf in _all_fixtures():
        doc = pymupdf.open(pdf)
        try:
            # ocr=False: no se ejecuta Tesseract en la detección (los escaneos
            # tardarían minutos); las imágenes vectoriales (logos, sellos)
            # igual se rasterizan en el modelo.
            if any((m := extract_page(doc, p, ocr=False)).images and not m.scanned for p in doc):
                out.append(pdf)
        finally:
            doc.close()
    return out


@needs_soffice
@pytest.mark.parametrize("pdf", _fixtures_con_imagenes_ancladas(), ids=lambda p: p.name)
def test_word_imagenes_sin_solape_renderizado_todos(tmp_path, pdf):
    """Render real con LibreOffice para cada fixture con imágenes ancladas:
    ningún texto que en el PDF original está FUERA de las imágenes puede
    acabar encima de una imagen en el Word.

    El texto que en el original ya cae dentro de una imagen (p. ej. "PAGADO"
    estampado sobre el sello, o las letras del logo) sí puede solaparse: es
    parte del gráfico, no un desplazamiento. Lo que no puede pasar es lo del
    bug original: texto de firmas desplazado sobre los QR.
    """
    out = tmp_path / "o.docx"
    convert(str(pdf), str(out), "word")
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf",
                    "--outdir", str(render_dir), str(out)],
                   check=True, capture_output=True, timeout=120)
    rendered = pymupdf.open(render_dir / "o.pdf")

    # Rectángulos de TINTA de las imágenes en el PDF original (modelo de
    # extracción: incluye los gráficos vectoriales rasterizados, como sellos
    # y logos). No basta el rectángulo de la imagen: el logo de la
    # referencia, p. ej., tiene su tinta hasta x=199 aunque su rectángulo
    # llegue a 203,9, y el texto del encabezado (que en el original empieza
    # en 205,4) lo roza al refluir en LibreOffice sin tapar nada visible.
    # En cambio un QR llena de tinta todo su rectángulo: cualquier texto
    # encima es un solape real.
    from io import BytesIO

    import numpy as np
    from PIL import Image as _Image

    def _ink_rect(img) -> pymupdf.Rect:
        pil = _Image.open(BytesIO(img.png)).convert("RGBA")
        a = np.asarray(pil)
        ink = (a[..., :3].min(axis=2) < 240) & (a[..., 3] > 30)
        ys, xs = np.where(ink)
        if len(xs) == 0:
            return pymupdf.Rect(img.x0, img.y0, img.x1, img.y1)
        w, h = img.x1 - img.x0, img.y1 - img.y0
        return pymupdf.Rect(
            img.x0 + xs.min() / pil.width * w, img.y0 + ys.min() / pil.height * h,
            img.x0 + (xs.max() + 1) / pil.width * w, img.y0 + (ys.max() + 1) / pil.height * h)

    src_doc = pymupdf.open(pdf)
    src_ink: list[list[tuple[pymupdf.Rect, pymupdf.Rect]]] = []  # (rectángulo, tinta)
    src_spans: list[list[tuple[str, pymupdf.Rect]]] = []
    for page in src_doc:
        model = extract_page(src_doc, page)
        src_ink.append([(pymupdf.Rect(i.x0, i.y0, i.x1, i.y1), _ink_rect(i)) for i in model.images])
        spans = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for line in b["lines"]:
                for s in line["spans"]:
                    spans.append((s["text"].strip(), pymupdf.Rect(s["bbox"])))
        src_spans.append(spans)

    def _overlaps(a: pymupdf.Rect, b: pymupdf.Rect) -> bool:
        ox = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
        oy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
        return ox > 1 and oy > 1

    for n, page in enumerate(rendered):
        images = [r for img in page.get_images(full=True) for r in page.get_image_rects(img[0])]
        spans = [(s["text"].strip(), pymupdf.Rect(s["bbox"]))
                 for b in page.get_text("dict")["blocks"] if b["type"] == 0
                 for line in b["lines"] for s in line["spans"] if s["text"].strip()]
        for r in images:
            # Tinta de ESTA imagen en el render: se busca la imagen original
            # por cercanía de centro (las ancladas van en su posición del PDF)
            # y se trasladan sus fracciones de tinta al rectángulo renderizado.
            best, best_d = None, 1e9
            for full, ink in src_ink[n]:
                d = abs((full.x0 + full.x1) / 2 - (r.x0 + r.x1) / 2) + abs((full.y0 + full.y1) / 2 - (r.y0 + r.y1) / 2)
                if d < best_d:
                    best, best_d = (full, ink), d
            if best is not None and best_d < 10:
                (full, ink) = best
                fx0 = (ink.x0 - full.x0) / max(1.0, full.x1 - full.x0)
                fx1 = (ink.x1 - full.x0) / max(1.0, full.x1 - full.x0)
                fy0 = (ink.y0 - full.y0) / max(1.0, full.y1 - full.y0)
                fy1 = (ink.y1 - full.y0) / max(1.0, full.y1 - full.y0)
                ink_r = pymupdf.Rect(r.x0 + fx0 * (r.x1 - r.x0), r.y0 + fy0 * (r.y1 - r.y0),
                                     r.x0 + fx1 * (r.x1 - r.x0), r.y0 + fy1 * (r.y1 - r.y0))
            else:
                ink_r = r
            for text, bbox in spans:
                if not _overlaps(ink_r, bbox):
                    continue
                # ¿Ese texto ya estaba sobre la tinta de una imagen en el original?
                src_hit = any(
                    _overlaps(sr, sb)
                    for _, sr in src_ink[n]
                    for st, sb in src_spans[n]
                    if st == text
                )
                assert src_hit, (
                    f"{pdf.name} pág {n + 1}: texto {text!r} en "
                    f"{[round(v, 1) for v in (bbox.x0, bbox.y0, bbox.x1, bbox.y1)]} se solapa "
                    f"con una imagen en {[round(v, 1) for v in (r.x0, r.y0, r.x1, r.y1)]} "
                    f"sin estar sobre ninguna imagen en el original")
