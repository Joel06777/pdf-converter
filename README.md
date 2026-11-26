# Convertidor PDF → Word / Excel / PowerPoint (motor propio)

Servicio independiente: no usa APIs de terceros. Se conecta a la página web (Vercel) por HTTP.

## Probar en local (sin Docker, sin Redis)
```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
sudo apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng ocrmypdf  # OCR para escaneados
python scripts/generate_fixtures.py   # genera los PDFs de prueba de tests/fixtures/
python scripts/convert_cli.py tests/fixtures/estado_ingresos_octubre_2026.pdf excel
pytest -q                            # 69 pruebas (medido el 26 nov 2026)
STORAGE_DIR=./data REDIS_URL= .venv/bin/uvicorn app.main:app --reload
```

## Producción
```bash
cp .env.example .env     # edita ALLOWED_ORIGINS, API_KEY, DOWNLOAD_SECRET y UPLOAD_SECRET
docker compose up -d --build --scale worker=2
```

Guía completa para desplegar sin pagar nada: `docs/DESPLIEGUE_GRATIS.md`
(Oracle Cloud Always Free + DuckDNS + Caddy). Para reconstruir el servidor
desde cero con un solo script: `scripts/bootstrap.sh`.

## API
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/upload-token` | pide un token de subida firmado (con API key; lo llama la función de Vercel, nunca el navegador) → `{upload_token, expires_in: 300, max_mb, upload_url}` |
| POST | `/api/v1/upload` | subida directa al backend con header `X-Upload-Token` (sin límite de 4,5 MB de Vercel) → `{job_id}` |
| POST | `/api/v1/convert` | `file` (PDF) + `target` = `excel` \| `word` \| `pptx` (+ `layout` = `pages`\|`continuous`, `formulas` = true\|false) → `{job_id}` |
| POST | `/api/v1/convert-many` | varios `files` + `target` → `{jobs: [{job_id, filename}]}` (máx. 20) |
| GET | `/api/v1/jobs/{id}` | estado (`queued/processing/done/error/cancelled`), progreso, informe `info.quality`, `download_url` |
| GET | `/api/v1/jobs/{id}/progress` | `{pages_done, pages_total, progress, status}` |
| POST | `/api/v1/jobs/{id}/cancel` | cancela un trabajo en cola o en proceso |
| GET | `/api/v1/jobs/{id}/download` | descarga el archivo (con `?token=` si hay `DOWNLOAD_SECRET`) |
| GET | `/health` | salud: Redis y espacio en disco |
| GET | `/metrics` | métricas Prometheus (trabajos por estado, duración, disco) |

Cada conversión devuelve `quality.text_coverage` y `quality.number_coverage` (1.0 = todo el texto y todas las cifras del PDF llegaron al archivo). Si el OCR tiene baja confianza, `info.ocr_warning` lo advierte en español y las celdas dudosas quedan resaltadas en amarillo en el Excel.

## Estructura
- `app/converters/extract.py`: lee texto, estilos, rellenos, líneas e imágenes del PDF (y OCR con limpieza previa + enderezado).
- `app/converters/pdf_to_excel.py`: reconstruye la cuadrícula visual → Excel con valores numéricos reales, formato, fórmulas de totales (solo si cuadran) y `layout=pages|continuous`.
- `app/converters/pdf_to_word.py`: tabla fiel (reportes) / pdf2docx (texto corrido) / OCR (escaneados); encabezados, fusiones verticales y listas.
- `app/converters/pdf_to_pptx.py`: una diapositiva editable por página; tablas nativas en páginas tabulares, rotación de texto.
- `app/converters/verify.py`: métrica de calidad automática.
- `app/converters/ocr.py`: enderezado, detección de rotación, confianza por palabra.
- `app/metrics.py`, `app/jsonlog.py`: métricas Prometheus y logs JSON sin contenido del documento.
- `web-example/`: frontend de ejemplo (HTML + JS puro) y funciones serverless de Vercel (`api/upload-token.js`, `api/convert.js`). El navegador sube el PDF directo al backend con un token firmado, sin pasar por Vercel (sin límite de 4,5 MB).
- `scripts/loadtest/`: prueba de carga con Locust y sus resultados medidos (`RESULTADOS.md`).
- `docs/`: `METRICAS.md` (medidas reales), `DESPLIEGUE.md`, `DESPLIEGUE_GRATIS.md` (Oracle Always Free paso a paso), `LICENCIAS.md`, `LIMITES.md`, `PRIVACIDAD.md`, `INFORME_FINAL.md`.
- `PROMPT_PARA_IA.md`: instrucciones completas para que otra IA continúe y amplíe el proyecto.

## Licencia

Este servicio se publica bajo la **GNU Affero General Public License v3.0
(AGPL-3.0)** — ver el archivo `LICENSE` y los avisos de terceros en `NOTICE`.
La razón es su motor, **PyMuPDF, que es AGPL-3.0** (o licencia comercial de
Artifex): al ofrecer el servicio por la web, la AGPL exige publicar el
código fuente del servicio, incluidas las modificaciones.

**Antes de lanzar, el repositorio debe hacerse público** (hoy es privado) y
la web debe mostrar un enlace visible **«Código fuente»** que apunte a ese
repositorio. Sin ese paso, el servicio no puede ofrecerse públicamente de
forma gratuita; la otra vía es comprar la licencia comercial de PyMuPDF.
Detalle, tabla completa de dependencias y la alternativa sin AGPL en
`docs/LICENCIAS.md`.

> Esto no es asesoría legal. Si el servicio va a ganar dinero, consulta a un
> abogado antes de lanzar.
