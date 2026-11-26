"""Regresión de rendimiento de la ruta Word (grid).

Causa raíz corregida en app/converters/pdf_to_word.py: cada llamada a
`table.cell()` de python-docx reconstruye la lista completa de celdas
(propiedad `_cells` sin caché), así que escribir los textos de una tabla
grande era O(n²): el documento de referencia (68 filas x 12 columnas)
tardaba 4,27 s solo en Word y `tabla_grande_50_filas` 1,35 s. Con el índice
propio de celdas (una sola construcción + mapa de dueños por fusión) la
referencia baja a ~1,2 s y la tabla grande a ~0,4 s, con cobertura 1,0.

Los umbrales son guardas generosas (2-3x lo medido), no benchmarks: solo
deben saltar si vuelve el comportamiento cuadrático, no por ruido de máquina.
"""
import time
from pathlib import Path

import pytest

from app.converters import convert

FIX = Path(__file__).parent / "fixtures"


def _word_time(pdf: Path, tmp_path: Path) -> tuple[float, dict]:
    out = tmp_path / "o.docx"
    t0 = time.monotonic()
    info = convert(str(pdf), str(out), "word")
    return time.monotonic() - t0, info


def test_word_referencia_rapida_y_completa(tmp_path):
    dt, info = _word_time(FIX / "estado_ingresos_octubre_2026.pdf", tmp_path)
    assert info["engine"] == "grid"
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0
    assert dt < 3.0, f"referencia Word tardó {dt:.2f} s (antes de la optimización: 4,27 s)"


# Los dos fixtures grandes son "gold" (scripts/generate_gold.py), no los genera
# scripts/generate_fixtures.py que corre la CI: si no existen, se salta.
_gold = pytest.mark.skipif(not (FIX / "tabla_grande_50_filas.pdf").exists()
                           or not (FIX / "estado_cuenta_6p.pdf").exists(),
                           reason="fixtures gold no generados en este entorno")


@_gold
def test_word_tabla_grande_rapida_y_completa(tmp_path):
    dt, info = _word_time(FIX / "tabla_grande_50_filas.pdf", tmp_path)
    assert info["engine"] == "grid"
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0
    assert dt < 1.5, f"tabla grande Word tardó {dt:.2f} s (antes: 1,35 s)"


@_gold
def test_word_estado_cuenta_6p_rapido_y_completo(tmp_path):
    dt, info = _word_time(FIX / "estado_cuenta_6p.pdf", tmp_path)
    assert info["engine"] == "grid"
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0
    assert dt < 2.0, f"estado 6p Word tardó {dt:.2f} s (antes: 1,06 s)"
