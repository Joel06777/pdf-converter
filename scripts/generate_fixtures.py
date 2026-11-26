"""Genera los PDFs de prueba de tests/fixtures/ con PyMuPDF (sin servicios externos).

Uso:  python scripts/generate_fixtures.py
Los archivos generados son deterministas: mismo contenido en cada ejecución.
"""
from __future__ import annotations

import math
from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
W, H = 595, 842  # A4 en puntos


def _text(page, x, y, text, size=10, font="helv", color=(0, 0, 0)):
    page.insert_text((x, y), text, fontsize=size, fontname=font, color=color)


def _line(page, x0, y0, x1, y1, width=0.7):
    page.draw_line((x0, y0), (x1, y1), color=(0, 0, 0), width=width)


def _table(page, x, y, col_x, rows, row_h=20, size=10, header=True, lines=True):
    """Dibuja una tabla simple. col_x: posiciones x de cada columna (incluye borde der.)."""
    if header:
        page.draw_rect(pymupdf.Rect(x, y, col_x[-1], y + row_h), color=(0.2, 0.4, 0.2), fill=(0.55, 0.85, 0.55))
    for i, row in enumerate(rows):
        yy = y + i * row_h
        for j, cell in enumerate(row):
            bold = header and i == 0
            _text(page, col_x[j] + 5, yy + 14, cell, size=size, font="hebo" if bold else "helv")
        if lines:
            _line(page, x, yy + row_h, col_x[-1], yy + row_h)
    if lines:
        for cx in [x, *col_x]:
            _line(page, cx, y, cx, y + len(rows) * row_h)
    return y + len(rows) * row_h


def factura(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "FACTURA Nº 001-002-0001234", size=16, font="hebo")
    _text(page, 40, 75, "Ferretería El Tornillo S.A.", size=12, font="hebo")
    _text(page, 40, 95, "RUC: 0993132977001", size=10)
    _text(page, 40, 115, "Cliente: Asociación de Propietarios Punta Esmeralda", size=10)
    _text(page, 40, 135, "Fecha: 15 de octubre de 2026", size=10)
    rows = [
        ["Descripción", "Cantidad", "Precio Unit.", "Total"],
        ["Tornillos galvanizados", "100", "$ 0.50", "$ 50.00"],
        ["Pintura blanca 1 galón", "5", "$ 25.00", "$ 125.00"],
        ["Cable eléctrico 100 m", "2", "$ 80.00", "$ 160.00"],
        ["TOTAL", "", "", "$ 335.00"],
    ]
    _table(page, 40, 170, [40, 300, 370, 460, 555], rows)
    _text(page, 40, 320, "Gracias por su compra. Valores en dólares americanos.", size=9)
    doc.save(path)


def estado_cuenta(path: Path) -> None:
    doc = pymupdf.open()
    for n in range(1, 4):
        page = doc.new_page(width=W, height=H)
        _text(page, 40, 50, "ESTADO DE CUENTA — BANCO EJEMPLO", size=13, font="hebo")
        _text(page, 40, 72, f"Página {n} de 3 — Octubre 2026", size=10)
        rows = [["Fecha", "Descripción", "Débito", "Crédito", "Saldo"]]
        saldo = 1000.00 + (n - 1) * 100
        for i in range(1, 9):
            debito = 50.00 * i
            saldo -= debito
            rows.append([f"0{i}/10/2026", f"Pago proveedor {i}", f"$ {debito:,.2f}", "$ 0.00", f"$ {saldo:,.2f}"])
        rows.append(["TOTAL", "", f"$ {sum(50.0 * i for i in range(1, 9)):,.2f}", "$ 0.00", f"$ {saldo:,.2f}"])
        _table(page, 40, 110, [40, 110, 330, 400, 470, 555], rows, row_h=22)
    doc.save(path)


def tabla_sin_lineas(path: Path) -> None:
    """Tabla sin líneas de rejilla: solo columnas alineadas por espacios."""
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "RESUMEN MENSUAL SIN LÍNEAS", size=14, font="hebo")
    y = 100
    for line in [
        ("Concepto", "Ene", "Feb", "Mar"),
        ("Cuotas ordinarias", "$ 1,200.00", "$ 1,200.00", "$ 1,250.00"),
        ("Cuotas extraordinarias", "$ 300.00", "$ 0.00", "$ 150.00"),
        ("Mantenimiento", "$ 450.50", "$ 480.00", "$ 470.25"),
        ("TOTAL", "$ 1,950.50", "$ 1,680.00", "$ 1,870.25"),
    ]:
        _text(page, 40, y, line[0], size=11, font="hebo" if line[0] in ("Concepto", "TOTAL") else "helv")
        _text(page, 300, y, line[1], size=11)
        _text(page, 400, y, line[2], size=11)
        _text(page, 490, y, line[3], size=11)
        y += 24
    doc.save(path)


def celdas_combinadas(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "FLUJO POR CATEGORÍA", size=14, font="hebo")
    # Relleno que abarca las filas de cada categoría (así el PDF marca la fusión vertical).
    page.draw_rect(pymupdf.Rect(40, 112, 150, 178), color=(0.9, 0.95, 0.9), fill=(0.9, 0.95, 0.9))
    page.draw_rect(pymupdf.Rect(40, 178, 150, 222), color=(0.95, 0.9, 0.9), fill=(0.95, 0.9, 0.9))
    # Columna "Categoría" con celdas que abarcan varias filas (fusión vertical).
    _table(page, 40, 90, [40, 150, 400, 555],
           [["Categoría", "Concepto", "Valor"],
            ["Ingresos", "Cuotas", "$ 2,000.00"],
            ["", "Alquiler salón", "$ 300.00"],
            ["", "Intereses", "$ 45.50"],
            ["Egresos", "Limpieza", "$ 400.00"],
            ["", "Seguridad", "$ 650.00"],
            ["TOTAL", "", "$ 1,295.50"]], row_h=22)
    doc.save(path)


def dos_columnas(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "BOLETÍN DE LA COMUNIDAD", size=14, font="hebo")
    left = ("La asociación informa a los vecinos que el mantenimiento de las áreas "
            "verdes se realizará el próximo sábado. Se solicita no estacionar "
            "frente a la garita durante la jornada de limpieza y pintura.")
    right = ("También se recuerda que la cuota de octubre vence el día 15. "
             "Los pagos pueden realizarse por transferencia o en la oficina "
             "de administración, de lunes a viernes, de 09:00 a 17:00.")
    # Texto corrido en dos columnas (rectángulos separados).
    for text, rect in ((left, pymupdf.Rect(40, 80, 280, 400)),
                       (right, pymupdf.Rect(310, 80, 555, 400))):
        rc = page.insert_textbox(rect, text, fontsize=11, fontname="helv")
        assert rc >= 0, "el texto no cupo en la columna"
    doc.save(path)


def acentos(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "ACTA CON ACENTOS Y SÍMBOLOS", size=14, font="hebo")
    lines = [
        "El señor Muñoz, dueño del local, pagó $ 1,234.56 por la reparación.",
        "La niña Ana María llevó piña, jamón y café a la reunión del comité.",
        "Cédula: 0923456789 — Teléfono: 0998765432 — RUC: 0993132977001.",
        "El camión costó $ 45,678.90 y el interés fue de 12.5% anual.",
        "Árbol, lápiz, música, fútbol, teléfono, único, público, Ñandú.",
    ]
    y = 90
    for line in lines:
        _text(page, 40, y, line, size=11)
        y += 24
    doc.save(path)


def _render_only(src_doc: pymupdf.Document, path: Path, rotate: float = 0.0) -> None:
    """Guarda un PDF que solo contiene la imagen de la primera página (escaneo)."""
    page = src_doc[0]
    pix = page.get_pixmap(dpi=200)
    out = pymupdf.open()
    new = out.new_page(width=page.rect.width, height=page.rect.height)
    # JPEG (calidad 90) para que el escaneo no pese 10+ MB como PNG sin comprimir.
    from io import BytesIO

    from PIL import Image

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if rotate:
        # Foto ligeramente inclinada: se gira la imagen con Pillow (fondo blanco).
        img = img.rotate(rotate, expand=False, fillcolor="white", resample=Image.BICUBIC)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    new.insert_image(new.rect, stream=buf.getvalue())
    out.save(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    factura(OUT / "factura.pdf")
    estado_cuenta(OUT / "estado_cuenta_multipagina.pdf")
    tabla_sin_lineas(OUT / "tabla_sin_lineas.pdf")
    celdas_combinadas(OUT / "celdas_combinadas.pdf")
    dos_columnas(OUT / "dos_columnas.pdf")
    acentos(OUT / "acentos.pdf")
    # Escaneados: se generan a partir de la factura (documento con cifras conocidas).
    tmp = pymupdf.open()
    factura(OUT / "_tmp_factura.pdf")
    src = pymupdf.open(OUT / "_tmp_factura.pdf")
    _render_only(src, OUT / "escaneado.pdf")
    _render_only(src, OUT / "foto_inclinada.pdf", rotate=3.0)
    (OUT / "_tmp_factura.pdf").unlink()
    for p in sorted(OUT.glob("*.pdf")):
        print(p.name, p.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
