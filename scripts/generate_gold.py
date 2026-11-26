"""Genera el conjunto de oro de PDFs de prueba (Fase 2).

Uso:  python scripts/generate_gold.py

Genera por código 28 PDFs nuevos en tests/fixtures/ (además de los 14 que ya
genera scripts/generate_fixtures.py) hasta un total de 42, y escribe
tests/fixtures/gold_manifest.json con la verdad de referencia de cada PDF
(texto, cifras, tablas, celdas combinadas, rellenos e imágenes).

Todo es determinista: datos fijos en el código, sin fechas del sistema ni
azar; los metadatos de creación/modificación de cada PDF son fijos.

Tipos cubiertos: facturas, estados de cuenta de varias páginas, estados
financieros, tablas sin líneas, celdas combinadas, dos columnas, formularios,
contratos, escaneos limpios, color con sello o marca de agua, y fotos de
celular con perspectiva.
"""
from __future__ import annotations

import json
import re
import sys
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

# La interpretación de cifras es la misma que usa el conversor
# (app/converters/numbers.py): "12.5%" vale 0.125, y los códigos como el RUC
# o la cédula se quedan como texto, no como número.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.converters.numbers import parse_number  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
MANIFEST = OUT / "gold_manifest.json"
W, H = 595, 842  # A4 en puntos
FIXED_META = {
    "creationDate": "D:20260101090000-05'00'",
    "modDate": "D:20260101090000-05'00'",
    "producer": "pdf-converter gold generator",
    "creator": "pdf-converter gold generator",
}

def _text(page, x, y, text, size=10, font="helv", color=(0, 0, 0)):
    page.insert_text((x, y), text, fontsize=size, fontname=font, color=color)


def _line(page, x0, y0, x1, y1, width=0.7, color=(0, 0, 0)):
    page.draw_line((x0, y0), (x1, y1), color=color, width=width)


def _money(v: float) -> str:
    return f"$ {v:,.2f}"


def _table(page, x, y, col_x, rows, row_h=20, size=10, header=True,
           lines=True, fills=None, header_fill=(0.55, 0.85, 0.55)):
    """Dibuja una tabla simple. `fills`: {(fila, col): (r, g, b)} o
    {(fila, None): color} para toda la fila."""
    fills = fills or {}
    if header:
        page.draw_rect(pymupdf.Rect(x, y, col_x[-1], y + row_h),
                       color=(0.2, 0.4, 0.2), fill=header_fill)
    for i, row in enumerate(rows):
        yy = y + i * row_h
        for j, cell in enumerate(row):
            fill = fills.get((i, j)) or fills.get((i, None))
            if fill is not None:
                page.draw_rect(pymupdf.Rect(col_x[j], yy, col_x[j + 1], yy + row_h),
                               color=fill, fill=fill)
            bold = header and i == 0
            _text(page, col_x[j] + 5, yy + 14, cell, size=size,
                  font="hebo" if bold else "helv")
        if lines:
            _line(page, x, yy + row_h, col_x[-1], yy + row_h)
    if lines:
        for cx in [x, *col_x]:
            _line(page, cx, y, cx, y + len(rows) * row_h)
    return y + len(rows) * row_h


def _finish(doc: pymupdf.Document, title: str) -> pymupdf.Document:
    meta = dict(FIXED_META)
    meta["title"] = title
    doc.set_metadata(meta)
    return doc


def _num_of(token: str):
    """Número (float) si el token es numérico según parse_number, o None."""
    p = parse_number(token)
    return p.value if p else None


def _ground_truth(doc: pymupdf.Document) -> dict:
    """Verdad de referencia extraída del PDF nativo: palabras y cifras."""
    numbers: list[float] = []
    words: set[str] = set()
    for page in doc:
        for w in page.get_text("words"):
            tok = w[4]
            n = _num_of(tok)
            if n is not None:
                numbers.append(n)
            elif tok != "$":
                words.add(tok.casefold())
    return {"numbers": sorted(numbers), "texts": sorted(words)}


def _meta(doc: pymupdf.Document, name: str, kind: str, tables=None,
          merged=None, fills=None, scanned=False, notes="") -> dict:
    gt = _ground_truth(doc)
    images = sum(len(p.get_images(full=True)) for p in doc)
    return {
        "file": name,
        "kind": kind,
        "pages": doc.page_count,
        "numbers": gt["numbers"],
        "texts": gt["texts"],
        "tables": tables or [],
        "merged": merged or [],
        "fills": fills or [],
        "images": images,
        "scanned": scanned,
        "notes": notes,
    }


def _save(doc: pymupdf.Document, path: Path) -> None:
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    # PyMuPDF escribe un /ID aleatorio en el tráiler: lo fijamos a ceros
    # (misma longitud) para que el archivo sea idéntico byte a byte en cada
    # ejecución. El /ID está en el tráiler, tras la tabla xref, así que no
    # afecta a los offsets.
    data = path.read_bytes()

    def _zero_id(m: re.Match) -> bytes:
        return (b"/ID [<" + b"0" * len(m.group(1)) + b"><"
                + b"0" * len(m.group(2)) + b">]")

    fixed = re.sub(rb"/ID\s*\[\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\]",
                   _zero_id, data, count=1)
    if fixed != data:
        path.write_bytes(fixed)


# ------------------------------------------------------------------ facturas

def factura_servicios(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "FACTURA Nº 001-003-0000456", size=16, font="hebo")
    _text(page, 40, 75, "Servicios Generales del Litoral S.A.", size=12, font="hebo")
    _text(page, 40, 95, "RUC: 0998765432001", size=10)
    _text(page, 40, 115, "Cliente: Asociación de Propietarios Punta Esmeralda", size=10)
    _text(page, 40, 135, "Fecha: 02 de noviembre de 2026", size=10)
    rows = [
        ["Descripción", "Cantidad", "Precio Unit.", "Total"],
        ["Limpieza de oficinas", "4", "$ 120.00", "$ 480.00"],
        ["Mantenimiento de jardines", "2", "$ 250.00", "$ 500.00"],
        ["Seguridad mensual", "1", "$ 650.00", "$ 650.00"],
        ["SUBTOTAL", "", "", "$ 1,630.00"],
        ["Descuento 5%", "", "", "$ -81.50"],
        ["IVA 15%", "", "", "$ 232.28"],
        ["TOTAL", "", "", "$ 1,780.78"],
    ]
    _table(page, 40, 170, [40, 300, 370, 460, 555], rows)
    _text(page, 40, 360, "Servicios prestados en octubre de 2026.", size=9)
    _finish(doc, "Factura servicios")
    meta = _meta(doc, path.name, "factura", tables=[rows])
    _save(doc, path)
    return meta


def factura_detalle_largo(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "FACTURA Nº 001-002-0002001", size=16, font="hebo")
    _text(page, 40, 75, "Ferretería El Tornillo S.A.", size=12, font="hebo")
    _text(page, 40, 95, "RUC: 0993132977001", size=10)
    _text(page, 40, 115, "Cliente: Constructora del Pacífico C.A.", size=10)
    _text(page, 40, 135, "Fecha: 10 de noviembre de 2026", size=10)
    items = [
        ("Tornillos galvanizados", 200, 0.50), ("Tuercas hexagonales", 300, 0.30),
        ("Pintura blanca 1 galón", 3, 30.00), ("Brochas 3 pulgadas", 10, 4.50),
        ("Cable eléctrico 100 m", 5, 80.00), ("Focos LED 12W", 20, 6.25),
        ("Cemento 50 kg", 8, 12.50), ("Arena fina m3", 4, 25.00),
        ("Tubo PVC 2 pulgadas", 15, 3.20), ("Llaves de paso", 6, 15.00),
        ("Candados 40 mm", 12, 8.75), ("Guantes de trabajo", 25, 2.40),
    ]
    rows = [["Descripción", "Cantidad", "Precio Unit.", "Total"]]
    subtotal = 0.0
    for desc, qty, price in items:
        total = round(qty * price, 2)
        subtotal += total
        rows.append([desc, str(qty), _money(price), _money(total)])
    iva = round(subtotal * 0.15, 2)
    rows += [["SUBTOTAL", "", "", _money(subtotal)],
             ["IVA 15%", "", "", _money(iva)],
             ["TOTAL", "", "", _money(subtotal + iva)]]
    _table(page, 40, 170, [40, 300, 370, 460, 555], rows, row_h=19)
    _text(page, 40, 170 + len(rows) * 19 + 20,
          "Entrega en obra: Km 13.5 Vía a la Costa, Guayaquil.", size=9)
    _finish(doc, "Factura detalle largo")
    meta = _meta(doc, path.name, "factura", tables=[rows])
    _save(doc, path)
    return meta


def factura_nota_credito(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "NOTA DE CRÉDITO Nº 001-002-0000033", size=16, font="hebo")
    _text(page, 40, 75, "Ferretería El Tornillo S.A.", size=12, font="hebo")
    _text(page, 40, 95, "RUC: 0993132977001", size=10)
    _text(page, 40, 115, "Cliente: Asociación de Propietarios Punta Esmeralda", size=10)
    _text(page, 40, 135, "Fecha: 12 de noviembre de 2026", size=10)
    _text(page, 40, 155, "Refiere a factura Nº 001-002-0001234", size=10)
    rows = [
        ["Concepto", "Cantidad", "Precio Unit.", "Total"],
        ["Devolución pintura blanca", "1", "$ -150.00", "$ -150.00"],
        ["Descuento por pronto pago", "1", "$ -25.00", "$ -25.00"],
        ["SUBTOTAL", "", "", "$ -175.00"],
        ["IVA 15%", "", "", "$ -26.25"],
        ["TOTAL", "", "", "$ -201.25"],
    ]
    _table(page, 40, 190, [40, 300, 370, 460, 555], rows)
    _finish(doc, "Nota de crédito")
    meta = _meta(doc, path.name, "factura", tables=[rows],
                 notes="Cifras negativas: prueba que el signo se conserva.")
    _save(doc, path)
    return meta


# --------------------------------------------------------- estados de cuenta

def estado_cuenta_6p(path: Path) -> dict:
    doc = pymupdf.open()
    tables = []
    saldo = 5000.00
    for n in range(1, 7):
        page = doc.new_page(width=W, height=H)
        _text(page, 40, 50, "ESTADO DE CUENTA — BANCO EJEMPLO", size=13, font="hebo")
        _text(page, 40, 72, f"Página {n} de 6 — Noviembre 2026", size=10)
        _text(page, 40, 92, f"Saldo inicial de la página: {_money(saldo)}", size=10)
        rows = [["Fecha", "Descripción", "Débito", "Crédito", "Saldo"]]
        total_deb = 0.0
        for i in range(1, 7):
            debito = round(25.00 * i + 10.00 * n, 2)
            saldo = round(saldo - debito, 2)
            total_deb += debito
            rows.append([f"{i:02d}/11/2026", f"Pago proveedor {i} pág. {n}",
                         _money(debito), "$ 0.00", _money(saldo)])
        rows.append(["TOTAL", "", _money(total_deb), "$ 0.00", _money(saldo)])
        _table(page, 40, 120, [40, 110, 330, 400, 470, 555], rows, row_h=22)
        tables.append(rows)
    _finish(doc, "Estado de cuenta 6 páginas")
    meta = _meta(doc, path.name, "estado_cuenta", tables=tables)
    _save(doc, path)
    return meta


def estado_cuenta_tarjeta(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "ESTADO DE CUENTA — TARJETA DE CRÉDITO", size=13, font="hebo")
    _text(page, 40, 72, "Titular: Fabián Alarcón Macías — Corte: 30 de noviembre de 2026", size=10)
    rows = [
        ["Fecha", "Descripción", "Valor"],
        ["01/11/2026", "Saldo anterior", "$ 450.00"],
        ["05/11/2026", "Compra supermercado", "$ 120.00"],
        ["09/11/2026", "Compra ferretería", "$ 85.50"],
        ["14/11/2026", "Compra farmacia", "$ 40.25"],
        ["20/11/2026", "Pago realizado", "$ -200.00"],
        ["30/11/2026", "Intereses del mes", "$ 18.55"],
        ["TOTAL A PAGAR", "", "$ 514.30"],
        ["PAGO MÍNIMO", "", "$ 51.43"],
    ]
    _table(page, 40, 110, [40, 120, 420, 555], rows, row_h=22)
    _text(page, 40, 340, "Fecha límite de pago: 19 de diciembre de 2026.", size=10)
    _finish(doc, "Estado de cuenta tarjeta")
    meta = _meta(doc, path.name, "estado_cuenta", tables=[rows])
    _save(doc, path)
    return meta


# ------------------------------------------------------- estados financieros

def balance_general(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "BALANCE GENERAL — ASOCIACIÓN PUNTA ESMERALDA", size=13, font="hebo")
    _text(page, 40, 72, "Al 30 de noviembre de 2026 — Valores en dólares", size=10)
    rows = [
        ["Cuenta", "Valor"],
        ["ACTIVO CORRIENTE", ""],
        ["Caja", "$ 12,000.00"],
        ["Bancos", "$ 45,000.00"],
        ["Cuentas por cobrar", "$ 18,500.00"],
        ["Inventario", "$ 22,000.00"],
        ["Total activo corriente", "$ 97,500.00"],
        ["ACTIVO FIJO", ""],
        ["Equipos", "$ 30,000.00"],
        ["Depreciación acumulada", "$ -6,000.00"],
        ["Total activo fijo", "$ 24,000.00"],
        ["TOTAL ACTIVO", "$ 121,500.00"],
        ["PASIVO CORRIENTE", ""],
        ["Cuentas por pagar", "$ 15,000.00"],
        ["Préstamos corto plazo", "$ 10,000.00"],
        ["Total pasivo corriente", "$ 25,000.00"],
        ["PASIVO LARGO PLAZO", ""],
        ["Préstamos largo plazo", "$ 30,000.00"],
        ["TOTAL PASIVO", "$ 55,000.00"],
        ["PATRIMONIO", ""],
        ["Capital", "$ 50,000.00"],
        ["Utilidades retenidas", "$ 16,500.00"],
        ["TOTAL PATRIMONIO", "$ 66,500.00"],
        ["TOTAL PASIVO + PATRIMONIO", "$ 121,500.00"],
    ]
    _table(page, 40, 100, [40, 380, 555], rows, row_h=19)
    _text(page, 40, 100 + len(rows) * 19 + 15,
          "El balance cuadra: activo 121,500.00 = pasivo + patrimonio 121,500.00.", size=9)
    _finish(doc, "Balance general")
    meta = _meta(doc, path.name, "estado_financiero", tables=[rows])
    _save(doc, path)
    return meta


def estado_resultados(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "ESTADO DE RESULTADOS — NOVIEMBRE 2026", size=13, font="hebo")
    rows = [
        ["Concepto", "Valor"],
        ["Ingresos por cuotas", "$ 180,000.00"],
        ["Costo de ventas", "$ -95,000.00"],
        ["Utilidad bruta", "$ 85,000.00"],
        ["Gastos de administración", "$ -22,000.00"],
        ["Gastos de ventas", "$ -18,000.00"],
        ["Depreciación", "$ -6,000.00"],
        ["Utilidad operativa", "$ 39,000.00"],
        ["Gastos por intereses", "$ -4,500.00"],
        ["Utilidad antes de impuestos", "$ 34,500.00"],
        ["Impuesto a la renta 25%", "$ -8,625.00"],
        ["UTILIDAD NETA", "$ 25,875.00"],
    ]
    _table(page, 40, 100, [40, 380, 555], rows, row_h=22)
    _finish(doc, "Estado de resultados")
    meta = _meta(doc, path.name, "estado_financiero", tables=[rows])
    _save(doc, path)
    return meta


def flujo_caja(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "FLUJO DE CAJA — NOVIEMBRE 2026", size=13, font="hebo")
    rows = [
        ["Concepto", "Valor"],
        ["Saldo inicial", "$ 60,234.42"],
        ["INGRESOS", ""],
        ["Cuotas ordinarias", "$ 150,000.00"],
        ["Alquiler de salón", "$ 12,000.00"],
        ["Otros ingresos", "$ 3,500.00"],
        ["Total ingresos", "$ 165,500.00"],
        ["EGRESOS", ""],
        ["Nómina", "$ 80,000.00"],
        ["Servicios básicos", "$ 25,000.00"],
        ["Mantenimiento", "$ 18,000.00"],
        ["Otros egresos", "$ 9,500.00"],
        ["Total egresos", "$ 132,500.00"],
        ["FLUJO NETO DEL MES", "$ 33,000.00"],
        ["SALDO FINAL", "$ 93,234.42"],
    ]
    _table(page, 40, 100, [40, 380, 555], rows, row_h=22)
    _finish(doc, "Flujo de caja")
    meta = _meta(doc, path.name, "estado_financiero", tables=[rows])
    _save(doc, path)
    return meta


# --------------------------------------------------------- tablas sin líneas

def tabla_sin_lineas_ventas(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "VENTAS TRIMESTRALES SIN LÍNEAS", size=14, font="hebo")
    data = [
        ("Producto", "Ene", "Feb", "Mar"),
        ("Tornillos", "$ 1,100.00", "$ 1,250.00", "$ 980.00"),
        ("Pintura", "$ 850.50", "$ 920.00", "$ 1,040.25"),
        ("Cable", "$ 640.00", "$ 700.00", "$ 715.50"),
        ("TOTAL", "$ 2,590.50", "$ 2,870.00", "$ 2,735.75"),
    ]
    y = 100
    for line in data:
        bold = line[0] in ("Producto", "TOTAL")
        _text(page, 40, y, line[0], size=11, font="hebo" if bold else "helv")
        _text(page, 280, y, line[1], size=11)
        _text(page, 380, y, line[2], size=11)
        _text(page, 480, y, line[3], size=11)
        y += 24
    _finish(doc, "Tabla sin líneas ventas")
    meta = _meta(doc, path.name, "tabla_sin_lineas", tables=[[list(r) for r in data]])
    _save(doc, path)
    return meta


def tabla_sin_lineas_nomina(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "NÓMINA MENSUAL SIN LÍNEAS", size=14, font="hebo")
    data = [
        ("Empleado", "Sueldo", "Descuento", "Neto"),
        ("Ana Torres", "$ 974.98", "$ 91.22", "$ 883.76"),
        ("Luis Pérez", "$ 1,200.00", "$ 112.32", "$ 1,087.68"),
        ("María Gómez", "$ 850.00", "$ 79.56", "$ 770.44"),
        ("TOTAL", "$ 3,024.98", "$ 283.10", "$ 2,741.88"),
    ]
    y = 100
    for line in data:
        bold = line[0] in ("Empleado", "TOTAL")
        _text(page, 40, y, line[0], size=11, font="hebo" if bold else "helv")
        _text(page, 200, y, line[1], size=11)
        _text(page, 320, y, line[2], size=11)
        _text(page, 440, y, line[3], size=11)
        y += 24
    _finish(doc, "Tabla sin líneas nómina")
    meta = _meta(doc, path.name, "tabla_sin_lineas", tables=[[list(r) for r in data]])
    _save(doc, path)
    return meta


# --------------------------------------------------------- celdas combinadas

def celdas_combinadas_presupuesto(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "PRESUPUESTO MENSUAL POR CATEGORÍA", size=14, font="hebo")
    y = 90
    page.draw_rect(pymupdf.Rect(40, y + 22, 150, y + 88),
                   color=(0.9, 0.95, 0.9), fill=(0.9, 0.95, 0.9))
    page.draw_rect(pymupdf.Rect(40, y + 88, 150, y + 176),
                   color=(0.95, 0.9, 0.9), fill=(0.95, 0.9, 0.9))
    rows = [
        ["Categoría", "Concepto", "Valor"],
        ["Ingresos", "Cuotas ordinarias", "$ 12,000.00"],
        ["", "Alquiler salón", "$ 1,200.00"],
        ["", "Intereses", "$ 145.50"],
        ["Egresos", "Limpieza", "$ 1,800.00"],
        ["", "Seguridad", "$ 2,600.00"],
        ["", "Jardinería", "$ 950.00"],
        ["", "Servicios básicos", "$ 1,150.00"],
        ["TOTAL NETO", "", "$ 6,845.50"],
    ]
    _table(page, 40, y, [40, 150, 400, 555], rows, row_h=22)
    _finish(doc, "Presupuesto celdas combinadas")
    merged = [
        {"rows": [1, 3], "cols": [0, 0], "value": "Ingresos"},
        {"rows": [4, 7], "cols": [0, 0], "value": "Egresos"},
    ]
    fills = [{"rows": [1, 3], "cols": [0, 0], "color": "#E6F2E6"},
             {"rows": [4, 7], "cols": [0, 0], "color": "#F2E6E6"}]
    meta = _meta(doc, path.name, "celdas_combinadas", tables=[rows],
                 merged=merged, fills=fills)
    _save(doc, path)
    return meta


def tabla_encabezado_doble(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "VENTAS POR TRIMESTRE", size=14, font="hebo")
    y = 90
    page.draw_rect(pymupdf.Rect(40, y, 555, y + 20),
                   color=(0.2, 0.4, 0.2), fill=(0.55, 0.85, 0.55))
    title = "VENTAS POR TRIMESTRE 2026"
    tw = pymupdf.get_text_length(title, fontname="hebo", fontsize=12)
    _text(page, 40 + (515 - tw) / 2, y + 15, title, size=12, font="hebo")
    rows = [
        ["Producto", "T1", "T2", "T3", "T4"],
        ["Tornillos", "$ 100.00", "$ 120.00", "$ 110.00", "$ 130.00"],
        ["Pintura", "$ 50.00", "$ 60.00", "$ 55.00", "$ 70.00"],
        ["Cable", "$ 80.00", "$ 75.00", "$ 90.00", "$ 85.00"],
        ["TOTAL", "$ 230.00", "$ 255.00", "$ 255.00", "$ 285.00"],
    ]
    _table(page, 40, y + 20, [40, 180, 255, 330, 405, 555], rows, row_h=22)
    _text(page, 40, y + 20 + len(rows) * 22 + 20,
          "Total anual: $ 1,025.00.", size=10)
    _finish(doc, "Tabla encabezado doble")
    merged = [{"rows": [0, 0], "cols": [0, 4], "value": "VENTAS POR TRIMESTRE 2026"}]
    meta = _meta(doc, path.name, "celdas_combinadas", tables=[rows],
                 merged=merged,
                 notes="Encabezado combinado horizontal sobre 5 columnas.")
    _save(doc, path)
    return meta


def tabla_grande_50_filas(path: Path) -> dict:
    doc = pymupdf.open()
    tables = []
    rows = [["Ítem", "Cantidad", "Precio Unit.", "Total"]]
    for i in range(1, 51):
        rows.append([f"Artículo {i}", str(i), "$ 10.00", _money(i * 10.0)])
    rows.append(["TOTAL", "", "", "$ 12,750.00"])
    # 25 filas por página (encabezado + 25 filas + TOTAL en la segunda).
    for chunk in (rows[:26], rows[26:]):
        page = doc.new_page(width=W, height=H)
        _text(page, 40, 50, "INVENTARIO — 50 ARTÍCULOS", size=13, font="hebo")
        _table(page, 40, 90, [40, 300, 370, 460, 555], chunk, row_h=20)
        tables.append(chunk)
    _finish(doc, "Tabla grande 50 filas")
    meta = _meta(doc, path.name, "tabla_grande", tables=tables,
                 notes="Tabla de 52 filas repartida en 2 páginas.")
    _save(doc, path)
    return meta


# -------------------------------------------------------------- dos columnas

def dos_columnas_texto(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "BOLETÍN MENSUAL DE LA COMUNIDAD", size=14, font="hebo")
    left = ("En noviembre la asociación recaudó $ 12,450.00 en cuotas "
            "ordinarias y $ 1,200.00 por el alquiler del salón. El gasto "
            "total del mes fue de $ 9,800.50, con lo que el saldo a favor "
            "quedó en $ 3,849.50 para diciembre.")
    right = ("Para diciembre se proyectan ingresos de $ 13,000.00 y egresos "
             "de $ 10,500.00. La cuota vence el día 15 y el valor es de "
             "$ 45.00 por unidad. Se recuerda pagar antes del día 10 para "
             "evitar el recargo de $ 5.00.")
    for text, rect in ((left, pymupdf.Rect(40, 80, 280, 400)),
                       (right, pymupdf.Rect(310, 80, 555, 400))):
        rc = page.insert_textbox(rect, text, fontsize=11, fontname="helv")
        assert rc >= 0, "el texto no cupo en la columna"
    _finish(doc, "Dos columnas texto")
    meta = _meta(doc, path.name, "dos_columnas")
    _save(doc, path)
    return meta


def dos_columnas_mixto(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "RESUMEN DE DICIEMBRE 2026", size=14, font="hebo")
    left_rows = [["Concepto", "Valor"], ["Agua", "$ 25.00"], ["Luz", "$ 40.50"],
                 ["Internet", "$ 45.00"], ["TOTAL", "$ 110.50"]]
    right_rows = [["Concepto", "Valor"], ["Cuotas", "$ 1,300.00"],
                  ["Alquiler", "$ 350.00"], ["Intereses", "$ 55.25"],
                  ["TOTAL", "$ 1,705.25"]]
    _table(page, 40, 100, [40, 150, 280], left_rows, row_h=20)
    _table(page, 310, 100, [310, 430, 555], right_rows, row_h=20)
    _text(page, 40, 240, "Gastos del mes a la izquierda; ingresos a la derecha.", size=10)
    _finish(doc, "Dos columnas mixto")
    meta = _meta(doc, path.name, "dos_columnas", tables=[left_rows, right_rows])
    _save(doc, path)
    return meta


# -------------------------------------------------------------- formularios

def formulario_solicitud(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "SOLICITUD DE RESERVA DE SALÓN COMUNAL", size=14, font="hebo")
    fields = [
        ("Nombre completo:", "Fabián Joel Alarcón Macías"),
        ("Cédula:", "0923456789"),
        ("Unidad / Villa:", "Villa 45 — Manzana 3"),
        ("Teléfono:", "0998765432"),
        ("Fecha del evento:", "20 de diciembre de 2026"),
        ("Hora de inicio:", "18:00"),
        ("Hora de fin:", "23:00"),
        ("Número de invitados:", "60"),
        ("Costo del alquiler:", "$ 150.00"),
        ("Depósito en garantía:", "$ 100.00"),
        ("TOTAL A PAGAR:", "$ 250.00"),
    ]
    y = 90
    for label, value in fields:
        _text(page, 40, y, label, size=11, font="hebo")
        _line(page, 40, y + 6, 555, y + 6, width=0.5)
        _text(page, 280, y, value, size=11)
        y += 28
    _text(page, 40, y + 10, "Acepto el reglamento del salón comunal.   [X] Sí   [ ] No", size=11)
    _finish(doc, "Formulario solicitud")
    meta = _meta(doc, path.name, "formulario")
    _save(doc, path)
    return meta


def formulario_checklist(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "LISTA DE VERIFICACIÓN — ENTREGA DE OBRA", size=14, font="hebo")
    items = [
        ("Pintura de paredes terminada", True, "$ 0.00"),
        ("Instalación eléctrica revisada", True, "$ 0.00"),
        ("Puertas y cerraduras instaladas", True, "$ 0.00"),
        ("Reparación de filtración en baño", False, "$ 120.00"),
        ("Limpieza final del área", False, "$ 85.50"),
        ("Retiro de escombros", True, "$ 0.00"),
    ]
    y = 90
    for label, done, cost in items:
        mark = "[X]" if done else "[ ]"
        _text(page, 40, y, mark, size=11, font="hebo")
        _text(page, 75, y, label, size=11)
        _text(page, 450, y, cost, size=11)
        y += 26
    _text(page, 40, y + 10, "Pendiente por reparar: $ 205.50", size=11, font="hebo")
    _text(page, 40, y + 36, "Responsable: Luis Pérez — Fecha: 18 de noviembre de 2026", size=10)
    _finish(doc, "Formulario checklist")
    meta = _meta(doc, path.name, "formulario")
    _save(doc, path)
    return meta


# ----------------------------------------------------------------- contratos

def contrato_arrendamiento(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "CONTRATO DE ARRENDAMIENTO", size=15, font="hebo")
    clauses = [
        "PRIMERA: El arrendador entrega en alquiler el local comercial "
        "ubicado en Km 13.5 Vía a la Costa, Guayaquil, por un plazo de 12 meses.",
        "SEGUNDA: El canon mensual es de $ 450.00, pagadero dentro de los "
        "primeros 5 días de cada mes.",
        "TERCERA: El arrendatario entrega un depósito en garantía de $ 900.00, "
        "equivalente a dos meses de canon, reembolsable al final del contrato.",
        "CUARTA: El valor total del contrato por los 12 meses es de $ 5,400.00.",
        "QUINTA: Los servicios básicos (agua, luz e internet) corren por "
        "cuenta del arrendatario, con un estimado mensual de $ 85.00.",
    ]
    y = 90
    for clause in clauses:
        rc = page.insert_textbox(pymupdf.Rect(40, y, 555, y + 90), clause,
                                 fontsize=11, fontname="helv")
        assert rc >= 0
        y += 95
    _text(page, 40, y + 10, "Guayaquil, 01 de noviembre de 2026", size=11)
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "CONTRATO DE ARRENDAMIENTO (continuación)", size=13, font="hebo")
    more = [
        "SEXTA: El arrendatario no podrá subarrendar el local sin "
        "autorización escrita del arrendador.",
        "SÉPTIMA: Cualquier mejora realizada queda en beneficio del inmueble "
        "sin derecho a reembolso, salvo acuerdo escrito.",
        "OCTAVA: En caso de mora mayor a 15 días, se aplica un recargo de "
        "$ 25.00 por mes vencido.",
    ]
    y = 90
    for clause in more:
        rc = page.insert_textbox(pymupdf.Rect(40, y, 555, y + 90), clause,
                                 fontsize=11, fontname="helv")
        assert rc >= 0
        y += 95
    _text(page, 40, y + 10, "Arrendador: Walter García — Arrendatario: Fabián Alarcón", size=11)
    _text(page, 40, y + 36, "Firmas: ____________________    ____________________", size=11)
    _finish(doc, "Contrato arrendamiento")
    meta = _meta(doc, path.name, "contrato")
    _save(doc, path)
    return meta


def contrato_servicios(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "CONTRATO DE PRESTACIÓN DE SERVICIOS", size=14, font="hebo")
    _text(page, 40, 80, "Entre la Asociación Punta Esmeralda y Servicios Generales del "
          "Litoral S.A., se acuerda lo siguiente:", size=11)
    rows = [
        ["Servicio", "Valor mensual"],
        ["Limpieza de áreas comunes", "$ 800.00"],
        ["Mantenimiento de jardines", "$ 350.00"],
        ["Seguridad nocturna", "$ 120.00"],
        ["TOTAL MENSUAL", "$ 1,270.00"],
        ["TOTAL ANUAL (12 meses)", "$ 15,240.00"],
    ]
    _table(page, 40, 130, [40, 380, 555], rows, row_h=22)
    _text(page, 40, 300, "El pago se realiza el día 5 de cada mes por transferencia.", size=11)
    _text(page, 40, 325, "El contrato rige desde el 01 de noviembre de 2026 por 12 meses.", size=11)
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "CONTRATO DE SERVICIOS (continuación)", size=13, font="hebo")
    _text(page, 40, 90, "Cláusula de penalidad: por cada día de retraso en el servicio, "
          "se descuenta $ 15.00 del valor mensual.", size=11)
    _text(page, 40, 120, "El servicio incluye materiales de limpieza por $ 60.00 mensuales, "
          "ya incluidos en el total.", size=11)
    _finish(doc, "Contrato servicios")
    meta = _meta(doc, path.name, "contrato", tables=[rows])
    _save(doc, path)
    return meta


# ------------------------------------------------- escaneos, color y fotos

def _pix_to_pdf(pix, path: Path, page_rect) -> None:
    """PDF de solo imagen a partir de un pixmap (escaneo)."""
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    out = pymupdf.open()
    new = out.new_page(width=page_rect.width, height=page_rect.height)
    new.insert_image(new.rect, stream=buf.getvalue())
    _finish(out, "Escaneo")
    _save(out, path)


def _render_all(src_doc: pymupdf.Document, path: Path, rotate: float = 0.0,
                dpi: int = 200) -> None:
    """Escaneo limpio: todas las páginas como imágenes, sin texto nativo."""
    out = pymupdf.open()
    for page in src_doc:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if rotate:
            img = img.rotate(rotate, expand=False, fillcolor="white",
                             resample=Image.BICUBIC)
        buf = BytesIO()
        img.save(buf, "JPEG", quality=90)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=buf.getvalue())
    _finish(out, "Escaneo")
    _save(out, path)


def _perspective_coeffs(src_corners, dst_corners):
    import numpy as np

    a, b = [], []
    for (x, y), (u, v) in zip(dst_corners, src_corners):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    coeffs = np.linalg.solve(np.array(a, dtype=float), np.array(b, dtype=float))
    return tuple(float(c) for c in coeffs)


def _render_perspective(src_doc: pymupdf.Document, path: Path, page_no: int = 0,
                        rotate: float = 2.0) -> None:
    """Foto de celular: perspectiva leve + inclinación."""
    page = src_doc[page_no]
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    w, h = img.size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(0.04 * w, 0.02 * h), (0.95 * w, 0.01 * h),
           (0.97 * w, 0.96 * h), (0.01 * w, 0.98 * h)]
    img = img.transform((w, h), Image.PERSPECTIVE,
                        _perspective_coeffs(src, dst), resample=Image.BICUBIC)
    if rotate:
        img = img.rotate(rotate, expand=False, fillcolor="white",
                         resample=Image.BICUBIC)
    # Guardar la imagen transformada (no el pixmap original).
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    out = pymupdf.open()
    new = out.new_page(width=page.rect.width, height=page.rect.height)
    new.insert_image(new.rect, stream=buf.getvalue())
    _finish(out, "Foto celular")
    _save(out, path)


def _render_foto_sombra(src_doc: pymupdf.Document, path: Path) -> None:
    """Foto de celular sobre una mesa: perspectiva + fondo gris con sombra."""
    from PIL import ImageDraw

    page = src_doc[0]
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    w, h = img.size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(0.06 * w, 0.03 * h), (0.93 * w, 0.02 * h),
           (0.96 * w, 0.94 * h), (0.03 * w, 0.97 * h)]
    img = img.transform((w, h), Image.PERSPECTIVE,
                        _perspective_coeffs(src, dst), resample=Image.BICUBIC)
    canvas = Image.new("RGB", (int(w * 1.08), int(h * 1.05)), (190, 190, 185))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([int(w * 0.05) + 8, int(h * 0.03) + 8,
                    int(w * 0.05) + w + 8, int(h * 0.03) + h + 8],
                   fill=(120, 120, 115))
    canvas.paste(img, (int(w * 0.05), int(h * 0.03)))
    buf = BytesIO()
    canvas.save(buf, "JPEG", quality=90)
    out = pymupdf.open()
    new = out.new_page(width=page.rect.width, height=page.rect.height)
    new.insert_image(new.rect, stream=buf.getvalue())
    _finish(out, "Foto celular con sombra")
    _save(out, path)


def color_sello_factura(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    page.draw_rect(pymupdf.Rect(40, 28, 150, 72), color=(0.1, 0.3, 0.6),
                   fill=(0.85, 0.9, 0.98), width=1.2)
    page.draw_circle((62, 50), 14, color=(0.1, 0.3, 0.6), fill=(0.1, 0.3, 0.6), width=1)
    _text(page, 56, 55, "SG", size=11, font="hebo", color=(1, 1, 1))
    _text(page, 82, 47, "Servicios", size=13, font="hebo", color=(0.1, 0.3, 0.6))
    _text(page, 82, 64, "DEL LITORAL S.A.", size=11, font="hebo", color=(0.1, 0.3, 0.6))
    _text(page, 40, 100, "FACTURA Nº 001-003-0000457", size=16, font="hebo")
    _text(page, 40, 125, "RUC: 0998765432001", size=10)
    _text(page, 40, 145, "Cliente: Comité La Puntilla", size=10)
    _text(page, 40, 165, "Fecha: 05 de noviembre de 2026", size=10)
    rows = [
        ["Descripción", "Cantidad", "Precio Unit.", "Total"],
        ["Limpieza mensual", "1", "$ 800.00", "$ 800.00"],
        ["Jardinería", "2", "$ 175.00", "$ 350.00"],
        ["SUBTOTAL", "", "", "$ 1,150.00"],
        ["IVA 15%", "", "", "$ 172.50"],
        ["TOTAL", "", "", "$ 1,322.50"],
    ]
    _table(page, 40, 200, [40, 300, 370, 460, 555], rows,
           header_fill=(0.1, 0.3, 0.6))
    page.draw_circle((470, 420), 48, color=(0.8, 0.1, 0.1), fill=None, width=2.5)
    page.draw_circle((470, 420), 40, color=(0.8, 0.1, 0.1), fill=None, width=1)
    _text(page, 432, 416, "CANCELADO", size=11, font="hebo", color=(0.8, 0.1, 0.1))
    _text(page, 438, 436, "05 NOV 2026", size=9, font="hebo", color=(0.8, 0.1, 0.1))
    _finish(doc, "Factura color sello")
    meta = _meta(doc, path.name, "color_sello", tables=[rows],
                 fills=[{"rows": [0, 0], "cols": [0, 3], "color": "#1A4D99"}])
    _save(doc, path)
    return meta


def marca_agua_confidencial(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "INFORME CONFIDENCIAL — PRESUPUESTO 2027", size=14, font="hebo")
    rows = [
        ["Rubro", "2026", "2027"],
        ["Cuotas ordinarias", "$ 144,000.00", "$ 156,000.00"],
        ["Alquiler salón", "$ 14,400.00", "$ 15,600.00"],
        ["Mantenimiento", "$ 21,600.00", "$ 24,000.00"],
        ["Seguridad", "$ 31,200.00", "$ 33,600.00"],
        ["TOTAL", "$ 211,200.00", "$ 229,200.00"],
    ]
    _table(page, 40, 100, [40, 280, 420, 555], rows, row_h=22)
    _text(page, 40, 280, "Uso interno de la administración. No distribuir.", size=10)
    # Marca de agua nativa, rotada 45° con morph, en gris claro.
    page.insert_text((150, 500), "CONFIDENCIAL", fontsize=48, fontname="hebo",
                     color=(0.85, 0.85, 0.85),
                     morph=(pymupdf.Point(150, 500), pymupdf.Matrix(45)))
    _finish(doc, "Marca de agua confidencial")
    meta = _meta(doc, path.name, "marca_agua", tables=[rows],
                 notes="Marca de agua de texto nativo rotada 45°.")
    _save(doc, path)
    return meta


def tabla_colores_rellenos(path: Path) -> dict:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "REPORTE DE GASTOS CON RELLENOS", size=14, font="hebo")
    rows = [
        ["Mes", "Concepto", "Valor"],
        ["Enero", "Limpieza", "$ 1,800.00"],
        ["Febrero", "Seguridad", "$ 2,600.00"],
        ["Marzo", "Jardinería", "$ 950.00"],
        ["Abril", "Servicios", "$ 1,150.00"],
        ["TOTAL", "", "$ 6,500.00"],
    ]
    fills = {(1, None): (0.92, 0.96, 1.0), (3, None): (0.92, 0.96, 1.0),
             (5, None): (1.0, 0.95, 0.8)}
    _table(page, 40, 90, [40, 150, 400, 555], rows, row_h=22, fills=fills,
           header_fill=(0.1, 0.3, 0.6))
    _finish(doc, "Tabla colores rellenos")
    fills_meta = [{"rows": [1, 1], "cols": [0, 2], "color": "#EBF5FF"},
                  {"rows": [3, 3], "cols": [0, 2], "color": "#EBF5FF"},
                  {"rows": [5, 5], "cols": [0, 2], "color": "#FFF2CC"}]
    meta = _meta(doc, path.name, "tabla_colores", tables=[rows], fills=fills_meta)
    _save(doc, path)
    return meta


def informe_mensual_mixto(path: Path) -> dict:
    doc = pymupdf.open()
    tables = []
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "INFORME MENSUAL — NOVIEMBRE 2026", size=15, font="hebo")
    _text(page, 40, 80, "Resumen: el mes cerró con ingresos de $ 13,650.00 y egresos de "
          "$ 9,800.50, para un saldo a favor de $ 3,849.50.", size=11)
    _text(page, 40, 105, "La morosidad bajó de 12% a 8% respecto a octubre.", size=11)
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "DETALLE DE INGRESOS Y EGRESOS", size=13, font="hebo")
    rows = [
        ["Concepto", "Ingresos", "Egresos"],
        ["Cuotas ordinarias", "$ 12,450.00", "$ 0.00"],
        ["Alquiler salón", "$ 1,200.00", "$ 0.00"],
        ["Limpieza", "$ 0.00", "$ 1,800.00"],
        ["Seguridad", "$ 0.00", "$ 2,600.00"],
        ["Jardinería", "$ 0.00", "$ 950.00"],
        ["Servicios básicos", "$ 0.00", "$ 1,150.00"],
        ["Mantenimiento", "$ 0.00", "$ 3,300.50"],
        ["TOTAL", "$ 13,650.00", "$ 9,800.50"],
    ]
    _table(page, 40, 90, [40, 300, 430, 555], rows, row_h=22)
    tables.append(rows)
    page = doc.new_page(width=W, height=H)
    _text(page, 40, 50, "CONCLUSIONES", size=13, font="hebo")
    _text(page, 40, 80, "Se recomienda mantener el fondo de reserva en $ 5,000.00 y "
          "destinar $ 2,000.00 a la reparación del cerramiento.", size=11)
    _text(page, 40, 110, "Próxima asamblea: 15 de diciembre de 2026 a las 19:00.", size=11)
    _finish(doc, "Informe mensual mixto")
    meta = _meta(doc, path.name, "informe_mixto", tables=tables)
    _save(doc, path)
    return meta


# ------------------------------------------------- escaneos y fotos (derivados)

def _meta_escaneado(src_doc: pymupdf.Document, name: str, kind: str,
                    notes: str = "") -> dict:
    """Verdad de referencia del documento origen (el escaneo no tiene texto)."""
    meta = _meta(src_doc, name, kind, scanned=True, notes=notes)
    meta["images"] = src_doc.page_count  # una imagen por página escaneada
    return meta


def escaneado_factura_servicios(path: Path) -> dict:
    src = pymupdf.open(OUT / "factura_servicios.pdf")
    meta = _meta_escaneado(src, path.name, "escaneado",
                           notes="Escaneo limpio (200 dpi) de factura_servicios.pdf.")
    _render_all(src, path)
    src.close()
    return meta


def escaneado_contrato(path: Path) -> dict:
    src = pymupdf.open(OUT / "contrato_servicios.pdf")
    meta = _meta_escaneado(src, path.name, "escaneado",
                           notes="Escaneo limpio (200 dpi) de contrato_servicios.pdf (2 págs.).")
    _render_all(src, path)
    src.close()
    return meta


def foto_perspectiva_factura(path: Path) -> dict:
    src = pymupdf.open(OUT / "factura_detalle_largo.pdf")
    meta = _meta_escaneado(src, path.name, "foto_celular",
                           notes="Foto con perspectiva + inclinación 2° de factura_detalle_largo.pdf.")
    _render_perspective(src, path)
    src.close()
    return meta


def foto_inclinada_contrato(path: Path) -> dict:
    src = pymupdf.open(OUT / "contrato_arrendamiento.pdf")
    meta = _meta_escaneado(src, path.name, "foto_celular",
                           notes="Foto inclinada 2.5° de contrato_arrendamiento.pdf (2 págs.).")
    _render_all(src, path, rotate=2.5)
    src.close()
    return meta


def foto_sombra(path: Path) -> dict:
    src = pymupdf.open(OUT / "factura_servicios.pdf")
    meta = _meta_escaneado(src, path.name, "foto_celular",
                           notes="Foto con perspectiva sobre fondo gris con sombra.")
    _render_foto_sombra(src, path)
    src.close()
    return meta


# -------------------------------------------------------------------- main

# (nombre de archivo, función generadora)
NUEVOS = [
    ("factura_servicios.pdf", factura_servicios),
    ("factura_detalle_largo.pdf", factura_detalle_largo),
    ("factura_nota_credito.pdf", factura_nota_credito),
    ("estado_cuenta_6p.pdf", estado_cuenta_6p),
    ("estado_cuenta_tarjeta.pdf", estado_cuenta_tarjeta),
    ("balance_general.pdf", balance_general),
    ("estado_resultados.pdf", estado_resultados),
    ("flujo_caja.pdf", flujo_caja),
    ("tabla_sin_lineas_ventas.pdf", tabla_sin_lineas_ventas),
    ("tabla_sin_lineas_nomina.pdf", tabla_sin_lineas_nomina),
    ("celdas_combinadas_presupuesto.pdf", celdas_combinadas_presupuesto),
    ("tabla_encabezado_doble.pdf", tabla_encabezado_doble),
    ("tabla_grande_50_filas.pdf", tabla_grande_50_filas),
    ("dos_columnas_texto.pdf", dos_columnas_texto),
    ("dos_columnas_mixto.pdf", dos_columnas_mixto),
    ("formulario_solicitud.pdf", formulario_solicitud),
    ("formulario_checklist.pdf", formulario_checklist),
    ("contrato_arrendamiento.pdf", contrato_arrendamiento),
    ("contrato_servicios.pdf", contrato_servicios),
    ("escaneado_factura_servicios.pdf", escaneado_factura_servicios),
    ("escaneado_contrato.pdf", escaneado_contrato),
    ("color_sello_factura.pdf", color_sello_factura),
    ("marca_agua_confidencial.pdf", marca_agua_confidencial),
    ("tabla_colores_rellenos.pdf", tabla_colores_rellenos),
    ("foto_perspectiva_factura.pdf", foto_perspectiva_factura),
    ("foto_inclinada_contrato.pdf", foto_inclinada_contrato),
    ("foto_sombra.pdf", foto_sombra),
    ("informe_mensual_mixto.pdf", informe_mensual_mixto),
]

# Fixtures preexistentes (scripts/generate_fixtures.py): la verdad de
# referencia se extrae de su texto nativo; los escaneados heredan la de
# factura.pdf, de la que se generaron.
EXISTENTES = {
    "acentos.pdf": "texto",
    "celdas_combinadas.pdf": "celdas_combinadas",
    "dos_columnas.pdf": "dos_columnas",
    "dos_columnas_tablas.pdf": "dos_columnas",
    "escaneado.pdf": "escaneado",
    "escaneado_color_sello.pdf": "escaneado",
    "estado_cuenta_multipagina.pdf": "estado_cuenta",
    "estado_ingresos_octubre_2026.pdf": "estado_financiero",
    "factura.pdf": "factura",
    "factura_real_logo_sello.pdf": "factura",
    "foto_celular_perspectiva.pdf": "foto_celular",
    "foto_inclinada.pdf": "foto_celular",
    "tabla_combinada_compleja.pdf": "celdas_combinadas",
    "tabla_sin_lineas.pdf": "tabla_sin_lineas",
}


def _meta_existente(name: str, kind: str) -> dict:
    doc = pymupdf.open(OUT / name)
    scanned = kind in ("escaneado", "foto_celular")
    if scanned:
        # La referencia es la factura de la que se generó el escaneo/foto.
        src = pymupdf.open(OUT / "factura.pdf")
        meta = _meta(src, name, kind, scanned=True,
                     notes="Fixture preexistente: referencia heredada de factura.pdf "
                           "(el sello y la marca de agua no están en la referencia).")
        meta["images"] = doc.page_count
        src.close()
    else:
        meta = _meta(doc, name, kind,
                     notes="Fixture preexistente: sin tabla de referencia registrada.")
    doc.close()
    return meta


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for name, fn in NUEVOS:
        manifest.append(fn(OUT / name))
        print(f"generado {name}")
    for name, kind in sorted(EXISTENTES.items()):
        path = OUT / name
        if not path.exists():
            print(f"AVISO: falta el fixture preexistente {name}; "
                  "ejecuta primero scripts/generate_fixtures.py")
            continue
        manifest.append(_meta_existente(name, kind))
    manifest.sort(key=lambda m: m["file"])
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    total = len(manifest)
    kinds: dict[str, int] = {}
    for m in manifest:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    print(f"\nConjunto de oro: {total} PDFs en {OUT}")
    for kind, n in sorted(kinds.items()):
        print(f"  {kind}: {n}")
    print(f"Manifiesto: {MANIFEST}")
    assert total >= 40, f"el conjunto de oro tiene {total} PDFs, se esperaban al menos 40"


if __name__ == "__main__":
    main()
