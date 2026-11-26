# Changelog

Todos los cambios notables de este proyecto, en orden cronológico inverso.
Formato inspirado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Sin publicar]

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
