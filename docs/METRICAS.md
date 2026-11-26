# Métricas de fidelidad (medidas, no estimadas)

Generadas con `python scripts/measure_metrics.py`, `python scripts/measure_ocr.py`
y con las pruebas de `tests/test_converters.py` y `tests/test_fixtures.py`.

## Entorno de medición
- VM Linux, Python 3.12.3, PyMuPDF 2.2, Tesseract 5.3.4 (`spa+eng`).
  OCRmyPDF **no** está instalado en esta VM (es opcional: el código lo
  omite sin error si falta; la CI sí lo instala). Tesseract se perdió al
  recrearse la VM y se reinstaló el 26 nov 2026 (ver §1.7 de
  `docs/INFORME_FINAL.md`).
- Pruebas: **119 passed, 0 failed, 2 warnings** (`pytest -q`, 26 nov 2026,
  120,42 s, re-medido tras la corrección de la prueba de rendimiento de
  Word): 69 de la base + 50 nuevas de la ronda del navegador primero
  (42 estructurales QR + 3 renderizadas + 3 de rendimiento + 2 de Nº).
  Sin Tesseract instalado, 2 pruebas de OCR fallaban; con Tesseract
  5.3.4 instalado, todo pasa.
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
| estado_ingresos_octubre_2026.pdf escaneado a 200 dpi | 100 % → **100 %** | 88,6 % → **88,9 %** | 90,3 % → 90,3 % |
| factura.pdf escaneada a 200 dpi | 100 % → **100 %** | 83,3 % → **100,0 %** | 87,1 % → **100,0 %** |
| factura.pdf como foto inclinada 3° | 100 % → **100 %** | 81,2 % → **97,9 %** | 85,5 % → 96,8 % |
| factura con sello + marca de agua, escaneada en color (nuevo) | — → **100 %** | — → **100,0 %** | — → **100,0 %** |
| foto de celular con perspectiva + 2° (nuevo) | — → **100 %** | — → **97,9 %** | — → 96,8 % |

Los valores de «Texto solo» después son los medidos tras el arreglo del
símbolo `Nº` en OCR (26 nov 2026, `app/converters/extract.py`,
`_fix_ocr_numero()`): el escaneo plano de la factura pasó de 97,9 % a
100,0 % (48/48 tokens) porque el único error que quedaba era el `Nº`
leído como `N?`. La columna «Tokens» conserva los valores medidos antes
del arreglo salvo los dos casos que quedaron en 100 % en todo; no se
re-midió entera tras el arreglo.

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
| estado_ingresos_octubre_2026.pdf | 0,35 s | 1,18 s | 0,65 s |
| factura.pdf | 0,05 s | 0,18 s | 0,06 s |
| estado_cuenta_multipagina.pdf | 0,11 s | 0,43 s | 0,17 s |
| escaneado.pdf (OCR) | 3,94 s | 3,70 s | 4,12 s |
| foto_inclinada.pdf (OCR + enderezado) | 5,63 s | 5,22 s | 5,40 s |

Los tiempos de Word son los medidos tras el arreglo de la lentitud de
Word (26 nov 2026, `scripts/measure_word.py`, mejor de 3): la causa era
que `table.cell()` de python-docx reconstruye la lista completa de celdas
en cada llamada; ahora se usa un índice propio de celdas. Referencia
4,27 s → 1,18 s; tabla grande de 50 filas 1,35 s → 0,36 s; estado de
cuenta de 6 páginas 1,06 s → 0,62 s; estado multipágina 0,67 s → 0,43 s.

Re-medición 26 nov 2026 (tras la corrección de la prueba de rendimiento,
`tests/test_word_perf.py`): referencia 0,76 s (mejor de 5) y 0,78–0,84 s
en 10 repeticiones sueltas; tabla grande 0,36 s; estado 6p 0,58–0,59 s.
La guarda de rendimiento ya no es un tiempo absoluto sino el cociente
Word/Excel (mejor de 3, mismo proceso): referencia 2,70–2,97, tabla
grande 3,48–3,75, estado 6p 3,87–4,04; el cociente apenas se mueve con
carga de CPU (variación <= 8 %), mientras que en GitHub Actions una sola
medición de Word llegó a 3,95 s (corredor ~5x más lento que esta VM) y
tumbó la guarda absoluta antigua en las ejecuciones #126–#132. Con el
código antiguo simulado (`table.cell()` en vez del índice plano) los
cocientes suben a 10,55 / 9,10 / 6,32 y la guarda salta en las 3 pruebas.
Detalle y umbrales (4,5 / 5,6 / 5,2) en el docstring de
`tests/test_word_perf.py`.

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

---

# Navegador (web/) — metodología y mediciones

## Metodología

- **Qué se mide:** tiempo desde que el usuario pulsa «Convertir»
  hasta que el archivo está listo para descargar, por destino y por
  fixture; tamaño de descarga en la primera visita; memoria usada
  por el motor (cuando el navegador la expone); y fidelidad
  (`text_coverage`, `number_coverage`) contra los mismos 12 fixtures
  del servidor.
- **Cómo se mide:** en el navegador, con `performance.now()` en
  `web/app.js` (tiempos) y con la pestaña de red de las herramientas
  de desarrollo (tamaños). Los tiempos se miden 3 veces y se anota
  la mediana. Los fixtures son los de `tests/fixtures/` (servidor)
  y los de `web/tests/fixtures/` (casos hostiles).
- **Emulaciones:** los celulares de gama media y baja se emulan con
  las herramientas de desarrollo del navegador (limitación de CPU y
  de red) y **se avisa de que son emulaciones**: un celular real
  rinde distinto. Cuando se mida en un celular real, se anota el
  modelo y se sustituye la fila.
- **Regla:** si no se midió, la celda dice **«sin medir»**. No se
  inventa ningún número.

## Tamaños de descarga (medidos el 26 nov 2026)

Medido con Node (`zlib`, Brotli calidad 11 y gzip nivel 9) sobre los
archivos que baja el navegador en la primera visita. Los `.traineddata.gz`
ya vienen comprimidos y no bajan más. Vercel comprime con Brotli en
tránsito, así que lo que paga el visitante es la columna Brotli.

| Archivo | Crudo | Brotli | gzip |
|---|---|---|---|
| `web/engine/index.js` (adaptador) | 3,9 KB | 1,5 KB | 1,7 KB |
| `web/engine/dist/worker.js` (motor sin MuPDF) | 2,04 MB | 0,38 MB | 0,50 MB |
| `web/engine/vendor/mupdf/mupdf.js` | 0,10 MB | 0,02 MB | 0,02 MB |
| `web/engine/vendor/mupdf/mupdf-wasm.js` | 0,03 MB | 0,01 MB | 0,01 MB |
| `web/engine/vendor/mupdf/mupdf-wasm.wasm` | 9,93 MB | 3,44 MB | 4,54 MB |
| **Núcleo sin OCR** | **12,10 MB** | **3,85 MB** | **5,07 MB** |
| `dist/tesseract-core-lstm.js` + `.wasm` + `.wasm.js` + `tesseract-worker.min.js` | 6,62 MB | 1,91 MB | 2,46 MB |
| `spa.traineddata.gz` + `eng.traineddata.gz` | 2,94 MB | 2,94 MB | 2,94 MB |
| **OCR completo (adicional al núcleo)** | **9,56 MB** | **4,85 MB** | **5,40 MB** |
| **Núcleo + OCR** | **21,66 MB** | **8,70 MB** | **10,47 MB** |
| Web: `app.js` + `engine.js` + `writers.js` + `config.js` + `styles.css` + `index.html` | 0,06 MB | 0,02 MB | 0,03 MB |
| Web `vendor/`: exceljs 4.4.0 + docx 9.16.0 + pptxgenjs 4.0.1 + fflate 0.8.2 + pdf.js 5.5.207 (+ worker) | 3,97 MB | 0,88 MB | 1,16 MB |
| **Total primera visita sin OCR** | **16,13 MB** | **4,75 MB** | **6,26 MB** |
| **Total primera visita con OCR** | **25,69 MB** | **9,60 MB** | **11,66 MB** |

Capacidad en Vercel Hobby (100 GB/mes, sin contar visitas repetidas:
el Service Worker guarda el motor tras la primera visita):

| Caso | Descarga por visita nueva (Brotli) | Visitas nuevas/mes en 100 GB |
|---|---|---|
| Sin OCR (lo habitual) | 3,85 MB (núcleo) + 0,90 MB (web) = 4,75 MB | ~21.600 |
| Con OCR (solo escaneados) | 8,70 MB + 0,90 MB = 9,60 MB | ~10.600 |

Ojo: el OCR se descarga solo cuando el PDF no tiene texto, así que la
mayoría de visitas pagan solo la fila sin OCR. La cifra de OCR cuenta
los 4 archivos de Tesseract (`core-lstm.js`, `.wasm`, `.wasm.js`,
`worker.min.js`) + los 2 datos de idioma; si el navegador no llega a
pedir el `.wasm.js` (depende de cómo cargue el núcleo), la descarga
real es menor. Eso se mide en la prueba de navegador con OCR, que
queda pendiente.

**Verificación de los escritores (26 nov 2026, Node con las
librerías vendidas):** con un modelo de prueba, `writeExcel` (los
3 diseños: por página, continuo, por tabla), `writeWord`,
`writePptx` y el ZIP producen archivos válidos; el `.xlsx` se
reabre con ExcelJS y la cifra queda como número (`150.5`, tipo
`number`) y la celda dudosa con relleno amarillo (`FFFFF2CC`).
Los tres archivos se abren en LibreOffice y se convierten a PDF
sin errores.

**Verificación del motor en el navegador (26 nov 2026, Playwright):**
`web/engine/index.js` + `dist/worker.js` existen tras `npm run build`
en `web/engine/` (Vite 8, MIT). La web convierte de verdad:
factura → Excel en Chromium con calidad texto 100 % / cifras 100 %
y TOTAL 335 en el `.xlsx`; factura → Word en Pixel 7. Detalle en
`tests/browser/README.md`.

## Tiempos de conversión en el navegador

Medido el 26 nov 2026 con Playwright en la VM de trabajo (una sola
ejecución por caso, no mediana de 3; sirve como orden de magnitud).
El tiempo es desde que se pulsa «Convertir» hasta que el archivo está
listo para descargar, con el motor ya cargado en la primera conversión
de la sesión (la carga del motor —worker 2,04 MB + WASM 9,93 MB—
ocurre una sola vez por visita).

| Dispositivo | Fixture | Excel | Word | PPTX |
|---|---|---|---|---|
| PC normal (Chromium, VM) | factura.pdf (1 pág.) | 5,6 s (web real) | sin medir | sin medir |
| Celular gama media (Pixel 7 emulado) | factura.pdf (1 pág.) | sin medir | 5,0 s (web real) | sin medir |
| Celular gama baja (Pixel 7 + CPU 4x) | factura.pdf (1 pág.) | sin medir | sin medir | sin medir |

Conversión a los 3 destinos seguidos con el worker directo
(`tests/browser/privacy.spec.js`, factura.pdf, 1 pág.):

| Dispositivo | Tiempo total (Excel + Word + PPTX) |
|---|---|
| PC normal (Chromium, VM) | 2,4 s |
| Celular gama baja (Pixel 7 + CPU 4x) | 4,7 s |
| PC normal (Firefox) | 3,5 s |

Sin medir todavía: estado de cuenta de varias páginas en el navegador,
PDF de 10 páginas a Excel (objetivo: pocos segundos en PC normal),
tiempos con OCR en el navegador, y cualquier medida en un celular real
o en WebKit (WebKit no se ejecuta en esta VM; en CI sí).

Los tiempos del servidor (arriba en este documento) **no** se trasladan
al navegador: el motor del navegador es otro código (MuPDF.js +
tesseract.js) y hay que medirlo aparte, en cada dispositivo.

## Fidelidad en el navegador

| Fixture | Excel texto/cifras | Word texto/cifras | PPTX texto/cifras |
|---|---|---|---|
| factura.pdf (web real, Chromium) | 1,0 / 1,0 (calidad mostrada por la web) | sin medir | sin medir |
| factura.pdf (web real, Pixel 7) | sin medir | 1,0 / 1,0 (el texto llega al .docx) | sin medir |
| 10 fixtures nativos × 3 destinos (motor en Node, `matrix.mjs`) | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |

### Paridad contra el oráculo Python (42 PDFs, 26 nov 2026)

`scripts/parity.py --ocr off --visual`: 252 filas, 0 errores.
Resultados en `scripts/parity/parity_results.json` y `.csv`; resumen
completo en `docs/INFORME_FINAL.md` §3.

| Destino | Navegador texto / cifras (33 nativos) | Celdas (19 fixtures, 858 celdas) |
|---|---|---|
| Excel | 0,9982 / 1,0 | 0,9463 (825/858), idéntico a Python |
| Word | 0,9982 / 1,0 | **1,0 (858/858)**, igual que Python (era 0,829 antes de la decisión grid/flow por cifras aisladas) |
| PowerPoint | 0,9982 / 1,0 | 1,0 (858/858), igual que Python |

El único texto que falta es en `estado_ingresos_octubre_2026.pdf`
(0,9406). Imágenes en Word del navegador (dibujos `<a:blip>`):
escaneos 1/1 y 2/2 (sin duplicar); en Excel el fondo del escaneo no
se copia a propósito (el texto OCR ya está en las celdas); en PPTX
1/1 y 2/2, igual que Python. Tiempos medios por conversión en Node:
Excel 1,69 s, PPTX 1,76 s, Word 1,85 s (corrida final, con pytest en
paralelo en la misma VM; sin carga paralela: 1,08 / 1,00 / 1,14 s).

La paridad completa contra el oráculo Python (42 PDFs del conjunto de
oro, con celdas, rellenos, bordes, combinadas, imágenes y métrica visual)
está en `scripts/parity/parity_results.json` y se resume en
`docs/INFORME_FINAL.md`.

## Casos hostiles (`web/tests/`)

| Caso | Resultado |
|---|---|
| 12 casos de `web/tests/fixtures/` | sin medir (ver `web/tests/hostile-cases.md`) |

## Pruebas en navegador real (Playwright)

Playwright 1.65.1 (Apache-2.0). Medido el 26 nov 2026 en la VM de
trabajo (detalle y cómo ejecutar: `tests/browser/README.md`):

| Prueba | Resultado |
|---|---|
| convert.spec.js Chromium: factura → Excel | pasa en 5,6 s; calidad texto 100 % / cifras 100 %; TOTAL 335 en el .xlsx; 0 peticiones fuera del origen local |
| convert.spec.js móvil Pixel 7: factura → Word | pasa en 5,0 s; «335» en el .docx; 0 peticiones fuera del origen local |
| privacy.spec.js Chromium: 3 destinos | pasa en 2,4 s; 6 peticiones estáticas locales, 0 externas |
| privacy.spec.js móvil CPU 4x: 3 destinos | pasa en 4,7 s; 0 peticiones externas |
| privacy.spec.js Firefox: 3 destinos | pasa en 3,5 s; 0 peticiones externas |
| WebKit | sin medir en esta VM (sin dependencias del SO); en CI con `--with-deps` |

Pendiente en el navegador real: conversión con OCR (escaneado),
estado de cuenta de varias páginas, los 12 casos hostiles de
`web/tests/` y el corrector de celdas dudosas con un escaneado real.
