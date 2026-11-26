"""Mide el tiempo de conversión a Word por fixture (ruta grid/flow/ocr).

Uso: .venv/bin/python scripts/measure_word.py [--repeticiones N]
Solo imprime lo medido en este entorno; no inventa cifras. Sirve para
comparar antes/después de optimizar la ruta Word (ver tests/test_word_perf.py).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging  # noqa: E402

logging.disable(logging.CRITICAL)

from app.converters import convert  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def measure(pdf: Path, reps: int) -> dict:
    out = Path("/tmp/med_word.docx")
    best = None
    engine = None
    quality = {}
    for _ in range(reps):
        t0 = time.time()
        info = convert(str(pdf), str(out), "word")
        dt = time.time() - t0
        best = dt if best is None else min(best, dt)
        engine = info.get("engine")
        quality = info.get("quality", {})
    return {"pdf": pdf.name, "engine": engine, "s": best,
            "texto": quality.get("text_coverage"), "cifras": quality.get("number_coverage")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeticiones", type=int, default=3)
    args = ap.parse_args()
    print("| Fixture | Motor | Mejor de N (s) | Texto | Cifras |")
    print("|---|---|---|---|---|")
    for pdf in sorted(FIX.glob("*.pdf")):
        try:
            r = measure(pdf, args.repeticiones)
        except Exception as exc:  # noqa: BLE001
            print(f"| {pdf.name} | ERROR | | | {exc} |")
            continue
        print(f"| {r['pdf']} | {r['engine']} | {r['s']:.2f} | {r['texto']} | {r['cifras']} |")


if __name__ == "__main__":
    main()
