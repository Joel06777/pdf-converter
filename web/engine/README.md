# Motor de conversión PDF → Excel / Word / PowerPoint en el navegador

Conversión **en el dispositivo del usuario** (WebAssembly + JavaScript, dentro
de un Web Worker). La página solo entrega archivos estáticos: el PDF **no
sale del dispositivo** y durante la conversión no hay ninguna petición de
red (verificado por `tests/network.test.js`).

Versión del motor: `0.1.0` (`ENGINE_VERSION` en `src/index.js`).
Licencia del paquete: AGPL-3.0-or-later (heredada de MuPDF).

## Arquitectura

```
PDF ──► extract.js (MuPDF.js) ──► modelo por página ──► excel.js  (.xlsx)
                                        │                ├─► pptx.js (.pptx)
                                        │                └─► word.js (.docx)
                                        ▼
                                   layout.js (cuadrícula)
                                   verify.js (cobertura)
                                   ocr.js (tesseract.js, solo si no hay texto)
```

**Modelo intermedio único por página** (`src/extract.js` → `build_layout` en
`src/layout.js`): un solo modelo alimenta los tres destinos.

- **Texto con estilo y posición por carácter**: MuPDF.js entrega cada
  carácter con su quad, fuente, tamaño, negrita/cursiva y color. La posición
  por carácter es lo que permite separar el símbolo `$` de la cifra que
  sigue (puerto fiel del `parse_number` de Python en `src/numbers.js`).
- **Rellenos y líneas**: el `Device` propio de MuPDF recoge rellenos
  rectangulares (color), líneas horizontales/verticales y trazos complejos
  (curvas o más de 40 segmentos → región gráfica rasterizada a 200 dpi,
  paridad con el backend Python).
- **Imágenes**: se extraen con composición de máscara (`smask`) y se
  incrustan en los tres destinos; las regiones gráficas se rasterizan.
- **Tablas**: la cuadrícula visual se reconstruye como en
  `app/converters/pdf_to_excel.py` (columnas por alineación de texto y
  líneas, filas, celdas combinadas horizontales y verticales, fusión de
  moneda con número, verificación de totales que **solo avisa y jamás
  cambia un valor**).

**Orquestador** (`src/convert.js`): abre el PDF, extrae página por página
(progreso real por página, cancelación con `isCancelled()`), OCR perezoso
(solo páginas sin texto nativo) y verificación de cobertura y aritmética.
El informe de calidad por conversión (`quality`) trae cobertura de texto y
de cifras, advertencias y qué quedó fuera; para escaneos puros
`verifiable: false` (no hay texto nativo contra el que verificar).

**Web Worker** (`src/worker.js`): mensajes `init` (`mupdfUrl`,
`tessdataUrl`, `coreUrl`, `workerUrl`), `info` (metadatos y páginas sin
convertir), `extract` (modelo neutro para la web, ver `src/neutral.js`),
`convert` (progreso por página, buffer transferible), `cancel`. El
protocolo se verificó en Node con un harness
(`scripts/check-worker.mjs`): `init → convert → done`, cobertura 1,0
en la factura de prueba. En el navegador, el worker no hace peticiones
de red durante la conversión.

**MuPDF no se empaqueta** (26 nov 2026): su salida de Emscripten se
rompe al empaquetarla con Vite/Rolldown — el worker empaquetado con
MuPDF dentro no responde `ready`, no pide el `.wasm` y no da error; en
Node el mismo bundle falla con `TypeError: e is not a function`
(Rolldown sustituye el `import("module")` de la rama de Node por un
módulo vacío). MuPDF se sirve aparte en `web/engine/vendor/mupdf/` y
el worker la carga con import dinámico en `init`. Por eso
`src/convert.js` tampoco importa MuPDF estático: la carga es perezosa
(`import("mupdf")` dinámico solo si no se pasa en `opts.mupdf`).

**Adaptador del navegador** (`src/browser-entry.js` → `web/engine/index.js`
tras `npm run build`): expone `window.PdfConverterEngine` con el contrato
de `web/engine.js` (`load`, `open`, `renderPage`, `extract`, `dispose`,
más `convert` directo). El build (`scripts/build-browser.mjs`, Vite 8,
MIT) genera `index.js`, `dist/worker.js` (motor completo sin MuPDF),
`dist/tesseract-*` y `vendor/mupdf/`; los datos de idioma se descargan
solos a `.tessdata/` si faltan. Todo lo generado por el build está en
`.gitignore`: se regenera en cada despliegue y en la CI.

## Dependencias (licencias y versiones verificadas)

| Paquete | Versión | Licencia | Uso |
|---|---|---|---|
| `mupdf` | 1.28.6 | AGPL-3.0-or-later | Extracción de texto/vectores/imágenes (WebAssembly) |
| `exceljs` | 4.4.0 | MIT | Generación de .xlsx |
| `docx` | 9.16.0 | MIT | Generación de .docx |
| `pptxgenjs` | 4.0.1 | MIT | Generación de .pptx |
| `tesseract.js` | 7.0.0 | Apache-2.0 | OCR en el navegador |
| `fflate` | 0.8.3 | MIT | PNG mínimo y lectura de .docx/.pptx en los tests |
| `vitest` | 5.1.2 | MIT | Tests (dev) |
| `vite` | 8.4.0 | MIT | Empaquetado para navegador (dev, `npm run build`) |

Datos de OCR (no son paquetes npm): `tessdata_fast` de GitHub,
`spa.traineddata.gz` (1.137.561 B) y `eng.traineddata.gz` (1.984.273 B).
Se descargan en `.tessdata/` (caché local, en `.gitignore`) y **solo se
cargan cuando el PDF no tiene texto**.

## Verificación de MuPDF.js (medida, no heredada)

Re-verificado en Node contra `tests/fixtures/estado_ingresos_octubre_2026.pdf`:

- **Posición por carácter**: sí. `page.toStructuredText("preserve-whitespace")`
  + walker `onChar(c, origin, font, size, quad, color)` entrega un quad por
  carácter con precisión sub-punto (`$` en x=423.125 con su propio quad).
  5.447 caracteres, 178 líneas en ese fixture.
- **Líneas con precisión suficiente**: sí. `page.run()` con `Device` propio
  recoge `fillPath`/`strokePath`; los trazos de líneas de tabla se
  reconstruyen con precisión de punto.
- **Rellenos**: 6 rellenos, incluido el verde 8ED973 (142,217,115) del
  encabezado, que se conserva en el .xlsx.
- **Imágenes**: 5 imágenes extraídas con máscara.
- **Cifras clave** presentes: 30,570.51; 27,948.96; 2,621.55.
- **Rotación**: con `/Rotate 90` los bounds se intercambian a
  [0,0,842,595], transform `[0,1,1,0,0,0]` y los quads vienen en espacio
  rotado; el motor endereza la imagen OCR y devuelve las cajas a su sitio.

### pdf.js como respaldo (evaluado, no adoptado)

`pdf.js` 6.5.438 (Apache-2.0) se evaluó como respaldo: `getTextContent()`
separa `$` con posición, pero **sin** posición por carácter, **sin**
negrita/color y **sin** extracción directa de vectores ni imágenes (solo
lista de operadores). Es un respaldo válido solo para texto; el motor
principal es MuPDF.js.

## Cobertura medida — texto nativo

Matriz completa: **10 fixtures × 3 destinos = 1,0 texto / 1,0 cifras**
(`tests/fixtures.test.js`, 42 pruebas; misma métrica que
`app/converters/verify.py`).

| Fixture | Excel | PowerPoint | Word |
|---|---|---|---|
| `estado_ingresos_octubre_2026.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `factura.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `estado_cuenta_multipagina.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `tabla_sin_lineas.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `celdas_combinadas.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `dos_columnas.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `acentos.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `factura_real_logo_sello.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `tabla_combinada_compleja.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |
| `dos_columnas_tablas.pdf` | 1,0 / 1,0 | 1,0 / 1,0 | 1,0 / 1,0 |

Casos concretos verificados (paridad con `tests/test_fixtures.py` de Python):

- **Excel**: factura con fórmula `=SUM` en el TOTAL, valores 335/50/160 y
  RUC como texto; estado de cuenta en 3 hojas (`pages`) y 1 hoja continua;
  tabla sin líneas con 1950.50/1680.00; fusión vertical en celdas
  combinadas; estado de ingresos con 30570.51/27948.96/2621.55 y relleno
  verde 8ED973.
- **PowerPoint**: factura con tabla nativa (`<a:tbl>`, cifra 335) y
  `gridSpan`/`vMerge` en celdas combinadas; una diapositiva por página.
- **Word**: estado de cuenta con 3 secciones y encabezado repetido;
  fusión vertical real (`vMerge`); dos columnas con orden de lectura
  izquierda → derecha.

### Word de texto corrido: estado

No hay equivalente directo de pdf2docx en JavaScript. Se implementó
reconstrucción propia de párrafos, columnas, listas y tablas (`src/word.js`,
ruta `flow`), además de la ruta de cuadrícula fija (`grid`) y la ruta OCR.
En `auto` con texto corrido se construyen `flow` y `grid` y se queda la de
mayor cobertura de texto; **si el texto empata, deciden las cifras
aisladas** (`isolatedNumberScore` en `src/word.js`): en `flow` las cifras
van enterradas en líneas («Alquiler mensual   $   800.00») y una
comprobación por celdas no las encuentra, aunque el texto esté completo.
Sin esa regla, 6 documentos de tabla sin líneas elegían `flow` y la
cobertura de celdas en Word era 0,829; con ella es **1,0 (858/858)** en
paridad, igual que Python. **Cobertura 1,0 medida en los 10 fixtures**,
pero **sin verificación de solapes en Word real** (no se abrió el .docx
en Word/LibreOffice para comprobar que nada se solapa): ese caso queda
documentado aquí y el servidor opcional existente sigue siendo el
respaldo para documentos de texto corrido complejos. La imagen de
página completa de un escaneo se incrusta una sola vez (en línea); la
cola de la tabla ya no la añade también flotante, que la duplicaba.

## OCR medido (tesseract.js, spa+eng)

`tests/ocr.test.js` (7 pruebas), contra el PDF original del que se generó
cada escaneo. Preprocesado: enderezado fino (±5°, paso 0,5°),
autocontraste con guarda por densidad de tinta, binarización (umbral 150),
eliminación de líneas de tabla largas, corrección de `Nº` (`N?`/`N*`/`N®`
→ `Nº`), mapa de confianza por celda (celdas de baja confianza en
amarillo `FFF2CC` en Excel).

| Caso | Texto | Cifras | Tiempo |
|---|---|---|---|
| `escaneado.pdf` (plano, 200 dpi) | 1,0 | 1,0 | ~5–13 s |
| `foto_inclinada.pdf` (3°) | 1,0 | 1,0 | ~7–27 s |
| `escaneado_color_sello.pdf` (sello + marca "COPIA") | 1,0 | 1,0 | ~5–17 s |
| `foto_celular_perspectiva.pdf` (perspectiva + 2°) | 0,9677 | 1,0 | ~7–27 s |
| Escaneo girado `/Rotate 90` (foto de lado) | 0,9839 | 1,0 | ~3 s |
| Escaneo girado `/Rotate 270` | 1,0 | 1,0 | ~6 s |

Notas:

- En perspectiva faltan solo dos tokens: `nº` y `ferretería`. En `/Rotate 90`
  falta solo un token `$` (de 7). Las cifras son 1,0 en todos los casos.
- El escaneo en color se generó de la factura normal (0001234, TOTAL
  335.00) con sello rojo y marca de agua "COPIA"; su verdad es
  `factura.pdf`, **no** `factura_real_logo_sello.pdf` (otra factura distinta,
  0001235, con subtotal e IVA, total 385.25). El test usa la verdad correcta.
- Referencia del backend Python (`docs/METRICAS.md`): OCR con Tesseract CLI
  5.3.4 daba texto 95,8–97,9 % y cifras 100 % en estos casos. El motor del
  navegador iguala o supera esas cifras de texto.
- Los tiempos varían mucho entre corridas (arranque del worker de
  Tesseract en Node); son orientativos, no un compromiso de rendimiento.

## Tamaños descargados y capacidad en Vercel Hobby

Medido con `npm run sizes` (`scripts/measure-sizes.mjs`, 26 nov 2026;
`Brotli` = lo que sirve Vercel con `.br` o compresión; `sizes.json` con
el detalle por archivo). Primera visita sin caché:

| Escenario | Por visita | Visitas/mes en 100 GB |
|---|---|---|
| Solo motor (PDF nativo) | 3,49 MB | **29.326** |
| + librerías de generación (exceljs, docx, pptxgenjs) | 4,00 MB | **25.614** |
| + OCR completo (núcleo + JS + datos spa+eng) | 9,23 MB | **11.097** |

Desglose (Brotli): `mupdf-wasm.wasm` 3,45 MB (crudo 9,93 MB),
`mupdf.js` 18,4 KB, núcleo Tesseract wasm 985,8 KB + JS 1,29 MB,
`exceljs` 196,4 KB, `docx` 175,8 KB, `pptxgenjs` 134,9 KB, motor propio
28,4 KB, datos `spa` 1,07 MB + `eng` 1,87 MB (ya `.gz`).

El test `tests/sizes.test.js` comprueba además un escenario intermedio
(motor + núcleo OCR, sin librerías ni datos de idioma): 4,43 MB →
23.132 visitas/mes, y exige más de 10.000 visitas/mes en el peor caso.

Con caché del navegador (los estáticos no cambian entre visitas), las
visitas siguientes no vuelven a descargar el motor.

## Límites anti-abuso (`src/limits.js`)

En el worker, antes de convertir: PDF 50 MB, 200 páginas, 200.000 objetos,
200.000 caracteres por página, 50.000 dibujos por página, 200 imágenes por
página, 100 Mpx por imagen decodificada, 120 s por página, 600 s en total.
PDF cifrado, corrupto o que supere un límite falla con elegancia y mensaje
claro en español (`ConversionError`: `pdf_invalido`, `pdf_cifrado`,
`pdf_corrupto`, `limite_excedido`, `cancelado`, `sin_texto`,
`ocr_no_disponible`, `conversion_fallida`).

## Uso

```js
import { convertPdf } from "pdf-converter-engine";

const { buffer, filename, mime, quality, warnings } = await convertPdf(pdfBytes, "excel", {
  // onProgress(page, total, "extract" | "generate"),
  // isCancelled: () => cancelado,
});
```

En el navegador, usar `src/worker.js` como Web Worker (ver su protocolo
arriba) y pasarle las URLs de los estáticos (`mupdfUrl`, `tessdataUrl`,
`coreUrl`, `workerUrl`).

## Tests

```bash
npm test            # vitest run (suite completa)
npm run build       # empaqueta para el navegador: index.js + dist/
npm run sizes       # mide tamaños reales y escribe sizes.json
node scripts/smoke.mjs factura.pdf excel
node scripts/matrix.mjs   # matriz nativa 10 fixtures × 3 destinos
node scripts/check-worker.mjs  # verifica el protocolo del worker en Node
```

Suite: 10 archivos de test, 80 pruebas en verde (26 nov 2026), en 56 s.
Los tests de OCR descargan los datos `tessdata_fast` en `.tessdata/` si faltan.
Novedades de esta ronda: `tests/word-images.test.js` (el .docx incrusta
el logo y la imagen de página completa de un escaneo) y
`tests/neutral.test.js` (el modelo neutro para la web: TOTAL 335 como
número, relleno 8ED973, celdas combinadas, cobertura de colocación 1,0,
sin duplicar el texto entre tablas y textos sueltos); y
`tests/word-mode.test.js` (decisión auto grid/flow por cifras aisladas:
6 documentos de tabla sin líneas eligen `grid` y la cifra queda aislada;
el texto corrido sin cifras en tabla sigue en `flow`) y la prueba de no
duplicación de la imagen de escaneo en `tests/word-images.test.js`.

## Qué quedó sin verificar

- **OCR en el navegador real**: tesseract.js con datos spa+eng funciona
  en Node (medido: escaneado plano 1,0/1,0; foto inclinada 3° 1,0/1,0;
  color con sello 1,0/1,0; perspectiva +2° 0,9677/1,0; `/Rotate 90`
  0,9839/1,0), pero no se ha probado en un navegador real todavía.
  La carga de los datos de idioma y del núcleo en el navegador es la
  parte sin verificar.
- **Word/Excel/PowerPoint reales**: los .docx/.xlsx/.pptx se verificaron
  leyendo su XML/contenido en Node y convirtiéndolos a PDF con
  LibreOffice, no abriéndolos en Word, Excel o PowerPoint. En particular,
  no se verificaron solapes en Word de texto corrido ni el ancla
  fraccional de imágenes en ExcelJS en Excel real.
- **WebKit**: no se ejecuta en la VM de trabajo (faltan dependencias del
  SO); en CI se instala con `--with-deps`.
- **Celulares reales**: lo medido es emulación Pixel 7 (Chromium) con CPU
  limitada 4x; un celular real rinde distinto.

## Verificado en navegador real (26 nov 2026, Playwright)

Ver `tests/browser/` para los detalles. Chromium y Firefox en la VM;
WebKit solo en CI.

- Conversión real en la web (`web/index.html`): factura → Excel en
  Chromium en 5,6 s, calidad texto 100 % / cifras 100 %, TOTAL 335 en
  el .xlsx; factura → Word en Pixel 7 en 5,0 s.
- Privacidad: conversión a los 3 destinos sin peticiones fuera del
  origen local (6 peticiones estáticas en Chromium: la página,
  `dist/worker.js`, `mupdf.js`, `mupdf-wasm.js`, `mupdf-wasm.wasm` y
  la factura). Chromium 2,4 s, móvil con CPU 4x 4,7 s, Firefox 3,5 s.
- Tamaños de descarga (Brotli, medidos el 26 nov 2026): núcleo sin OCR
  3,85 MB → 26.626 visitas nuevas/mes en 100 GB/mes; con OCR completo
  8,70 MB → 11.782 visitas nuevas/mes; web (app + writers + vendor)
  0,90 MB. Detalle en `docs/METRICAS.md`.
