"""Mide la precisión del OCR (cifras y texto) por caso, antes/después de un cambio.

Uso: .venv/bin/python scripts/measure_ocr.py
Compara cada escaneo contra el PDF nativo del que se generó, con los mismos
tokens que usa app/converters/verify.py. Solo imprime lo medido; no inventa cifras.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

from app.converters import convert  # noqa: E402
from app.converters.verify import pdf_tokens, xlsx_tokens  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
REF = FIX / "estado_ingresos_octubre_2026.pdf"


def _make_scan_ref(tmp: Path) -> Path:
    """Escaneo a 200 dpi del documento de referencia (como test_converters)."""
    src = pymupdf.open(REF)
    pix = src[0].get_pixmap(dpi=200)
    scan = pymupdf.open()
    page = scan.new_page(width=src[0].rect.width, height=src[0].rect.height)
    page.insert_image(page.rect, pixmap=pix)
    path = tmp / "scan_ref.pdf"
    scan.save(path)
    return path


def _precision(expected, got, kind):
    exp = {k: v for k, v in expected.items() if k[0] == kind}
    total = sum(exp.values())
    hit = sum(min(v, got.get(k, 0)) for k, v in exp.items())
    return hit / total if total else 1.0


def _combined(expected, got):
    total = sum(expected.values())
    hit = sum(min(v, got.get(k, 0)) for k, v in expected.items())
    return hit / total if total else 1.0


def measure(scan: Path, original: Path, label: str) -> dict:
    out = Path(tempfile.gettempdir()) / "med_ocr.xlsx"
    t0 = time.time()
    info = convert(str(scan), str(out), "excel")
    dt = time.time() - t0
    expected = pdf_tokens(str(original))
    got = xlsx_tokens(str(out))
    num = _precision(expected, got, "n")
    txt = _precision(expected, got, "t")
    comb = _combined(expected, got)
    return {"label": label, "num": num, "txt": txt, "comb": comb, "s": dt,
            "ocr_pages": info.get("ocr_pages"), "warning": bool(info.get("ocr_warning"))}


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cases = [
            (FIX / "escaneado.pdf", FIX / "factura.pdf", "escaneado 200 dpi (factura)"),
            (FIX / "foto_inclinada.pdf", FIX / "factura.pdf", "foto inclinada 3° (factura)"),
            (_make_scan_ref(tmp), REF, "escaneado 200 dpi (referencia)"),
            (FIX / "escaneado_color_sello.pdf", FIX / "factura.pdf", "escaneado color + sello + marca agua"),
            (FIX / "foto_celular_perspectiva.pdf", FIX / "factura.pdf", "foto celular perspectiva+2°"),
        ]
        print("| Caso | Cifras | Texto solo | Tokens (texto+cifras) | s | OCR págs. | Advertencia |")
        print("|---|---|---|---|---|---|---|")
        for scan, orig, label in cases:
            try:
                r = measure(scan, orig, label)
            except Exception as exc:  # noqa: BLE001
                print(f"| {label} | ERROR | | | | | {exc} |")
                continue
            print(f"| {r['label']} | {r['num']:.1%} | {r['txt']:.1%} | {r['comb']:.1%} | {r['s']:.1f} | "
                  f"{r['ocr_pages']} | {'sí' if r['warning'] else 'no'} |")


if __name__ == "__main__":
    main()
