"""Mide cobertura y duración por fixture y destino; imprime tabla Markdown.

Uso: python scripts/measure_metrics.py  (tarda ~1 min con OCR)
Solo imprime lo medido en este entorno; no inventa cifras.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.converters import convert  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
EXT = {"excel": "xlsx", "word": "docx", "pptx": "pptx"}
REF = FIX / "estado_ingresos_octubre_2026.pdf"

print("| Fixture | Destino | Texto | Cifras | Segundos | Notas |")
print("|---|---|---|---|---|---|")
for pdf in [REF, *sorted(p for p in FIX.glob("*.pdf") if p.name != REF.name)]:
    for target in ("excel", "word", "pptx"):
        out = Path(f"/tmp/metrica.{EXT[target]}")
        t0 = time.time()
        try:
            info = convert(str(pdf), str(out), target)
        except Exception as exc:  # noqa: BLE001
            print(f"| {pdf.name} | {target} | ERROR | | | {exc} |")
            continue
        dt = time.time() - t0
        q = info.get("quality", {})
        notas = []
        if info.get("ocr_pages"):
            notas.append(f"OCR {info['ocr_pages']} pág.")
        if info.get("ocr_warning"):
            notas.append("advertencia OCR")
        if info.get("formulas"):
            notas.append(f"fórmulas: {', '.join(info['formulas'])}")
        print(f"| {pdf.name} | {target} | {q.get('text_coverage')} | {q.get('number_coverage')} "
              f"| {dt:.2f} | {'; '.join(notas)} |")
