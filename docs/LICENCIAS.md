# Licencias de las dependencias

## PyMuPDF — AGPL-3.0 (o comercial)
PyMuPDF se distribuye bajo **AGPL-3.0** (o licencia comercial de Artifex).
Para un servicio web público como este, la AGPL exige:
- publicar el código fuente del servicio (incluidas las modificaciones) bajo
  AGPL-3.0, con aviso de licencia, **o**
- comprar la licencia comercial de Artifex.

**Recomendación al dueño:** si el servicio va a ser público y no quieres
publicar el código, compra la licencia comercial antes de lanzar. Si el código
se publica (repositorio público con licencia AGPL-3.0), el uso es conforme.

**Alternativa sin AGPL:** sustituir PyMuPDF por `pypdf` (BSD-3-Clause) para
leer el PDF + `pdfplumber` (MIT) para extraer texto y `ocrmypdf`/Tesseract
para OCR. Es un cambio grande: habría que reescribir `extract.py` (PyMuPDF
aporta posiciones de caracteres, dibujos vectoriales e imágenes incrustadas en
una sola librería) y volver a medir la fidelidad. No se hizo en esta entrega.

## Resto de dependencias (verificadas en sus paquetes)

| Dependencia | Licencia | Uso |
|---|---|---|
| pdf2docx | GPL-3.0 | ruta de texto corrido a Word |
| python-docx | MIT | escribir .docx |
| python-pptx | MIT | escribir .pptx |
| openpyxl | MIT | escribir .xlsx |
| Pillow | MIT (HPND) | imágenes y binarización |
| NumPy | BSD-3-Clause | limpieza de líneas para OCR |
| FastAPI / Starlette | MIT | API HTTP |
| Uvicorn | BSD-3-Clause | servidor ASGI |
| Celery | BSD-3-Clause | cola de trabajos |
| redis (cliente) | MIT | cola y límite por IP |
| python-multipart | Apache-2.0 | subida de archivos |
| pytest / httpx (dev) | MIT / BSD-3-Clause | pruebas |
| locust (dev, carga) | MIT | prueba de carga |

**Ojo con pdf2docx (GPL-3.0):** es copyleft como la AGPL. Si el servicio se
publica bajo AGPL, pdf2docx es compatible. Si se compra la licencia comercial
de PyMuPDF, habría que revisar también pdf2docx (o eliminar la ruta `flow` y
usar solo la cuadrícula propia).

## Binarios del sistema (Dockerfile)
- Tesseract 5.x: Apache-2.0.
- OCRmyPDF: MPL-2.0.
- Ghostscript (dependencia de OCRmyPDF): AGPL-3.0.
- LibreOffice (solo verificación local, no se instala en la imagen): MPL-2.0.
