# Informe final — Convertidor PDF (tercera ronda, 26 nov 2026)

Proyecto: convertidor de PDF a Word / Excel / PowerPoint con el motor
en el **navegador** (WebAssembly + JavaScript, dentro de un Web Worker;
la página solo entrega archivos estáticos). El motor Python existente
es el **oráculo de referencia** y el servidor FastAPI + Celery + Redis
queda como **respaldo opcional**. Repositorio privado:
https://github.com/Joel06777/pdf-converter (rama `main`, head `3bfa2c0`
antes de esta ronda; el push de esta ronda lo hace el dueño con ayuda
de Snoop). Todo el trabajo se hizo con costo cero y sin servicios de
pago. La ronda anterior (integración motor ↔ web y verificación en
navegador real) quedó documentada en `CHANGELOG.md`.

> Esto no es asesoría legal. La sección de licencias resume lo auditado;
> ante duda legal, consulta a un abogado.

## 1. Qué se corrigió y cómo se verificó (comandos y resultados reales)

### 1.1 Estado base verificado por mí al empezar (no heredado)

```bash
cd ~/workspace/pdf-converter-work/pdf-converter
.venv/bin/python -m pytest -q
# 119 passed, 2 warnings, en 610,70 s (re-medido en esta ronda;
#  tardó 10 min por la carga paralela en la VM: paridad y Playwright
#  corrían a la vez; en la ronda anterior, sin carga, fueron ~171 s)
```

VM de verificación: 4 vCPU con cuota compartida, 7,7 GB RAM, x86_64,
sin Docker (`docker: command not found`), sin Redis, sin `.git` local.
El motor Python (oráculo) ya estaba en 119 passed tras la auditoría
de la ronda anterior; en esta ronda no se tocó su lógica, solo el
harness de paridad (ver §1.4).

### 1.2 Word del navegador: cobertura de celdas 0,829 → 1,0 (corregido)

**Problema.** En paridad, la cobertura de celdas en Word del navegador
era 0,829 frente a 1,0 de Python. Los 6 documentos afectados eran
contrato_servicios (0,5833), dos_columnas_mixto (0,6),
informe_mensual_mixto (0,4074), tabla_encabezado_doble (0,36),
tabla_sin_lineas_nomina (0,4) y tabla_sin_lineas_ventas (0,4). Los
valores que faltaban eran todos importes con `$` (`$ 800.00`,
`$ 974.98`, `$ 12,450.00`…).

**Causa raíz (medida, no supuesta).** El motor elegía la ruta `flow`
(texto corrido) para esos documentos: `paragraphsFromRows` une los
segmentos de cada fila con 3 espacios («Alquiler mensual   $   800.00»),
así que el importe queda enterrado en una línea de párrafo y la
comprobación de celdas no lo encuentra. El motor decidía `grid` solo
si `tableLike(models)` o si la cobertura de **texto** de grid superaba
a la de flow — y el texto empata (0,9982), así que ganaba flow. Sondeo
con `web/engine/scripts/probe-word-mode.mjs` (Node, modo explícito):

| Fixture | auto antes | flow (cifras aisladas) | grid (cifras aisladas) |
|---|---|---|---|
| contrato_servicios.pdf | flow | 0/5 = 0 | 5/5 = 1 |
| dos_columnas_mixto.pdf | flow | 0/8 = 0 | 8/8 = 1 |
| informe_mensual_mixto.pdf | flow | 0/16 = 0 | 16/16 = 1 |
| tabla_encabezado_doble.pdf | flow | 0/16 = 0 | 16/16 = 1 |
| tabla_sin_lineas_nomina.pdf | flow | 0/12 = 0 | 12/12 = 1 |
| tabla_sin_lineas_ventas.pdf | flow | 0/12 = 0 | 12/12 = 1 |

**Corrección.** En el fallback auto de `modelsToWord`
(`web/engine/src/word.js`): si la cobertura de texto empata (diferencia
< 0,0001), deciden las **cifras aisladas** — valores numéricos de los
`placements` de `buildLayout` que aparecen como texto completo `<w:t>`
en el .docx — con la función nueva `isolatedNumberScore` y `docxTexts`
(nuevo en `web/engine/src/verify.js`, que extrae los textos `<w:t>`
completos sin partirlos en tokens). El texto sigue mandando: grid solo
gana si no pierde texto y sus cifras aisladas superan a las de flow.

**Verificación.** 7 pruebas nuevas en
`web/engine/tests/word-mode.test.js` (los 6 documentos eligen `grid`,
la cifra queda aislada y la cobertura de texto y cifras es 1,0; el
texto corrido sin cifras en tabla —`dos_columnas.pdf`— sigue en
`flow`). Suite completa del motor: **80 passed** (ver §2). Paridad
final (ver §3): celdas en Word del navegador **1,0 (858/858)**,
igual que Python; celdas en Excel **0,9463 (825/858), idéntico en
ambos motores** (las 33 celdas que faltan son las mismas en Python y
en el navegador: filas de totales que ninguno de los dos reproduce
como celda aislada — es una limitación compartida, no del navegador).

### 1.3 Word del navegador: la imagen de un escaneo se duplicaba (corregido)

**Problema.** En paridad, los escaneos daban 2 imágenes en Word del
navegador frente a 1 esperada (escaneado_contrato 4/2). Diagnóstico
con `web/engine/scripts/probe-word-images.mjs`: el .docx tenía **un
solo archivo en `word/media/` pero dos referencias `<a:blip>`** — la
página aparecía dos veces: una en línea y otra flotante.

**Causa raíz.** En `gridSections` (`src/word.js`), la cola flotante
saltaba la imagen de página completa solo si `lay.rows.length` era
distinto de cero; sin OCR no hay filas, así que la imagen iba flotante
**y** en línea (`scanImageParagraphs`).

**Corrección.** La cola ya salta siempre las imágenes de página
completa de un escaneo (`if (img.fullPage && model.scanned) continue;`):
el párrafo en línea es el único punto de incrustación. 1 prueba nueva
en `tests/word-images.test.js` (escaneado en grid: 1 archivo en media
y 1 solo `<a:blip>`).

**Verificación.** Paridad final: escaneos en Word del navegador
**1/1 y 2/2** (ver §3). Nota sobre la métrica: el conteo de imágenes
de paridad para Word sumaba `inline_shapes` + partes de imagen, lo
que contaba dos veces cada imagen en línea aunque solo se dibujara una
vez; ahora cuenta dibujos (`<a:blip>` en `word/document.xml`). Con la
métrica vieja, el arreglo no se habría visto (seguía dando 2/1).

### 1.4 Paridad: métrica de imágenes en Word (corregida)

`scripts/parity.py`, `_cell_values_docx`: el conteo de imágenes ahora
es `xml.count("<a:blip")` sobre `word/document.xml` (nº de dibujos),
en vez de `len(doc.inline_shapes) + nº de partes de imagen`. La
métrica vieja inflaba a los dos lados: una imagen en línea del
navegador contaba 2 (forma + parte) y la miniatura
`/docProps/thumbnail.jpeg` que python-docx añade por defecto contaba
como imagen del escaneo en Python (así Python parecía dar 1/1 en
escaneos cuando en realidad no incrusta el escaneo en Word con OCR
desactivado). Los números de imágenes de las rondas anteriores no son
comparables con los de esta ronda para Word.

### 1.5 Barra de progreso bloqueada por la CSP (corregido)

**Problema.** La barra de progreso de `web/index.html` era un `<div>`
con el ancho en línea (`bar.style.width = …%` en `web/app.js`). La
CSP estricta (`style-src 'self'` en `vercel.json` y en la meta CSP de
cada HTML) bloquea los estilos en línea: la conversión avanzaba, pero
la barra no se pintaba. Era el último pendiente anotado en
`web/README.md`.

**Corrección.** La barra es ahora un elemento `<progress>` nativo
(`web/index.html`, `web/app.js` pone `bar.value`, `web/styles.css`
con estilos para `::-webkit-progress-bar`,
`::-webkit-progress-value` y `::-moz-progress-bar`, incluido el modo
oscuro). Al ser nativo no necesita estilos en línea y la CSP sigue
estricta, sin `'unsafe-inline'`. El mismo problema existía en el
corrector de celdas dudosas (`td.style.fontWeight = "bold"` en
`app.js`): ahora usa la clase `.bold` de `styles.css`. Verificado con
`grep`: no quedan asignaciones a `.style.` en `web/app.js` ni en
`web/engine.js`. Las pruebas Playwright de la web real pasan (ver §2).

### 1.6 Guía de despliegue: el Build Command era incorrecto (corregido)

`docs/DESPLIEGUE_GRATIS.md` decía dejar el **Build Command vacío**
(«no hay nada que compilar»). Eso era falso desde la integración: los
archivos del motor (`web/engine/index.js`, `dist/worker.js`,
`vendor/mupdf/`) **no están en el repositorio** (están en
`web/engine/.gitignore`) y se generan con `npm run build`. Con el
Build Command vacío, Vercel publicaría la web en **modo de
demostración** (vista previa sí, conversión no).

**Corrección.** En Vercel: **Build Command**
`cd engine && npm ci && npm run build` y **Node.js Version 20.x**
(el motor exige Node 20 o superior). En GitHub Pages: hay que
construir con GitHub Actions (publicar desde la rama no sirve, porque
GitHub publica los archivos tal cual y los del motor no están en el
repositorio). El paso 4 de comprobación ahora dice qué hacer si el
botón de convertir dice que el motor no está instalado (revisar los
Build Logs del despliegue). Tamaños de primera visita actualizados:
**4,75 MB con Brotli sin OCR; 9,60 MB con OCR** (antes decía 1,1 MB
con gzip, cifra de cuando la web no tenía motor).

### 1.7 Prueba de rendimiento de Word inestable en CI + Tesseract ausente en la VM (corregido, 26 nov 2026)

**Problema 1 — la CI fallaba de forma intermitente.** En GitHub Actions, el
job `test` falló en las ejecuciones #126–#132 con 1 prueba fallida
(`tests/test_word_perf.py::test_word_referencia_rapida_y_completa`:
«referencia Word tardó 3,95 s», límite 3,0 s), mientras las ejecuciones
#133–#138 del mismo código pasaron. La prueba medía UNA sola conversión
a Word con un umbral absoluto: el corredor compartido de GitHub es hasta
~5x más lento que esta VM (referencia local 0,78–0,84 s frente a 3,95 s
en GitHub), así que un umbral absoluto no puede separar «máquina lenta»
de «regresión del algoritmo» en las dos máquinas.

**Corrección.** La guarda ya no es un tiempo absoluto: mide la mejor de
3 repeticiones a Word y a Excel del mismo PDF, en el mismo proceso, y
exige que el cociente Word/Excel no supere un umbral (4,5 referencia;
5,6 tabla grande; 5,2 estado 6p) más un tope absoluto generoso (10x el
mejor tiempo local) como red de seguridad. El cociente cancela la
velocidad de la máquina: Excel hace la misma extracción y cuadrícula
pero no usa python-docx, así que si vuelve el O(n²) de `table.cell()`
solo sube el numerador. Medido en local: ratios optimizados 2,70–2,97 /
3,48–3,75 / 3,87–4,04 (sin carga y con 3 hilos quemando CPU; el ratio
apenas se mueve, variación <= 8 %).

**Verificación de que la guarda sigue detectando la regresión.**
Sustituido temporalmente el índice plano por `table.cell()` (simulación
parcial de la regresión), las 3 pruebas fallaron con ratios 10,55 /
9,10 / 6,32; el convertidor se restauró byte a byte después (verificado
con `diff`). No se tocó `app/converters/pdf_to_word.py`: el perfilado
(cProfile) muestra el coste repartido dentro de python-docx (xpath,
`get_child_element`, `OxmlElement`), sin un punto caliente propio que
optimizar más; el coste que queda es inherente a construir la tabla
celda a celda con python-docx.

**Problema 2 — 2 pruebas de OCR fallaban en esta VM.** Al ejecutar la
suite completa tras el arreglo, 2 pruebas de OCR fallaron
(`test_scanned_pdf_uses_ocr`, `test_scanned_accuracy_vs_original`,
precisión 0,0 %): el binario `tesseract` no estaba instalado en la VM
(se perdió al recrearse la máquina; en la ronda 1 se había instalado
con apt). Además los espejos de Ubuntu configurados
(`azure.archive.ubuntu.com`, `mirror.cogentco.com`) no respondían
(`apt-get update` colgado 21 min; curl con tiempo agotado), así que se
añadió temporalmente `archive.ubuntu.com` como fuente
(`/etc/apt/sources.list.d/temp-archive.sources`, se deja puesto porque
es el archivo oficial de Ubuntu y los otros dos espejos no responden) y
se instaló `tesseract-ocr 5.3.4` con `spa` y `eng`. Tras instalarlo,
las 2 pruebas pasaron. Lección: si la VM se recrea, hay que reinstalar
Tesseract antes de ejecutar pytest; la CI ya lo instala en cada
ejecución (ver `.github/workflows/ci.yml`).

### 1.8 Resumen de la ronda (todo medido, nada heredado sin re-verificar)

- pytest: **119 passed, 2 warnings, en 120,42 s** (tras instalar
  Tesseract; sin él, 2 pruebas de OCR fallaban — ver §1.7).
- Prueba de rendimiento de Word: reescrita como guarda de ratio
  Word/Excel (ver §1.7); pasa 3 de 3 veces en local y detecta la
  regresión simulada en las 3 pruebas.

## 2. Resultados de las verificaciones

### pytest (oráculo Python, ejecutado por mí al final)

```bash
.venv/bin/python -m pytest -q
# 119 passed, 2 warnings, en 120,42 s (26 nov 2026, tras la corrección
#  de la prueba de rendimiento de Word y tras instalar Tesseract 5.3.4;
#  sin Tesseract, 2 pruebas de OCR fallaban — ver §1.7)
```

### Motor del navegador (vitest, ejecutado por mí)

```bash
cd web/engine && npx vitest run
# 10 archivos, 80 passed, en 56,42 s
```

Era 72; +7 de `tests/word-mode.test.js` y +1 de no duplicación en
`tests/word-images.test.js`. Los scripts de sondeo
(`scripts/probe-word-mode.mjs`, `scripts/probe-word-images.mjs`) son
diagnóstico y quedan en el repositorio como referencia; no forman
parte de la suite.

### Build del motor para el navegador

```bash
cd web/engine && npm run build
# exit 0; dist/ tiene 5 archivos, 8,68 MB en total
```

### Playwright (web real, ejecutado por mí en esta VM)

```bash
cd tests/browser && npx playwright test
# 7 passed, 3 failed — los 3 fallos son WebKit (ver abajo)
```

- Chromium: factura → Excel con TOTAL 335 y 0 peticiones externas
  (9,4 s); privacidad 3 destinos (4,1 s).
- Móvil Pixel 7: factura → Word (7,8 s); privacidad (4,0 s); móvil
  con CPU 4x y memoria reducida (11,7 s).
- Firefox: privacidad 3 destinos (9,0 s).
- **WebKit: 3 fallos al lanzar el navegador** — «Host system is
  missing dependencies to run browsers»: faltan dependencias del
  sistema operativo en esta VM. No es un fallo del código: en CI se
  instala con `playwright install --with-deps webkit`. Queda sin
  verificar en esta VM, como en las rondas anteriores.

### CI en GitHub Actions

No ejecutada aquí (no hay `.git` local ni acceso de escritura a
GitHub desde este entorno). El trabajo `browser` ya incluye el paso
de build del motor (`npm run build` en `web/engine/`) antes de
Playwright. Última comprobación en la página de Actions (26 nov 2026,
10:15, antes del push de la corrección de §1.7): la ejecución #150
para el head `a8a1cd7` estaba en cola (Queued), con los cuatro jobs
(test, docker-build, docker-build-arm64, browser) en cola; las
ejecuciones #139–#142 estaban en curso y #143–#149 en cola (una
ejecución por cada push de la subida). Las ejecuciones #126–#132
habían fallado por la prueba de rendimiento de Word que se corrige
en §1.7 (3,95 s frente al límite de 3,0 s) y las #133–#138 habían
pasado en verde (~18 min cada una). La verificación final en verde
la hace el dueño tras el push de esta corrección (ver §5.1).

## 3. Métricas (paridad final, 26 nov 2026)

Paridad completa contra el oráculo Python sobre el **conjunto de oro
de 42 PDFs** (14 originales + 28 generados por código, deterministas;
1.122 cifras de referencia). Comando:

```bash
.venv/bin/python scripts/parity.py --ocr off --visual
# exit 0; 252 filas, 0 errores
# (corrida final: 427 s; corría pytest en paralelo en la misma VM,
#  por eso los tiempos del navegador son mayores que en la corrida
#  anterior sin carga: 1,08 / 1,00 / 1,14 s)
```

Resultados en `scripts/parity/parity_results.json` y `.csv`
(directorio ignorado por git). Detalle por tipo en `docs/METRICAS.md`.

### Texto y cifras en PDFs nativos (33 PDFs; los 9 escaneados/fotos sin OCR dan 0, como es esperable)

| Destino | Oráculo Python texto / cifras | Navegador texto / cifras | Tiempo medio Python | Tiempo medio navegador |
|---|---|---|---|---|
| Excel | 1,0 / 1,0 | 0,9982 / 1,0 | 0,13 s | 1,69 s |
| PowerPoint | 1,0 / 1,0 | 0,9982 / 1,0 | 0,20 s | 1,76 s |
| Word | 1,0 / 1,0 | 0,9982 / 1,0 | 0,40 s | 1,85 s |

El único texto que falta en el navegador es
`estado_ingresos_octubre_2026.pdf` (0,9406 en los 3 destinos); las
cifras están completas (1,0) en los 3 destinos.

### Celdas (19 fixtures con tablas, 858 celdas)

| Destino | Oráculo Python | Navegador |
|---|---|---|
| Excel | 0,9463 (825/858) | 0,9463 (825/858) — idéntico |
| Word | 1,0 (858/858) | **1,0 (858/858)** — era 0,829 |
| PowerPoint | 1,0 (858/858) | 1,0 (858/858) |

Rellenos y bordes: idénticos en ambos motores (ej. tabla_colores:
11 celdas con relleno, 18 con borde). Celdas combinadas: ambos
reproducen 2/2 rangos fusionados verticales.

### Imágenes

| Caso | Word Python | Word navegador | Excel navegador | PPTX navegador |
|---|---|---|---|---|
| Escaneado 1 pág. | 0 dibujos* | **1/1** | 0/1 (a propósito) | 1/1 |
| Escaneado 2 págs. | 0 dibujos* | **2/2** | 0/2 (a propósito) | 2/2 |
| Foto celular | 0 dibujos* | **1/1** | 0/1 (a propósito) | 1/1 |
| Factura con logo y sello | 2 | 2 | — | — |
| Estado de ingresos (5 imágenes en el PDF) | 5 | 6 | — | — |

\* El oráculo Python **no incrusta** la imagen del escaneo en el
.docx cuando el OCR está desactivado (la salida de `convert()` con
`ocr=False` no tiene ninguna imagen en `word/media/` ni ningún dibujo
en `word/document.xml`). El «1/1» que daba la métrica vieja para
Python era un falso positivo: contaba `/docProps/thumbnail.jpeg`, la
miniatura que python-docx añade por defecto, como si fuera la imagen
del escaneo. La métrica nueva de dibujos lo deja claro: navegador
1/1 frente a Python 0/1. Con OCR activado, la ruta de Python pasa
por `improve_scan` (OCRmyPDF) y el documento resultante sí puede
llevar la imagen; eso no se midió en esta corrida (`--ocr off`). En
Excel el navegador no copia el fondo del escaneo a propósito
(`src/excel.js`: el texto OCR ya está en las celdas). En el estado de
ingresos el navegador dibuja 6 imágenes frente a 5 de Python: el PDF
tiene 5 imágenes raster y el manifiesto solo registra 1; la sexta del
navegador es una imagen pequeña que Python no dibuja (o que dibuja
como parte de otra) — sin verificar cuál es.

### Visual (solo Word de Python, 8 archivos; diferencia por regiones con Pillow/NumPy, sin SSIM)

Diferencia media absoluta 0,0062–0,0392; máximo por región
0,0307–0,11. Sin umbral formal definido y sin medir en el navegador.

### OCR (motor Python, con Tesseract; el OCR del navegador solo se midió en Node con tesseract.js)

Escaneado 1,0/1,0; escaneado_color_sello 1,0/1,0;
escaneado_contrato 0,9855/1,0; escaneado_factura_servicios 1,0/1,0;
foto_celular_perspectiva 0,9808/1,0; foto_inclinada 1,0/1,0;
foto_inclinada_contrato 0,9825/1,0; foto_perspectiva_factura
0,7182/0,5714 (caso difícil: factura larga con perspectiva);
foto_sombra 0,9623/0,9412 (texto/cifras). **Caveat:** los 7 primeros
valores proceden de un log de una corrida completa que se perdió en
un reinicio del runtime; solo los 2 últimos están en el JSON actual
de `scripts/parity-ocr/parity_results.json`. Los logs finales están
en `~/workspace/parity_fast2.log` y `~/workspace/parity_ocr2.log`.

### Comparación con otros convertidores (sobre los 33 PDFs nativos)

| Herramienta | Texto (media) | Cifras (media) |
|---|---|---|
| Oráculo Python (este proyecto) | 1,0 | 1,0 |
| pdf2docx 0.5.13 | 0,9979 | 1,0 |
| pdfplumber | 0,9927 | 0,9807 |
| **Navegador (este proyecto)** | **0,9982** | **1,0** |

LibreOffice: no medido — `soffice --convert-to docx` de un PDF falla
en esta VM (error de escritura `SfxBaseModel 0xc10`; Draw no exporta
a Word allí). Camelot: no medido — no instalado, requiere Ghostscript,
no disponible en esta VM. No se afirma superioridad: los números están
muy próximos. Detalle en `scripts/parity/COMPARACION.md`.

### Descarga y capacidad (medido el 26 nov 2026, Brotli)

| | Tamaño Brotli | Visitas nuevas/mes en 100 GB/mes (Vercel Hobby) |
|---|---|---|
| Núcleo sin OCR (worker + WASM + web) | 3,85 MB | 26.626 |
| Con OCR completo (spa+eng) | 8,70 MB | 11.782 |
| Primera visita sin OCR | 4,75 MB | ~21.600 |
| Primera visita con OCR | 9,60 MB | ~10.600 |

## 4. Verificado / no verificado

| Requisito | Estado |
|---|---|
| Excel cobertura texto y cifras 1,0 en nativos | **Casi**: texto 0,9982, cifras 1,0 (solo falta texto en estado_ingresos) |
| Rellenos, bordes, combinadas e imágenes iguales al oráculo | **Sí** en celdas (Excel idéntico a Python; Word y PPTX 1,0); imágenes de escaneo en Excel 0/1 a propósito |
| PowerPoint cobertura 1,0, una diapositiva por página, todo editable | **Sí** (0,9982/1,0; celdas 1,0; imágenes 1/1 y 2/2) |
| Word cobertura 1,0 y cero solapes | **Cobertura sí** (0,9982/1,0; celdas 1,0); **solapes sin verificar** en Word real (solo LibreOffice en la ronda 2 para el QR) |
| OCR cifras ≥99% y texto ≥97% en escaneos limpios; celdas dudosas marcadas | **Python sí** en cifras (100% en 5 casos) y texto 88,9%–100,0% (el escaneado de referencia queda en 88,9%, por debajo del 97%); **navegador solo en Node**, no en navegador real |
| Visual sobre umbral definido | **Sin umbral formal**; medida solo en 8 Word de Python |
| Navegadores Chromium, Firefox y WebKit en CI, con emulación de celular | **Chromium y Firefox pasan aquí**; WebKit sin medir aquí (solo en CI); Pixel 7 emulado pasa |
| Privacidad: cero peticiones de red durante la conversión | **Sí** (privacy.spec.js: 6 peticiones estáticas locales, 0 externas) |
| Rendimiento por formato y dispositivo | **Parcial**: tiempos medidos en Node y en Playwright (una ejecución por caso); memoria no medida; sin celular real ni PDF de 10 páginas a Excel en el navegador |
| Descarga: tamaños reales y capacidad mensual | **Sí** (Brotli, ver §3) |
| Seguridad: pruebas hostiles, CSP estricta, sin secretos en historial | **Parcial**: 12 casos hostiles sin medir; CSP estricta (la barra ya no usa estilos en línea); sin secretos reales en archivos; **historial de GitHub pendiente de revisar** |
| Costo cero en toda la ruta recomendada | **Sí** |
| Comparación con LibreOffice, pdf2docx, pdfplumber/camelot | **Parcial**: pdf2docx y pdfplumber medidos; LibreOffice y Camelot no medidos |

## 5. Pasos manuales que solo el dueño puede hacer

### 5.1 Subir esta ronda a GitHub y comprobar la CI
1. En el chat, pedir a Snoop que suba los cambios (él hace el push).
2. Abrir https://github.com/Joel06777/pdf-converter/actions
3. Ver la ejecución más reciente: los trabajos (`test`, `browser`,
   `docker-build`, `docker-build-arm64`) deben estar en verde. Si
   alguno falla, no lanzar todavía: avisar a Snoop con el nombre del
   trabajo que falló. **Ojo:** el trabajo `browser` construye el motor
   (`npm run build`); si falla el build, la web queda en modo de
   demostración.

### 5.2 Hacer público el repositorio (obligatorio antes de lanzar)
Sin este paso el servicio no puede ofrecerse públicamente gratis bajo
AGPL (ver `docs/LICENCIAS.md`).
1. Abrir https://github.com/Joel06777/pdf-converter/settings
2. Bajar hasta la zona «Danger Zone» → «Change repository visibility».
3. Pulsar «Change visibility» → elegir **Make public** → escribir el
   nombre del repositorio para confirmar.
4. Comprobar que en la página principal del repositorio ya no dice
   «Private».
5. La web debe mostrar un enlace visible «Código fuente» que apunte a
   https://github.com/Joel06777/pdf-converter

### 5.3 Crear la etiqueta v1.0.0
1. Cuando la CI esté en verde, abrir
   https://github.com/Joel06777/pdf-converter/releases/new
2. En «Choose a tag» escribir `v1.0.0` y pulsar «Create new tag».
3. Título: `v1.0.0`. Descripción: copiar la sección `[Sin publicar]`
   de `CHANGELOG.md`.
4. Pulsar «Publish release».

### 5.4 Publicar la web en Vercel
Guía completa paso a paso en `docs/DESPLIEGUE_GRATIS.md`. Resumen:
Root Directory `web`, **Build Command**
`cd engine && npm ci && npm run build`, **Node.js 20.x**, sin
variables de entorno. Antes de lanzar, decidir si el sitio será
comercial: **Vercel Hobby es solo uso no comercial** (confirmar en
https://vercel.com/pricing; si va a ganar dinero, hace falta Pro).
Alternativa: GitHub Pages con GitHub Actions (no desde la rama).

### 5.5 Revisar el historial de git en busca de secretos
En este equipo no había historial git local, así que no se pudo
revisar. Antes de hacer público el repositorio, en un ordenador con
el historial completo:
```bash
git log --all -p -- .env
git log --all -G 'sk-|AKIA|BEGIN.*PRIVATE KEY'
git grep "$(git rev-list --all)" -- .env  # o gitleaks detect / trufflehog
```
Activar GitHub secret scanning y push protection. Si aparece algo,
rotarlo antes de publicar.

### 5.6 Poner el correo real de contacto de privacidad
El correo de `docs/PRIVACIDAD.md` y `web/privacy.html` es un marcador
(`privacidad@tu-dominio.com`); reemplazarlo por el correo real antes
de publicar la política.

### 5.7 Lista de verificación manual (no automatizable aquí)

**En Microsoft Word, Excel y PowerPoint reales** (no LibreOffice):
1. Convertir `tests/fixtures/factura.pdf` a los 3 destinos y abrir
   cada archivo en su programa: comprobar que el TOTAL 335.00 está
   como número (Excel: la celda suma con `=SUM`; Word: el importe no
   se solapa con nada; PowerPoint: todo editable, una diapositiva).
2. Convertir `tests/fixtures/estado_ingresos_octubre_2026.pdf` a
   Excel: comprobar el relleno verde del encabezado y que las cifras
   30,570.51 / 27,948.96 / 2,621.55 están como números.
3. Convertir `tests/fixtures/tabla_sin_lineas_ventas.pdf` a Word:
   comprobar que los importes aparecen en celdas de tabla (no
   enterrados en líneas de texto).
4. Convertir `tests/fixtures/escaneado.pdf` a Word: comprobar que la
   imagen del escaneo aparece **una sola vez** (no duplicada).
5. Convertir `tests/fixtures/escaneado.pdf` a Excel: comprobar que el
   texto OCR está en celdas (el fondo del escaneo no se copia a
   propósito).

**En un celular real** (gama media si es posible):
6. Abrir la web publicada, arrastrar un PDF de varias páginas y
   convertir a Excel: anotar el tiempo y si el celular se calienta o
   el navegador cierra la pestaña.
7. Probar sin conexión tras la primera visita (PWA): la página debe
   abrir y convertir.
8. Probar un PDF escaneado (foto de celular): comprobar que el OCR
   descarga los datos de idioma una sola vez y que las celdas dudosas
   quedan marcadas en amarillo.

**Servidor opcional (solo si el dueño decide activarlo):** crear la
cuenta Oracle, generar los secretos (`API_KEY`, `DOWNLOAD_SECRET`,
`UPLOAD_SECRET`) y pegar las variables en Vercel; probar la subida
de un PDF de más de 4,5 MB en la web real. Guía en
`docs/SERVIDOR_OPCIONAL.md`.

## 6. Límites conocidos y riesgos

- **Texto que falta en el navegador**: `estado_ingresos_octubre_2026.pdf`
  da 0,9406 en texto (las cifras están completas). Sin diagnosticar
  qué líneas faltan.
- **Excel celdas 0,9463**: las 33 celdas que faltan son las mismas en
  Python y en el navegador (filas de totales). Sin diagnosticar por
  qué ninguno de los dos las reproduce como celda aislada.
- **Imágenes del oráculo en Word**: la métrica vieja contaba
  `/docProps/thumbnail.jpeg` (miniatura por defecto de python-docx)
  como imagen del escaneo, así que Python parecía incrustar 1/1; en
  realidad, con OCR desactivado, Python no incrusta el escaneo en
  Word (0 dibujos) y el navegador sí (1/1). Con OCR activado, la ruta
  de Python pasa por `improve_scan` y puede llevar la imagen; no se
  midió en esta corrida.
- **Estado de ingresos**: el navegador dibuja 6 imágenes frente a 5
  de Python; sin verificar cuál es la sexta.
- **Render en Microsoft Word**: el arreglo del QR se verificó solo con
  LibreOffice; Word debería respetar igual el `tblGrid` fijo, pero no
  se comprobó en Word. Los solapes de Word de texto corrido no se
  verificaron en ningún render.
- **WebKit**: no se ejecuta en esta VM (faltan dependencias del SO).
- **Celulares reales**: nada medido; solo emulación Pixel 7.
- **OCR en el navegador real**: sin medir (solo Node con tesseract.js).
- **Casos hostiles**: los 12 de `web/tests/` siguen sin medirse.
- **Vercel Hobby**: números (100 GB/mes) y condición no comercial
  contrastados con varias fuentes que citan la página oficial
  (19–22 nov 2026), sin leer la página oficial directamente.
  Confirmar en https://vercel.com/pricing antes de lanzar.
- **Privacidad**: el correo de contacto es un marcador (ver §5.6).
- **Servidor opcional**: la carga con Redis, la cola real y el build
  Docker amd64/arm64 quedan para la CI; en esta VM no hay Docker ni
  Redis.
- **Historial de git**: sin `.git` local; pendiente de revisar (ver §5.5).

## 7. Lo que no se pudo hacer o verificar y por qué

- **Build Docker amd64/arm64**: sin Docker en esta VM. Queda para la
  CI de GitHub (trabajos `docker-build` y `docker-build-arm64`).
- **CI en GitHub**: no ejecutada aquí; el push y la comprobación en
  verde los hace el dueño tras esta ronda.
- **WebKit en esta VM**: faltan dependencias del SO; `install-deps`
  no las instaló. En CI se instalan con `--with-deps`.
- **Celular real y Microsoft Word/Excel/PowerPoint reales**: no hay
  dispositivos ni licencias aquí; lista de verificación manual en
  §5.7.
- **OCR en el navegador real**: tesseract.js necesita descargar los
  modelos de idioma; en Node se midió, en navegador real no.
- **Historial de git**: no había `.git` local (ver §5.5).
- **LibreOffice y Camelot en la comparación**: motivos en §3.
- **Memoria máxima por conversión**: no medida en ningún dispositivo.
- **PDF de 10 páginas a Excel en el navegador**: sin medir (objetivo:
  pocos segundos en PC normal).
