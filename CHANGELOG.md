# Changelog

Todos los cambios notables de este proyecto, en orden cronológico inverso.
Formato inspirado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Sin publicar]

### Correcciones de Word y de la web (26 nov 2026)

> Estado: la cobertura de celdas en Word del navegador subió de 0,829
> a 1,0 y la imagen de un escaneo ya no se duplica en Word. La
> etiqueta v1.0.0 se prepara cuando la CI esté en verde tras el push;
> no se crea en GitHub desde aquí.

#### Corregido
- **Word: decisión grid/flow por cifras aisladas**
  (`web/engine/src/word.js`, `src/verify.js`): en modo auto, cuando
  la cobertura de texto empata, ahora deciden las cifras aisladas
  (`isolatedNumberScore` + `docxTexts` nuevo en `verify.js`): en
  `flow` las cifras van enterradas en líneas («Alquiler mensual
  $ 800.00») y una comprobación por celdas no las encuentra. La
  cobertura de celdas en Word del navegador pasó de **0,829 a 1,0
  (858/858)** en paridad, igual que Python. 7 pruebas nuevas en
  `tests/word-mode.test.js`.
- **Word: imagen de escaneo duplicada** (`web/engine/src/word.js`):
  sin OCR la imagen de página completa iba en línea
  (`scanImageParagraphs`) y además flotante en la cola de la tabla,
  así que la página aparecía dos veces. La cola ya salta siempre
  las imágenes de página completa de un escaneo. 1 prueba nueva en
  `tests/word-images.test.js`.
- **Métrica de imágenes en paridad** (`scripts/parity.py`): el
  conteo de Word sumaba `inline_shapes` + partes de imagen, así que
  una imagen en línea contaba dos veces aunque solo se dibujara una
  vez. Ahora cuenta dibujos (`<a:blip>` en `word/document.xml`).
- **Barra de progreso bloqueada por la CSP** (`web/index.html`,
  `web/app.js`, `web/styles.css`): la barra era un `<div>` con ancho
  en línea, que `style-src 'self'` bloquea. Ahora es un
  `<progress>` nativo (sin estilos en línea) y la negrita del
  corrector de celdas usa la clase `.bold`. La CSP sigue estricta.
- **Guía de despliegue** (`docs/DESPLIEGUE_GRATIS.md`): el paso de
  build del motor era incorrecto — decía dejar el Build Command
  vacío, pero los archivos generados (`index.js`, `dist/`,
  `vendor/mupdf/`) no están en el repositorio. En Vercel el Build
  Command es `cd engine && npm ci && npm run build` y la versión de
  Node es 20.x; en GitHub Pages hay que construir con GitHub
  Actions (publicar desde la rama no sirve: quedan en modo
  demostración). Tamaños de primera visita actualizados (4,75 MB
  Brotli sin OCR; 9,60 MB con OCR).

#### Medido en esta ronda (26 nov 2026)
- Motor (vitest): **80 passed** (10 archivos, 56 s).
- Paridad (33 nativos, 252 filas, 0 errores): navegador texto
  0,9982 / cifras 1,0 en los 3 destinos; celdas Excel 0,9463
  (825/858, idéntico a Python), Word 1,0 (858/858), PPTX 1,0
  (858/858). Tiempos medios del navegador en la corrida final
  (con pytest en paralelo): Excel 1,69 s, PPTX 1,76 s, Word 1,85 s
  por conversión; sin carga paralela: 1,08 / 1,00 / 1,14 s.

### Integración motor ↔ web y verificación en navegador real (26 nov 2026)

> Estado: la web convierte de verdad en el navegador (Chromium,
> Firefox, Pixel 7 emulado). La etiqueta v1.0.0 se prepara cuando la
> CI esté en verde tras el push; no se crea en GitHub desde aquí.

#### Añadido
- **Adaptador del navegador** (`web/engine/src/browser-entry.js`):
  expone `window.PdfConverterEngine` con el contrato de
  `web/engine.js` (`load`, `open`, `renderPage`, `extract`,
  `dispose`, más `convert` directo). El motor se construye con
  `npm run build` (Vite 8.4.0, MIT) y produce `web/engine/index.js`,
  `web/engine/dist/worker.js`, `dist/tesseract-*` y
  `web/engine/vendor/mupdf/` (MuPDF servido aparte, sin empaquetar).
- **Modelo neutro** (`web/engine/src/neutral.js`): convierte el
  modelo del motor y su cuadrícula al formato que esperan `web/app.js`
  y `web/writers.js` (tablas, textos sueltos, imágenes, celdas dudosas,
  cobertura de colocación). Mensajes nuevos en el worker: `info` y
  `extract`.
- **Pruebas de la web real** (`tests/browser/convert.spec.js`):
  factura → Excel en Chromium y factura → Word en Pixel 7, con
  comprobación de cero peticiones fuera del origen local.
- **Prueba de privacidad con el worker real**
  (`tests/browser/privacy.spec.js`): conversión a los 3 destinos sin
  stubs; 6 peticiones estáticas locales en Chromium, 0 externas.
- **Paso de build en la CI** (trabajo `browser`): `npm run build` en
  `web/engine/` antes de Playwright.

#### Corregido
- **Word en el navegador**: `Packer.toBuffer` de docx lanzaba
  «nodebuffer is not supported by this platform»; ahora se usa
  `Packer.toArrayBuffer` (`web/engine/src/word.js`, `packDoc`).
- **Imágenes de escaneo en Word**: el motor no las incrustaba (0/1
  y 0/2 en paridad); ahora van en línea con `scanImageParagraphs`
  (2 pruebas nuevas en `tests/word-images.test.js`).
- **MuPDF empaquetado se rompía con Vite/Rolldown**: el worker
  quedaba mudo (sin `ready`, sin pedir el `.wasm`, sin error) y en
  Node fallaba con `TypeError: e is not a function`. MuPDF se sirve
  aparte y `src/convert.js` la carga perezosa. El worker pasó de
  16 MB a 2,1 MB.
- **La web fallaba al convertir** (`Cannot set properties of null
  (setting 'innerHTML')` en `showResults`): `hide()` borraba con
  `textContent = ""` los hijos del contenedor, incluido el
  `<div id="downloadList">`. `hide()` ya solo oculta; `showResults`
  tiene guarda contra `null`.
- **CSP de la barra de progreso**: corregido en esta ronda — la
  barra es ahora un `<progress>` nativo y la negrita del corrector
  usa una clase CSS; la CSP sigue estricta (`style-src 'self'`).

#### Medido en esta ronda (26 nov 2026)
- `pytest -q`: **119 passed, 0 failed, 2 warnings** (171 s).
- Motor (vitest): **72 passed** (8 archivos, 56 s).
- Playwright: convert Chromium 5,6 s, móvil Pixel 7 Word 5,0 s,
  privacidad Chromium 2,4 s, móvil CPU 4x 4,7 s, Firefox 3,5 s.
- Tamaños (Brotli): núcleo sin OCR 3,85 MB → 26.626 visitas
  nuevas/mes en 100 GB/mes; con OCR 8,70 MB → 11.782; web 0,90 MB.

### Web del navegador (26 nov 2026) — fases 3, 4, 5, 6, 7 y documentación

> Estado: la web está terminada contra el contrato del motor, pero
> `web/engine/` aún no tiene punto de entrada para el navegador
> (existe y está en construcción: MuPDF.js 1.28.6, tesseract.js 7.0.0).
> La web funciona en modo de demostración: vista previa sí, conversión
> todavía no. Nada de esta sección inventa una medición.

#### Añadido
- **Web estática completa en `web/`** (HTML + JavaScript puro, sin
  frameworks): `index.html` (convertidor), `excel.html`, `word.html`
  y `pptx.html` (páginas por herramienta con texto útil, preguntas
  frecuentes y JSON-LD), `privacy.html`, `styles.css` (celular
  primero, modo oscuro), `app.js`, `engine.js` (cargador + contrato
  del motor), `writers.js`, `config.js` (único archivo de
  configuración), `vercel.json` (CSP + caché), `sw.js` + `manifest.webmanifest`
  (PWA, uso sin conexión tras la primera visita).
- **Arrastrar y soltar, varios archivos y ZIP** (fflate 0.8.2 MIT,
  vendido en `web/vendor/`), selección de rango de páginas, diseño
  de Excel (una hoja por página, continua, por tabla) y unión de
  varios PDF en un solo libro.
- **Vista previa lado a lado** (PDF original con pdf.js 5.5.207 +
  resultado como tabla), **informe de calidad** y **corrector de
  celdas dudosas del OCR** antes de descargar (las correcciones salen
  en el archivo).
- **Estados claros en español**: cargando el motor (con barra),
  procesando por página, listo, error con qué hacer. Accesible con
  teclado y lector de pantalla (`aria-live`, roles, foco visible).
- **Detección de capacidad del dispositivo** (memoria y núcleos) con
  límites ajustados y mensaje claro («Este PDF es grande para tu
  dispositivo; prueba con un rango de páginas»).
- **Carga diferida**: motor al primer uso, pdf.js solo para la vista
  previa, cada librería de escritura solo para su destino, ZIP solo
  al pedirlo, datos de idioma del OCR solo si hace falta.
- **Botón «copiar informe técnico»** sin contenido del documento
  (versión, navegador, dispositivo aproximado, errores, tiempos) y
  enlace al formulario de incidencias de GitHub prellenado.
- **Enlace visible «Código fuente»** en el pie de cada página
  (https://github.com/Joel06777/pdf-converter) y enlace a la
  política de privacidad, que explica que el archivo no sale del
  dispositivo.
- **Librerías del navegador vendidas** en `web/vendor/` con licencia
  y huella SRI (fflate 0.8.2, exceljs 4.4.0, docx 9.16.0, pptxgenjs
  4.0.1, pdfjs-dist 5.5.207). Tamaños medidos: 4,0 MB sin comprimir,
  1,1 MB con gzip.
- **Pruebas con PDFs hostiles** en `web/tests/`: 12 casos generados
  por código (`generate-hostile-pdfs.mjs`, sin dependencias), incluido
  un PDF cifrado real AES-256; página de pruebas `web/tests/index.html`
  y tabla de resultados en `web/tests/hostile-cases.md` (sin medir).
- **Docs nuevas**: `docs/SERVIDOR_OPCIONAL.md` (el servidor como
  respaldo opcional) y `docs/ROADMAP.md` (backlog priorizado).
- **Docs actualizadas**: `docs/DESPLIEGUE_GRATIS.md` (reescrita:
  web estática en Vercel + alternativa GitHub Pages, sin servidor,
  sin claves), `docs/PRIVACIDAD.md` (modo navegador: el archivo no
  sale del dispositivo), `docs/LIMITES.md` (límites del motor del
  navegador y casos hostiles), `docs/LICENCIAS.md` (dependencias del
  navegador: mupdf AGPL-3.0-or-later, pdf.js Apache-2.0, exceljs /
  docx / pptxgenjs / fflate MIT, tesseract.js Apache-2.0, Playwright
  Apache-2.0), `docs/METRICAS.md` (metodología del navegador y tablas
  vacías con «sin medir»).

#### Verificado en esta ronda (26 nov 2026)
- Licencias de las 6 librerías del navegador leídas del `package.json`
  y del `LICENSE` de cada paquete descargado de npm; Playwright 1.65.1
  Apache-2.0 verificado en el registro de npm.
- Términos de jsDelivr verificados en su repositorio oficial
  (vigentes desde el 5 oct 2026): gratis, sin límite de ancho de
  banda; paquete npm ≤ 150 MB.
- Escritores verificados con un modelo de prueba en Node: Excel (3
  diseños), Word, PPTX y ZIP producen archivos válidos; el `.xlsx`
  se reabre con ExcelJS (cifra como número, celda dudosa en
  amarillo) y los tres archivos se abren en LibreOffice y se
  convierten a PDF.
- Sintaxis de todo el JavaScript de `web/` comprobada con
  `node --check`; HTML comprobado con un analizador.
- Los 12 fixtures hostiles generados y comprobados con PyMuPDF
  (el válido abre; el cifrado es AES-256 real; el truncado, el vacío
  y el que no es PDF dan error).

#### Sin verificar (queda pendiente)
- `web/engine/` existe pero no tiene punto de entrada para el
  navegador (`web/engine/index.js`, `src/index.js` y `src/worker.js`
  no existen aún) ni expone `window.PdfConverterEngine`; además su
  arquitectura (modelo de spans + escritores propios) difiere del
  contrato de `web/README.md`. Falta la integración (adaptador del
  motor o adaptación de `app.js`). Sin motor no se pudo medir ningún
  tiempo ni ninguna fidelidad en el navegador, ni correr los casos
  hostiles en la página. Las tablas de `docs/METRICAS.md` y de
  `web/tests/hostile-cases.md` están vacías con «sin medir».
- La web no se probó en un navegador real (no había navegador en la
  máquina de trabajo; Playwright no instalado).
- Vercel Hobby: números y condición no comercial contrastados con
  varias fuentes que citan la página oficial, pero sin leer la
  página oficial directamente. GitHub Pages: límites numéricos sin
  verificar. MuPDF.js y tesseract.js: versiones previstas (1.28.x y
  7.0.0), a confirmar cuando llegue el motor.

Cambios de esta ronda (26 nov 2026), solo lo constatado en los archivos:

### Añadido
- **Subida directa al backend con token firmado** (`UPLOAD_SECRET`):
  `POST /api/v1/upload-token` entrega un token HMAC-SHA256 de un solo uso
  que caduca en 5 minutos, y `POST /api/v1/upload` acepta el PDF directo
  con el header `X-Upload-Token`, sin pasar por Vercel (sin límite de
  4,5 MB). La API key nunca llega al navegador. Función serverless nueva
  `web-example/api/upload-token.js` y flujo nuevo en `web-example/app.js`.
  Probado con un PDF sintético de 40 MB de principio a fin; token
  caducado, reutilizado o manipulado se rechaza con 401
  (`tests/test_upload_token.py`, 9 pruebas).
- **Tope de cola**: si hay más de `MAX_QUEUE_JOBS` (50) trabajos en cola,
  la API responde 503 «Estamos con mucha demanda, intenta en unos
  minutos» sin consumir el token de subida (`tests/test_capacidad.py`,
  5 pruebas). Límite de páginas OCR por trabajo: `MAX_OCR_PAGES=20`.
- **CI ARM**: trabajo `docker-build-arm64` (buildx + QEMU) que construye
  y prueba la imagen en `linux/arm64` y ejecuta pytest dentro del
  contenedor; humo de conversión añadido también al build amd64.
- **5 fixtures nuevos más difíciles** (factura real con logo y sello,
  tabla con fusiones verticales y horizontales, dos columnas con tablas,
  escaneado en color con sello y marca de agua, foto de celular con
  perspectiva) con 20 pruebas nuevas y métricas en `docs/METRICAS.md`.
- **OCR mejorado**: fusión `$` + cifra en la misma celda, guarda de
  binarización por densidad de tinta y validación subtotal + IVA = total
  solo para marcar celdas dudosas (nunca cambia valores). Texto OCR:
  factura escaneada 87,1 % → 98,4 % (tokens), foto inclinada 85,5 % →
  96,8 %; cifras 100 % en todos los casos.
- `scripts/loadtest/RESULTADOS.md`: prueba de carga real medida en esta
  VM (200 usuarios, 2 min): 0 fallos, ~43 conversiones/min en modo
  inline, POST p50 35 s / p95 99 s por la saturación del modo inline.
- `docs/INFORME_FINAL.md`: informe final de esta ronda.
- `LICENSE`: texto completo de la GNU AGPL-3.0 (descargado de
  <https://www.gnu.org/licenses/agpl-3.0.txt>).
- `NOTICE`: avisos de copyright y licencias de terceros, en español.
- `docs/DESPLIEGUE_GRATIS.md`: guía paso a paso de despliegue gratuito
  (Oracle Cloud Always Free + DuckDNS + Caddy + Vercel).
- `scripts/bootstrap.sh`: script de reconstrucción del servidor en un solo
  comando (validado con `bash -n`).
- `docs/PRIVACIDAD.md`: política de privacidad basada en el comportamiento
  real del código (borrado del original al terminar, resultados a los
  60 minutos, logs sin contenido de documentos).

### Corregido
- **QR solapado con texto en Word** (área de firmas del documento de
  referencia): anchos reales de columna en la cuadrícula de la tabla,
  fusiones vecinas ya no invadidas y las imágenes ancladas a su propio
  párrafo vacío. Verificado renderizando con LibreOffice: 0 solapes
  >1 pt; cobertura de texto y cifras sigue en 1,0
  (`tests/test_word_qr.py`, 2 pruebas).
- `docs/LICENCIAS.md`: auditoría completa de dependencias. Corrección
  importante: **pdf2docx 0.5.13 es MIT, no GPL-3.0** (Artifex lo
  relicenció; verificado en PyPI y en el repositorio oficial). La tabla
  incluye ahora todas las dependencias Python y del sistema, con fuentes
  oficiales.
- `README.md`: sección de licencia ampliada (AGPL-3.0, repositorio público
  obligatorio antes de lanzar y enlace «Código fuente» en la web);
  endpoints de subida directa, 69 pruebas y despliegue gratis.
- `docker-compose.yml`: memoria por worker 2g → 1g (medido), límites de
  memoria en api, redis y beat.

### Medido en esta ronda (26 nov 2026)
- `pytest -q`: **69 passed, 0 failed** (110 s). Base de la ronda: 33.
- Texto nativo: cobertura 1,0/1,0 en los 12 fixtures y los 3 destinos.

## [v1.0.0] — sin publicar aún

Primera versión funcional del servicio. No hay tag publicado en el
repositorio; la versión de la API es `1.1.0` según `app/main.py`.

### Añadido
- Conversión de PDF a **Excel** (`.xlsx`): reconstrucción de la cuadrícula
  visual con valores numéricos reales, formato, fórmulas de totales (solo
  si cuadran) y `layout=pages|continuous`.
- Conversión de PDF a **Word** (`.docx`): tabla fiel para reportes, ruta de
  texto corrido con pdf2docx y ruta OCR para escaneados.
- Conversión de PDF a **PowerPoint** (`.pptx`): una diapositiva editable
  por página, con tablas nativas en páginas tabulares.
- **OCR propio** para PDFs escaneados (Tesseract `spa+eng` + OCRmyPDF):
  binarización, enderezado, detección de rotación y aviso `ocr_warning`
  en español cuando la confianza es baja (celdas dudosas resaltadas en
  amarillo en Excel).
- **Informe de calidad** en cada conversión: `quality.text_coverage` y
  `quality.number_coverage` (1.0 = todo el texto y todas las cifras del
  PDF llegaron al archivo).
- API REST con FastAPI: subida de uno o varios archivos (máx. 20),
  consulta de estado y progreso por página, cancelación, descarga con
  enlace firmado de 15 minutos (`DOWNLOAD_SECRET`), `/health` y `/metrics`
  (Prometheus).
- Cola de trabajos con Celery + Redis (modo inline sin Redis para
  desarrollo) y limpieza automática de trabajos de más de 60 minutos
  (cada 5 minutos).
- **Privacidad por diseño**: el PDF original se borra al terminar
  (también si hay error o cancelación), los resultados se borran a los
  60 minutos, y los logs JSON no contienen contenido de los documentos.
- **Límites y errores claros en español**: 50 MB y 200 páginas por
  archivo, 60 conversiones por hora y por IP, rechazo de PDFs con
  contraseña y de formularios dinámicos XFA.
- Frontend de ejemplo (`web-example/`) con funciones serverless de Vercel
  que reenvían al backend.
- **33 pruebas** (`pytest -q`: 33 passed, 0 failed) y medición de
  fidelidad en 7 fixtures: cobertura 1.0/1.0 en texto y cifras en PDF
  nativos y 100 % de cifras en escaneos limpios a 200 dpi
  (ver `docs/METRICAS.md`).
- Documentación: `README.md`, `docs/DESPLIEGUE.md`, `docs/LICENCIAS.md`,
  `docs/LIMITES.md`, `docs/METRICAS.md` y `PROMPT_PARA_IA.md`.

### Límites conocidos
- Ver `docs/LIMITES.md`: gráficos vectoriales dentro de tablas, fuentes
  raras sin mapa de caracteres, formularios XFA, texto rotado 180° en
  PowerPoint y escaneos borrosos o manuscritos.
