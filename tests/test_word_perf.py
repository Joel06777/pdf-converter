"""Regresión de rendimiento de la ruta Word (grid).

Causa raíz corregida en app/converters/pdf_to_word.py: cada llamada a
``table.cell()`` de python-docx reconstruye la lista completa de celdas
(propiedad ``_cells`` sin caché), así que escribir los textos de una tabla
grande era O(n²): el documento de referencia (68 filas x 12 columnas)
tardaba 4,27 s solo en Word y ``tabla_grande_50_filas`` 1,35 s. Con el índice
propio de celdas (una sola construcción + mapa de dueños por fusión) la
referencia baja a ~0,8 s y la tabla grande a ~0,4 s, con cobertura 1,0.

Por qué la guarda es un RATIO y no un tiempo absoluto (26 nov 2026)
--------------------------------------------------------------------
La versión anterior de esta prueba medía UNA sola conversión a Word y exigía
``dt < 3,0 s`` para la referencia. En GitHub Actions eso falló en las
ejecuciones #126-#132 con 3,95 s en una sola medición, mientras las
ejecuciones #133-#138 del mismo código pasaron: el corredor compartido de
GitHub es hasta ~5x más lento que esta VM (referencia local 0,78-0,84 s
frente a 3,95 s en GitHub) y una sola medición de tiempo de pared depende de
la máquina y de la contención del momento. Un umbral absoluto no puede
separar "máquina lenta" de "regresión del algoritmo" en las dos máquinas a la
vez: 3,0 s es 3,8x el tiempo local optimizado pero MENOS que el tiempo
optimizado en GitHub.

La guarda nueva mide, en el mismo proceso y seguidas, la mejor de 3
repeticiones a Word y a Excel del mismo PDF, y exige que el cociente
Word/Excel no supere un umbral. El cociente cancela la velocidad de la
máquina: Excel hace la misma extracción y reconstrucción de la cuadrícula,
pero no usa python-docx, así que si vuelve el O(n²) de ``table.cell()`` solo
sube el numerador. Medido en local (mejor de 3, sin carga y con 3 hilos
quemando CPU en paralelo, 26 nov 2026):

* referencia: Word 0,77-1,08 s / Excel 0,26-0,40 s -> ratio 2,70-2,97
* tabla grande: Word 0,37-0,50 s / Excel 0,11-0,13 s -> ratio 3,48-3,75
* estado 6p: Word 0,58-0,78 s / Excel 0,14-0,20 s -> ratio 3,87-4,04

El ratio apenas se mueve con carga (variación observada <= 8 %), así que el
umbral se fija en 1,5x el ratio optimizado máximo medido: hay ~50 % de
margen sobre el ruido y el ratio de la regresión queda por encima.

Que la guarda sigue detectando la regresión (verificado, no heredado)
----------------------------------------------------------------------
Simulación independiente del código antiguo (26 nov 2026): conté las
llamadas a ``table.cell()`` que hacía el bucle antiguo (una por texto
colocado + una por fusión) y medí su coste en una tabla del mismo tamaño:
referencia ~194 llamadas -> +2,43 s; tabla grande ~208 -> +0,64 s;
estado 6p ~252 -> +0,37 s (cota inferior: el código antiguo también llamaba
a ``table.cell()`` en las fusiones verticales). Sumado al tiempo optimizado,
el ratio de la regresión sería ~12,3 en la referencia, ~9,2 en la tabla
grande y ~6,4-7,1 en el estado 6p (coherente con los "antes" 4,27 s, 1,35 s
y 1,06 s). Los umbrales (4,5 / 5,6 / 5,2) quedan por debajo de esos ratios
en los tres casos.

Comprobación en vivo de que la guarda salta (26 nov 2026): con el índice
plano sustituido temporalmente por ``table.cell()`` (simulación parcial de
la regresión: solo el acceso por celda, no las fusiones) las tres pruebas
fallaron en la primera pasada, con ratios 10,25 / 8,86 / 6,22; en una
segunda pasada fallaron referencia y tabla grande y el estado 6p quedó
justo por debajo de su umbral antiguo (6,0). Por eso el umbral del estado
6p se fijó en 5,2 y no en 6,0: el ratio optimizado máximo medido es 4,04
(29 % de margen, frente a un ruido observado <= 8 %) y la regresión medida
en vivo es 6,22 (con el código antiguo completo, ~7,1). El estado 6p es la
guarda más ajustada de las tres, porque ahí la regresión solo costaba
~0,5 s; queda documentado así y no se disimula.

Además se mantiene un tope absoluto generoso (mejor de 3) como red de
seguridad contra una lentitud catastrófica: 10x el mejor tiempo local
medido, muy por encima del factor ~5x del corredor de GitHub, así que no
salta por una máquina lenta.
"""
import time
from pathlib import Path

import pytest

from app.converters import convert

FIX = Path(__file__).parent / "fixtures"

# (ratio máximo, tope absoluto en segundos de la mejor de 3 repeticiones)
# Ratio = mejor Word / mejor Excel del mismo PDF, en el mismo proceso.
LIMITES = {
    "estado_ingresos_octubre_2026.pdf": (4.5, 8.0),
    "tabla_grande_50_filas.pdf": (5.6, 4.0),
    "estado_cuenta_6p.pdf": (5.2, 6.0),
}


def _best_time(pdf: Path, fmt: str, tmp_path: Path, reps: int = 3) -> tuple[float, dict]:
    """Mejor tiempo de `reps` conversiones y su info (la mejor filtra picos)."""
    ext = {"word": "docx", "excel": "xlsx"}[fmt]
    best_dt, best_info = None, None
    for i in range(reps):
        out = tmp_path / f"o{i}.{ext}"
        t0 = time.monotonic()
        info = convert(str(pdf), str(out), fmt)
        dt = time.monotonic() - t0
        if best_dt is None or dt < best_dt:
            best_dt, best_info = dt, info
    return best_dt, best_info


def _check_ratio(pdf: Path, tmp_path: Path):
    """Devuelve (word_min, excel_min, ratio) y exige cobertura 1,0 en Word."""
    dt_word, info = _best_time(pdf, "word", tmp_path)
    dt_excel, _ = _best_time(pdf, "excel", tmp_path)
    assert info["engine"].startswith("grid")
    assert info["quality"]["text_coverage"] == 1.0
    assert info["quality"]["number_coverage"] == 1.0
    ratio = dt_word / dt_excel
    return dt_word, dt_excel, ratio


def test_word_referencia_rapida_y_completa(tmp_path):
    dt_word, dt_excel, ratio = _check_ratio(FIX / "estado_ingresos_octubre_2026.pdf", tmp_path)
    ratio_max, tope = LIMITES["estado_ingresos_octubre_2026.pdf"]
    assert ratio < ratio_max, (
        f"referencia Word/Excel = {ratio:.2f} (Word {dt_word:.2f} s, Excel {dt_excel:.2f} s); "
        f"el ratio optimizado medido es <= 3,0 y con el O(n²) de table.cell() es ~10,3 medido (~12,3 estimado)"
    )
    assert dt_word < tope, f"referencia Word tardó {dt_word:.2f} s (mejor de 3)"


# Los dos fixtures grandes son "gold" (scripts/generate_gold.py), no los genera
# scripts/generate_fixtures.py que corre la CI: si no existen, se salta.
_gold = pytest.mark.skipif(not (FIX / "tabla_grande_50_filas.pdf").exists()
                           or not (FIX / "estado_cuenta_6p.pdf").exists(),
                           reason="fixtures gold no generados en este entorno")


@_gold
def test_word_tabla_grande_rapida_y_completa(tmp_path):
    dt_word, dt_excel, ratio = _check_ratio(FIX / "tabla_grande_50_filas.pdf", tmp_path)
    ratio_max, tope = LIMITES["tabla_grande_50_filas.pdf"]
    assert ratio < ratio_max, (
        f"tabla grande Word/Excel = {ratio:.2f} (Word {dt_word:.2f} s, Excel {dt_excel:.2f} s); "
        f"el ratio optimizado medido es <= 3,75 y con el O(n²) de table.cell() es ~8,9 medido (~9,2 estimado)"
    )
    assert dt_word < tope, f"tabla grande Word tardó {dt_word:.2f} s (mejor de 3)"


@_gold
def test_word_estado_cuenta_6p_rapido_y_completo(tmp_path):
    dt_word, dt_excel, ratio = _check_ratio(FIX / "estado_cuenta_6p.pdf", tmp_path)
    ratio_max, tope = LIMITES["estado_cuenta_6p.pdf"]
    assert ratio < ratio_max, (
        f"estado 6p Word/Excel = {ratio:.2f} (Word {dt_word:.2f} s, Excel {dt_excel:.2f} s); "
        f"el ratio optimizado medido es <= 4,04 y con el O(n²) de table.cell() es ~6,2 medido (~7,1 con el código antiguo completo)"
    )
    assert dt_word < tope, f"estado 6p Word tardó {dt_word:.2f} s (mejor de 3)"
