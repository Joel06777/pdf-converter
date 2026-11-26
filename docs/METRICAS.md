# Métricas de fidelidad (medidas, no estimadas)

Generadas con `python scripts/measure_metrics.py` y con las pruebas de
`tests/test_converters.py` y `tests/test_fixtures.py`.

## Entorno de medición
- VM Linux, Python 3.12.3, PyMuPDF 2.2, Tesseract 5.3.4 (`spa+eng`), OCRmyPDF 15.2.0.
- Pruebas: **33 passed, 0 failed** (`pytest -q`, 26 nov 2026).
- Los tiempos son de una sola ejecución en este entorno y varían entre corridas;
  sirven como orden de magnitud, no como garantía.

## PDFs con texto nativo — cobertura (1.0 = todo el texto y todas las cifras)

| Fixture | Excel texto/cifras | Word texto/cifras | PPTX texto/cifras |
|---|---|---|---|
| estado_ingresos_octubre_2026.pdf (referencia) | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| factura.pdf | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| estado_cuenta_multipagina.pdf (3 págs.) | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| tabla_sin_lineas.pdf | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| celdas_combinadas.pdf | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| dos_columnas.pdf | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| acentos.pdf | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |

## PDFs escaneados — precisión del OCR (comparado con el PDF original)

El escaneado no tiene texto nativo, así que la calidad no es verificable contra
sí mismo: se compara contra el PDF del que se generó el escaneo.

| Caso | Precisión de cifras | Precisión de texto (tokens) |
|---|---|---|
| estado_ingresos_octubre_2026.pdf escaneado a 200 dpi | **100 %** | 90,3 % |
| factura.pdf escaneada a 200 dpi | **100 %** | 87,1 % |
| factura.pdf como foto inclinada 3° | **100 %** | 85,5 % |

Las cifras (lo crítico en documentos contables) se recuperan al 100 % en los
tres casos. El texto pierde algunas palabras por errores típicos del OCR
(`Nº` leído como `N?`, palabras partidas, sellos). Cuando la confianza del OCR
es baja, la conversión devuelve `ocr_warning` en español y las celdas dudosas
quedan resaltadas en amarillo en el Excel.

## Tiempos (una página, salvo estado de cuenta: 3 páginas)

| Fixture | Excel | Word | PPTX |
|---|---|---|---|
| estado_ingresos_octubre_2026.pdf | 0,35 s | 4,58 s | 0,65 s |
| factura.pdf | 0,05 s | 0,18 s | 0,06 s |
| estado_cuenta_multipagina.pdf | 0,11 s | 0,70 s | 0,17 s |
| escaneado.pdf (OCR) | 3,94 s | 3,70 s | 4,12 s |
| foto_inclinada.pdf (OCR + enderezado) | 5,63 s | 5,22 s | 5,40 s |

El OCR domina el tiempo (~4–6 s por página). Word en el documento de
referencia tarda más (~4,6 s) por la reconstrucción de la tabla con
python-docx.

## Fórmulas de totales (Excel)
Se aplican solo si el PDF etiqueta la fila como TOTAL y la suma de la columna
coincide con la cifra impresa (±0,01). Medido:
- factura.pdf: `G10 =SUM(G7:G9)` (335,00).
- tabla_sin_lineas.pdf: `C6, E6, G6` (totales de Ene/Feb/Mar).
- estado_cuenta_multipagina.pdf: `E12, G12` por página.
- estado_ingresos_octubre_2026.pdf: ninguna (sus totales no son suma directa
  de la columna; no se inventa ninguna fórmula).
