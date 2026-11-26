# Métricas de fidelidad (medidas, no estimadas)

Generadas con `python scripts/measure_metrics.py`, `python scripts/measure_ocr.py`
y con las pruebas de `tests/test_converters.py` y `tests/test_fixtures.py`.

## Entorno de medición
- VM Linux, Python 3.12.3, PyMuPDF 2.2, Tesseract 5.3.4 (`spa+eng`), OCRmyPDF 15.2.0.
- Pruebas: **69 passed, 0 failed** (`pytest -q`, 26 nov 2026, 112 s): 44 de la
  base + 20 nuevas de esta tanda (13 de fixtures, 4 de totales/moneda y 3 de
  `missing_sample`) + 5 de `tests/test_capacidad.py` (otro agente, en paralelo).
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
| factura_real_logo_sello.pdf (nuevo) | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| tabla_combinada_compleja.pdf (nuevo) | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| dos_columnas_tablas.pdf (nuevo) | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |

## PDFs escaneados — precisión del OCR (comparado con el PDF original)

El escaneado no tiene texto nativo, así que la calidad no es verificable contra
sí mismo: se compara contra el PDF del que se generó el escaneo.

Aclaración sobre la columna "Texto" de versiones anteriores: lo que antes se
publicaba como "precisión de texto (tokens)" era en realidad la precisión
combinada de texto + cifras. Aquí se separan las dos: "Texto solo" cuenta
solo tokens de texto y "Tokens" es el combinado anterior, para que las cifras
sean comparables con las publicadas antes.

| Caso | Cifras antes → después | Texto solo antes → después | Tokens (texto+cifras) antes → después |
|---|---|---|---|
| estado_ingresos_octubre_2026.pdf escaneado a 200 dpi | 100 % → **100 %** | 88,6 % → 88,6 % | 90,3 % → 90,3 % |
| factura.pdf escaneada a 200 dpi | 100 % → **100 %** | 83,3 % → **97,9 %** | 87,1 % → **98,4 %** |
| factura.pdf como foto inclinada 3° | 100 % → **100 %** | 81,2 % → **95,8 %** | 85,5 % → **96,8 %** |
| factura con sello + marca de agua, escaneada en color (nuevo) | — → **100 %** | — → **97,9 %** | — → **98,4 %** |
| foto de celular con perspectiva + 2° (nuevo) | — → **100 %** | — → **95,8 %** | — → **96,8 %** |

Las cifras (lo crítico en documentos contables) se recuperan al 100 % en los
cinco casos. El texto que sigue perdiéndose es casi todo el símbolo `Nº`
(leído `N?` por Tesseract) y alguna palabra junto a líneas de tabla.
Cuando la confianza del OCR es baja, la conversión devuelve `ocr_warning`
en español y las celdas dudosas quedan resaltadas en amarillo en el Excel.

### Qué cambió en el OCR y qué se probó sin mejora (26 nov 2026)

Medido con `scripts/measure_ocr.py` (conversión a Excel, 5 casos). Cambios
adoptados:

- **Símbolo `$` perdido en Excel** (`app/converters/pdf_to_excel.py`,
  `_merge_currency_with_number`): el OCR guarda `"$ 0.50"` como dos
  fragmentos y ambos caían en la misma celda, así que la cifra sobrescribía
  al `$`. Los 7 `$` de la factura escaneada no llegaban al Excel. Ahora, si
  moneda suelta y cifra comparten celda, se fusionan en `"$ 0.50"` con
  formato `$`, sin cambiar ningún valor. Es casi toda la mejora de texto
  (los spans del OCR ya estaban al 97,9 %; el Excel los dejaba en 83,3 %).
- **Binarización: guarda por densidad de tinta** (`app/converters/extract.py`,
  `_binarized_copy`): `autocontrast(cutoff=1)` en páginas con menos del 1 %
  de píxeles oscuros ponía el percentil 1 en un gris claro y volvía negro
  todo lo de debajo (medido: los píxeles negros se triplicaban y un documento
  de 4 líneas salía ilegible). Ahora cutoff=1 solo si hay ≥1 % de píxeles
  oscuros; si no, cutoff=0 (estira min/max sin recortar). La foto inclinada
  necesita el cutoff=1: con cutoff=0 en todo, su cantidad `5` se perdía
  (cifras 100 % → 92,9 %); con el guarda vuelve al 100 %.
- **Validación subtotal + IVA = total** (`app/converters/pdf_to_excel.py`,
  `check_totals`): solo en páginas con OCR, si las tres filas existen y la
  suma no cuadra (±0,01), las tres celdas quedan en amarillo y el aviso en
  español se añade a `ocr_warning` (también en `info["totals_warning"]`).
  Nunca cambia un valor: el total impreso se queda como está.

Probado y NO adoptado (medido, sin mejora o con empeoramiento):

- **Binarización adaptativa** (NumPy con media local y OpenCV
  `adaptiveThreshold` gaussiano, 51 px, C=10): en el escaneo plano empata
  (97,9 % texto) pero en la foto inclinada cae a 83,3 % de texto y 57–64 %
  de cifras (frente a 97,9 % / 100 % del umbral global 150). No se adopta
  y no se añade `opencv-python-headless` como dependencia (Apache-2.0,
  ~90 MB) porque no mejora nada.
- **Otsu** (umbral automático con NumPy): empata en el escaneo plano y en
  el documento escaso, pero baja las cifras al 92,9 % en la foto con
  perspectiva (umbral 106, demasiado bajo). No se adopta.
- **Renderizado a 400 dpi**: mixto — en la foto inclinada sube las cifras
  por CLI, pero en el escaneo plano baja el texto (95,8 % frente a 97,9 %)
  y duplica el tiempo de render. No se adopta. El renderizado ya estaba a
  300 dpi antes de esta tanda.
- **Modelos `tessdata_best` de español**: se descargaron gratis de
  GitHub (`tesseract-ocr/tessdata_best`, `spa.traineddata`, 13,5 MB) y se
  probaron con `--tessdata-dir`: el texto baja de 97,9 % a 87,5 % en el
  escaneo plano y de 97,9 % a 85,4 % en la foto inclinada, y `Nº` pasa de
  leerse `N*` a `N®` (sigue mal). No se adoptan ni se exigen.
- **PSM 6 de Tesseract**: por CLI empata en el escaneo plano y arregla las
  cifras de la foto inclinada por CLI, pero el OCR de PyMuPDF (que es el
  que alimenta los spans) ya las lee al 100 %; no se cambia la ruta de OCR.

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
python-docx. Tras los cambios de esta tanda, los tiempos de OCR medidos con
`measure_ocr.py` (solo Excel) se mantienen en el mismo orden: escaneado
3,9 s, foto inclinada 5,4 s, referencia escaneada 14,7 s, escaneado en color
3,8 s, foto con perspectiva 5,5 s.

## Fórmulas de totales (Excel)
Se aplican solo si el PDF etiqueta la fila como TOTAL y la suma de la columna
coincide con la cifra impresa (±0,01). Medido:
- factura.pdf: `G10 =SUM(G7:G9)` (335,00).
- tabla_sin_lineas.pdf: `C6, E6, G6` (totales de Ene/Feb/Mar).
- estado_cuenta_multipagina.pdf: `E12, G12` por página.
- estado_ingresos_octubre_2026.pdf: ninguna (sus totales no son suma directa
  de la columna; no se inventa ninguna fórmula).
- factura_real_logo_sello.pdf (nuevo): la fila SUBTOTAL es fórmula
  `=SUM(...)` de los artículos (335,00); el TOTAL no es fórmula porque
  335,00 + 50,25 no es la suma de la columna (no se inventa).
- tabla_combinada_compleja.pdf (nuevo): TOTAL con fórmula `=SUM(...)` (520,00).
- dos_columnas_tablas.pdf (nuevo): un `=SUM(...)` por tabla (100,50 y 1.545,50).

## Calidad: qué quedó fuera

`info["quality"]` (lo que devuelve la API en `info.quality`) incluye
`missing_sample`: hasta 20 palabras/cifras del PDF que no llegaron al
archivo. Verificado por prueba en los tres destinos borrando la palabra
"Pintura" de cada salida: Excel la nombra (`['pintura', 'blanca', '1.0',
'galón']`), Word y PPTX también (`['pintura']`). Cuando la cobertura es
1,0, `missing_sample` es `[]`.

## Prueba de carga (medida el 26 nov 2026; detalle en `scripts/loadtest/RESULTADOS.md`)

Entorno: VM de 4 vCPU con cuota compartida de 1,5, 7,7 GB RAM, x86_64,
sin Docker ni Redis, API en modo inline (sin workers Celery). **No es
Oracle Always Free (2 OCPU ARM / 12 GB)**: estos números no se pueden
trasladar a Oracle sin medir allí. Los PDFs de carga tenían texto nativo
(sin OCR).

| Prueba | Resultado |
|---|---|
| 1 usuario, 1 pág. → Excel | extremo a extremo 0,30 s |
| 1 usuario, 10 págs. → Excel | extremo a extremo 0,44 s |
| 1 usuario, 50 págs. → Excel | extremo a extremo 1,30 s |
| 1 usuario, 50 págs. → Word | extremo a extremo 11,25 s (Word es ~9× más caro que Excel) |
| Humo, 10 usuarios, 1 min | POST 83, 0 fallos, mediana 100 ms, p95 2,6 s; E2E mediana 3,1 s, p95 11,0 s |
| Carga, 200 usuarios, rampa 10/s, 2 min | POST 169, **0 fallos**, mediana 35 s, p95 99 s; E2E 34, mediana 40 s, p95 103 s; **~43 conversiones/min sostenidas**; 0 trabajos en error |
| Protección, `MAX_QUEUE_JOBS=5`, 20 usuarios, 1 min | 327 intentos, **285 rechazados con 503 (87 %)**, 42 aceptados; E2E mediana 6,4 s |

Lectura: en modo inline Starlette ejecuta las conversiones en un pool de
40 hilos y la GIL satura la CPU, por eso el POST llegó a tardar 35 s de
mediana. El modo inline no es apto para carga; en producción la
conversión va a workers Celery (2 workers × concurrency 2 = 4
conversiones a la vez, recomendado para Oracle). La RSS del proceso
creció de 114 MB a 1,2 GB sin bajar al drenar: por eso el worker se
recicla cada 50 trabajos (`max-tasks-per-child=50`) y tiene límite de
memoria de 1g.
