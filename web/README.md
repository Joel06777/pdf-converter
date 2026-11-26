# Web del convertidor (archivos estáticos, sin servidor)

HTML + JavaScript puro, sin frameworks. Todo ocurre en el navegador:
el PDF no sale del dispositivo. El servidor opcional
(`docs/SERVIDOR_OPCIONAL.md`) solo se usa como respaldo si el dueño
lo activa.

> **Estado (26 nov 2026): la integración con el motor está hecha.**
> `web/engine/` se construye con `npm run build` (desde `web/engine/`)
> y genera `web/engine/index.js` (adaptador) y `web/engine/dist/worker.js`
> (motor completo en Web Worker), con MuPDF servido aparte en
> `web/engine/vendor/mupdf/`. La web convierte de verdad en el navegador:
> vista previa con pdf.js, extracción con el motor y escritura con
> `writers.js`. Verificado en Chromium con Playwright
> (`tests/browser/convert.spec.js`): factura → Excel con calidad
> texto 100 % y cifras 100 %, sin peticiones fuera del origen local.
> Sin el build (`web/engine/index.js` ausente) la página sigue en
> **modo de demostración**: la vista previa funciona y el botón
> «Convertir» explica que falta el motor.

## Qué hay en cada archivo

| Archivo | Para qué |
|---|---|
| `index.html` | Convertidor principal: subir, destino, rango de páginas, vista previa lado a lado, corrector de celdas dudosas, descarga, informe técnico |
| `excel.html`, `word.html`, `pptx.html` | Páginas de aterrizaje por herramienta, con texto útil, preguntas frecuentes y datos estructurados (JSON-LD) |
| `privacy.html` | Política de privacidad corta (la completa está en `docs/PRIVACIDAD.md`) |
| `styles.css` | Estilos, celular primero, con modo oscuro |
| `app.js` | Lógica de la página: archivos, progreso, vista previa, corrector, descarga, informe técnico |
| `engine.js` | Cargador del motor + contrato que debe cumplir `web/engine/index.js` |
| `writers.js` | Escritores .xlsx/.docx/.pptx y ZIP con librerías del navegador (carga diferida) |
| `config.js` | **El único archivo de configuración**: origen de librerías, servidor opcional, enlaces |
| `vercel.json` | Cabeceras de seguridad (CSP) y caché para Vercel |
| `sw.js`, `manifest.webmanifest`, `favicon.svg` | PWA: uso sin conexión tras la primera visita |
| `vendor/` | Librerías del navegador vendidas (con licencia y huella SRI) |
| `tests/` | PDFs hostiles generados por código + página de pruebas |

## Contrato del motor (`web/engine/index.js`)

### Estado de la integración (26 nov 2026): resuelta con la opción A

El motor se construye con `npm run build` (desde `web/engine/`, con
Vite 8, MIT, gratis) y produce:

- `web/engine/index.js` — adaptador (`src/browser-entry.js`) que
  expone `window.PdfConverterEngine` según el contrato de abajo.
- `web/engine/dist/worker.js` — el motor completo en un Web Worker
  (ExcelJS, docx, pptxgenjs, Tesseract, fflate empaquetados).
- `web/engine/vendor/mupdf/` — MuPDF.js 1.28.6 + su WASM, servidos
  aparte (no empaquetados: su salida de Emscripten se rompe al
  empaquetarla con Vite/Rolldown; el worker la carga con import
  dinámico en `init`).
- `web/engine/dist/tesseract-*` — núcleo y script de Tesseract.
- `web/engine/.tessdata/` — datos de idioma spa/eng (se descargan
  solos en el build desde tessdata_fast si faltan).

El adaptador extrae el modelo neutro en el worker
(`src/neutral.js`: tablas, textos, imágenes, celdas dudosas,
cobertura de colocación) y la web escribe los archivos con
`writers.js`. El motor también expone `convert()` directo (worker
→ `convertPdf`) para usos sin la web; las pruebas de privacidad
(`tests/browser/privacy.spec.js`) lo usan para convertir a los tres
destinos sin salir del origen local.

Dos detalles que costó encontrar (26 nov 2026):

- Empaquetar MuPDF dentro del worker dejaba el worker mudo: no
  respondía `ready`, no pedía el `.wasm` y no daba error; en Node el
  mismo bundle fallaba con `TypeError: e is not a function` porque
  Rolldown sustituyó el `import("module")` de la rama de Node de
  Emscripten por un módulo vacío. La solución fue no empaquetar
  MuPDF y hacer perezosa su carga también en `src/convert.js`
  (`import("mupdf")` dinámico solo si no se pasa en `opts.mupdf`).
- La barra de progreso es un `<progress>` nativo: el ancho en línea
  que usaba antes lo bloqueaba la CSP de `index.html`
  (`style-src 'self'`), así que la barra no se pintaba. Al ser un
  elemento nativo no necesita estilos en línea y la CSP sigue
  estricta. Lo mismo para la negrita de las celdas del corrector
  (`td.style.fontWeight` → clase `.bold` en `styles.css`).

### El contrato (lo que `web/engine/index.js` expone)

Al cargarse, el motor deja en `window.PdfConverterEngine` un objeto con:

- `ENGINE_VERSION`: texto, p. ej. `"1.0.0 (MuPDF.js 1.28.0)"`.
- `engineName`: texto legible, p. ej. `"MuPDF.js"`.
- `supportsOCR`: `true`/`false`.
- `load(onProgress)` — inicializa el motor. `onProgress(fracción 0..1, mensaje)`.
- `open(arrayBuffer, nombreArchivo)` → `{ pageCount, encrypted, title, pages: [{ width, height, hasText }] }`.
  Lanza `Error("encrypted")` si tiene contraseña y `Error("invalid")` si no es un PDF válido.
- `renderPage(doc, indicePagina, canvas, escala)` — dibuja la página en el canvas.
- `extract(doc, { from, to, onProgress })` → modelo neutro:
  `{ pages: [{ pageNumber, scanned, tables, texts, images }], doubtfulCells, quality, ocr_warning }`.
  Cada tabla es `{ rows: [[celda, …]] }` y cada celda
  `{ value, type: "number"|"text"|"date", bold, italic, fill, numFmt, colspan, rowspan, doubtful, confidence }`.
  `quality` es `{ text_coverage, number_coverage, missing_sample }`.
- `dispose(doc)` — opcional, libera el documento.

El modelo neutro es lo que `writers.js` convierte a .xlsx/.docx/.pptx:
el motor extrae, la web escribe. Así el motor no depende de las
librerías de escritura.

## Cambiar de dónde se sirven las librerías (sin tocar el código)

Solo hay que cambiar `vendorBase` en `config.js`:

- `"self"` (por defecto): las librerías se sirven desde `web/vendor/`
  junto a la página. Funciona sin conexión tras la primera visita y no
  depende de ningún tercero.
- `"jsdelivr"`: las mismas versiones, con la misma huella SRI, se cargan
  desde la CDN pública jsDelivr (`https://cdn.jsdelivr.net/npm/...`).
  jsDelivr es gratis para uso personal y comercial, sin límite de ancho
  de banda ni de peticiones, según sus Términos de Uso vigentes
  (5 oct 2026, verificados el 26 nov 2026); solo sirve archivos de
  código abierto y tiene límites de tamaño por archivo/paquete
  (paquete npm ≤ 150 MB, archivo de GitHub ≤ 20 MB). Nuestras librerías
  están muy por debajo. El motor (`web/engine/`) **siempre** se sirve
  desde el propio sitio, nunca por CDN de terceros.

Para verificar una huella SRI de un archivo vendido:

```bash
openssl dgst -sha384 -binary web/vendor/exceljs/exceljs-4.4.0.min.js | openssl base64 -A
```

## Probar en local

```bash
cd web/engine && npm ci && npm run build && cd ../..
python3 -m http.server 8080 --directory web
# abre http://localhost:8080
```

Sin el build (`web/engine/index.js` ausente), la página abre en modo
de demostración (vista previa sí, conversión no). Con el build, la
conversión completa ocurre en local, sin red.

## Caché y versiones

- Los archivos de `web/vendor/` llevan la versión en el nombre
  (`exceljs-4.4.0.min.js`): por eso `vercel.json` les da caché larga
  e inmutable. Al actualizar una librería, cambia el nombre del archivo
  y actualiza `writers.js` y `web/vendor/README.md`.
- `web/engine/` cambia con cada versión del motor: su caché es corta
  (1 hora) y el Service Worker usa `CACHE_NAME = "pdf-converter-v1"`,
  que hay que subir (`v2`, `v3`…) en cada versión nueva de la web.

## Seguridad

- CSP estricta: solo recursos del propio sitio (`'self'`); sin scripts
  externos sin verificar. Ver `vercel.json` y la meta CSP de cada HTML.
- **Si activas el servidor opcional**, añade su origen a `connect-src`
  en `web/vercel.json` y en la meta CSP de `web/index.html` (por
  ejemplo, `connect-src 'self' https://convertidor.tu-dominio.com`).
  Si no lo haces, el navegador bloquea la llamada y la página dice
  que el servidor no está disponible.
- Subresource Integrity (SRI, sha384) en toda librería cargada desde
  jsDelivr. Las vendidas en local no necesitan SRI (son archivos propios
  del repositorio) pero su huella está en `web/vendor/README.md`.
- Sin cuentas, sin rastreo, sin analíticas de terceros, sin cookies
  innecesarias. El único almacenamiento es la caché de la app y los
  ajustes de la página, en el propio dispositivo.
- Pruebas con PDFs defectuosos, cifrados y hostiles: `web/tests/`.
