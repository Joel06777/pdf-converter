# Licencias de las dependencias

> **⚠️ Esto NO es asesoría legal.** Es una auditoría técnica de licencias hecha
> el 26 de noviembre de 2026 a partir de los metadatos de los paquetes
> instalados, de PyPI y de los repositorios oficiales. Si el servicio va a
> ganar dinero o a tratar datos sensibles, consulta a un abogado antes de
> lanzar. Las licencias cambian: vuelve a comprobar esta tabla cada vez que
> actualices una dependencia.

## Decisión: opción gratuita = cumplir la AGPL-3.0

El servicio completo se publica bajo **GNU AGPL-3.0** (archivo `LICENSE` en la
raíz del repositorio). Eso es gratis y es la única vía gratuita, porque el
motor del servicio, **PyMuPDF, es AGPL-3.0** y no hay forma de usarlo en un
servicio web público y cerrado sin pagar su licencia comercial.

Cumplir la AGPL significa, en la práctica, estas tres cosas (hazlas **antes**
de lanzar):

1. **Hacer público el repositorio** `Joel06777/pdf-converter` (hoy es
   privado) con el archivo `LICENSE` (texto completo de la AGPL-3.0) y el
   archivo `NOTICE` con los avisos de terceros.
2. **Poner un enlace visible «Código fuente» en la web** (por ejemplo, en el
   pie de página) que apunte al repositorio público. La AGPL, sección 13,
   exige que quien use el servicio por la red pueda obtener el código fuente
   correspondiente —incluidas tus modificaciones— desde un servidor de red sin
   coste.
3. **Publicar el código tal como está desplegado**: el repositorio público
   debe ser el mismo código que corre en el servidor (incluidos `Dockerfile`,
   `docker-compose.yml` y `.env.example`). Lo único que NO se publica es el
   archivo `.env` con las claves secretas (ya está en `.gitignore`).

La alternativa de pago es comprar la **licencia comercial de PyMuPDF a
Artifex** (precio bajo presupuesto, no publicado; hay que pedirlo en
<https://artifex.com/licensing>). Con esa licencia el servicio podría ser
cerrado — pero ojo: habría que revisar también el resto de dependencias
copyleft que haya en ese momento (hoy, tras la corrección de pdf2docx que se
explica abajo, no queda ninguna otra dependencia copyleft fuerte en el
servicio, salvo Ghostscript como proceso del sistema; ver la tabla).

## Tabla auditada (versiones fijadas en `requirements.txt` y `Dockerfile`)

Método de verificación: licencia declarada en los metadatos del paquete
instalado en el entorno del proyecto (`.venv`), contrastada con la ficha de
PyPI (`https://pypi.org/pypi/<paquete>/<versión>/json`) y con el repositorio
oficial. «Compatible con AGPL-3.0» significa que esa licencia permite
combinar el componente en un servicio publicado bajo AGPL-3.0.

### Python — dependencias directas (`requirements.txt`)

| Dependencia | Versión | Licencia | Fuente oficial | Compatible con AGPL-3.0 |
|---|---|---|---|---|
| PyMuPDF (`pymupdf`) | 2.2 | **AGPL-3.0 o comercial Artifex** | <https://github.com/pymupdf/PyMuPDF> · <https://pypi.org/project/pymupdf/> | Es la licencia que manda: todo el servicio va bajo AGPL-3.0 |
| pdf2docx | 0.5.13 | **MIT** ✅ (ver corrección abajo) | <https://github.com/ArtifexSoftware/pdf2docx> · <https://pypi.org/project/pdf2docx/> | Sí |
| python-docx | 1.2.0 | MIT | <https://github.com/python-openxml/python-docx> · <https://pypi.org/project/python-docx/> | Sí |
| python-pptx | 1.0.2 | MIT | <https://github.com/python-openxml/python-pptx> · <https://pypi.org/project/python-pptx/> | Sí |
| openpyxl | 3.1.5 | MIT | <https://foss.heptapod.net/openpyxl/openpyxl> · <https://pypi.org/project/openpyxl/> | Sí |
| Pillow | 12.3.0 | MIT-CMU (licencia tipo HPND) | <https://github.com/python-pillow/Pillow> · <https://pypi.org/project/pillow/> | Sí |
| NumPy | 2.5.3 | BSD-3-Clause (y otras permisivas) | <https://github.com/numpy/numpy> · <https://pypi.org/project/numpy/> | Sí |
| FastAPI | 0.165.0 | MIT | <https://github.com/fastapi/fastapi> · <https://pypi.org/project/fastapi/> | Sí |
| Starlette (dependencia de FastAPI) | 1.10.0 | BSD-3-Clause | <https://github.com/encode/starlette> | Sí |
| Uvicorn | 0.54.0 | BSD-3-Clause | <https://github.com/encode/uvicorn> · <https://pypi.org/project/uvicorn/> | Sí |
| python-multipart | 0.0.32 | Apache-2.0 | <https://github.com/Kludex/python-multipart> · <https://pypi.org/project/python-multipart/> | Sí |
| Celery | 5.7.0 | BSD-3-Clause | <https://github.com/celery/celery> · <https://pypi.org/project/celery/> | Sí |
| redis (cliente Python) | 8.2.0 | MIT | <https://github.com/redis/redis-py> · <https://pypi.org/project/redis/> | Sí |
| Pydantic (dependencia de FastAPI) | 2.14.4 | MIT | <https://github.com/pydantic/pydantic> | Sí |

### Python — dependencias transitivas de pdf2docx

`pdf2docx` declara en PyPI que necesita `PyMuPDF>=1.26.7`,
`python-docx>=0.8.10`, `fonttools>=4.24.0`, `numpy>=1.17.2`,
`opencv-python-headless>=4.5` y `fire>=0.3.0`. Todas son permisivas:

| Dependencia | Licencia | Fuente |
|---|---|---|
| fonttools | MIT | <https://github.com/fonttools/fonttools> |
| opencv-python-headless | Apache-2.0 | <https://github.com/opencv/opencv-python> |
| fire | Apache-2.0 | <https://github.com/google/python-fire> |

### Python — solo desarrollo (`requirements-dev.txt`, no se despliega)

| Dependencia | Licencia | Fuente |
|---|---|---|
| pytest | MIT | <https://github.com/pytest-dev/pytest> |
| httpx | BSD-3-Clause | <https://github.com/encode/httpx> |
| locust | MIT | <https://github.com/locustio/locust> |

### Sistema — paquetes del `Dockerfile` (imagen `python:3.12-slim`, Debian)

| Componente | Licencia | Fuente oficial | Compatible con AGPL-3.0 |
|---|---|---|---|
| Tesseract OCR (`tesseract-ocr`, `tesseract-ocr-spa`, `tesseract-ocr-eng`) | Apache-2.0 | <https://github.com/tesseract-ocr/tesseract> | Sí |
| OCRmyPDF (`ocrmypdf`) | MPL-2.0 | <https://github.com/ocrmypdf/OCRmyPDF> | Sí (copyleft débil, solo a nivel de archivo: si se modificara OCRmyPDF habría que publicar esos cambios; no se modifica) |
| Ghostscript | **AGPL-3.0** (o comercial Artifex) | <https://www.ghostscript.com/> · <https://artifex.com/licensing> | Sí, misma familia que la AGPL del servicio. Ver nota abajo |
| fonts-liberation | SIL Open Font License 1.1 | <https://github.com/liberationfonts/liberation-fonts> | Sí |
| fonts-dejavu-core | Licencia Bitstream Vera (permisiva; partes en dominio público) | <https://dejavu-fonts.github.io/> | Sí |
| Servidor Redis (`redis:7-alpine` en `docker-compose.yml`) | BSD-3-Clause | <https://github.com/redis/redis> | Sí. ⚠️ No subas a `redis:8` sin revisar: desde Redis 8 el servidor cambió a licencias RSALv2/SSPL. El `docker-compose.yml` fija `redis:7-alpine`; déjalo así |

### Solo verificación local (NO se instala en la imagen Docker)

| Componente | Licencia | Nota |
|---|---|---|
| LibreOffice | MPL-2.0 | Solo como herramienta local opcional de verificación, según `PROMPT_PARA_IA.md`. No forma parte del servicio |

### Despliegue (no es código del servicio, pero conviene saberlo)

| Componente | Licencia | Nota |
|---|---|---|
| Caddy (HTTPS automático, ver `docs/DESPLIEGUE.md`) | Apache-2.0 | No verificado directamente en esta ronda: Caddy no forma parte del código del servicio, solo del despliegue. Comprobar en <https://github.com/caddyserver/caddy> antes de citarlo como definitivo |

## Corrección importante: pdf2docx YA NO es GPL

La versión anterior de este documento decía que pdf2docx era **GPL-3.0**.
Eso era cierto para las versiones antiguas, pero **ya no es vigente**:

- El repositorio oficial es ahora
  <https://github.com/ArtifexSoftware/pdf2docx> (Artifex compró el proyecto
  al autor original, `dothinking`).
- Artifex lo ha **relicenciado bajo la licencia MIT**: el archivo `LICENSE`
  del repositorio dice «Copyright (c) 2026 Artifex Software, Inc.» con el
  texto estándar del MIT, y la página del proyecto en GitHub muestra
  «License: MIT License (MIT)».
- La versión fijada en este proyecto, **pdf2docx 0.5.13 (publicada en PyPI
  el 1 de mayo de 2026)**, declara `"license": "MIT"` en su ficha oficial de
  PyPI (<https://pypi.org/pypi/pdf2docx/0.5.13/json>) y su descripción dice
  literalmente que ha sido «relicensed under the MIT License».

**Qué significa esto en la práctica:**

- pdf2docx ya no impone ninguna obligación copyleft al servicio. Es una
  dependencia permisiva más, como python-docx.
- **No bajes la versión de pdf2docx.** Las versiones antiguas (las del autor
  original) sí eran GPL-3.0. Si alguien fijara una versión vieja, volvería
  el problema que se describe en el apartado siguiente.
- pdf2docx sigue dependiendo de PyMuPDF (`PyMuPDF>=1.26.7`), así que la
  obligación AGPL del servicio no desaparece: viene de PyMuPDF, no de
  pdf2docx.

### Qué habría implicado pdf2docx si siguiera siendo GPL-3.0

Se deja explicado porque es la duda que tenía la versión anterior del
documento, y porque aplica a cualquier dependencia GPL que se añada en el
futuro:

- La **GPL-3.0 y la AGPL-3.0 son compatibles para combinarse**: la sección 13
  de la AGPL permite enlazar o combinar una obra AGPL con una obra GPL-3.0
  en una sola obra combinada, que se publica bajo AGPL-3.0. Es decir, un
  pdf2docx GPL **no habría impedido** publicar todo el servicio bajo
  AGPL-3.0. No habría habido que sustituirlo para la opción gratuita.
- Lo que **sí** habría impedido es la opción de pago: si se compra la
  licencia comercial de PyMuPDF para mantener el servicio cerrado, una
  dependencia GPL-3.0 no podría quedarse dentro de un servicio cerrado. En
  ese caso habría habido que eliminar la ruta `flow` de Word (la única que
  usa pdf2docx, en `app/converters/pdf_to_word.py`) o sustituir pdf2docx.
- Con pdf2docx ya en MIT, ese problema **desapareció**: la única barrera
  para un servicio cerrado es hoy PyMuPDF (y Ghostscript, ver abajo).

## Nota sobre Ghostscript (AGPL-3.0)

Ghostscript **no se instala directamente** en el `Dockerfile`: llega como
dependencia del paquete Debian `ocrmypdf`. El código del servicio no lo
llama directamente; lo usa OCRmyPDF como proceso independiente del sistema.
Aun así:

- Como el servicio entero ya se publica bajo AGPL-3.0, Ghostscript no añade
  ninguna obligación nueva: su licencia es de la misma familia y el servicio
  ya cumple lo que pide.
- Si algún día se comprara la licencia comercial de PyMuPDF para cerrar el
  servicio, Ghostscript seguiría siendo AGPL y habría que tratarlo aparte
  (comprar su licencia comercial, sustituir esa parte de OCRmyPDF, o
  verificar si el uso como proceso separado lo permite — eso lo debe decidir
  un abogado).
- Para confirmarlo en tu servidor, ejecuta dentro del contenedor:
  `docker compose exec api dpkg -l | grep -E "ghostscript|ocrmypdf|tesseract"`.

## Alternativa permisiva (SIN implementar): sustituir PyMuPDF

> **Documentación, no implementación.** Nadie ha cambiado el código. Esto es
> lo que habría que hacer si algún día se quisiera un servicio cerrado sin
> pagar la licencia comercial de PyMuPDF.

**Reemplazo propuesto:** `pypdfium2` (Apache-2.0 / BSD-3-Clause, enlaces a
PDFium, el motor de PDF de Chrome) para leer y renderizar el PDF, más
`pdfminer.six` / `pdfplumber` (MIT) para extraer el texto con posiciones.
Fuentes: <https://github.com/pypdfium2-team/pypdfium2>,
<https://github.com/pdfminer/pdfminer.six>,
<https://github.com/jsvine/pdfplumber>.

### Dónde se usa PyMuPDF hoy (solo lectura del código, sin tocarlo)

PyMuPDF aparece en **7 archivos** de `app/`, en unos 35 puntos de uso:

| Archivo | Uso de PyMuPDF |
|---|---|
| `app/converters/extract.py` (el núcleo) | `get_text("rawdict")` con spans, caracteres, fuentes, tamaños, colores y dirección del texto; `get_image_info` + `Pixmap` + `extract_image` (imágenes con transparencia/smask); `get_drawings` (rellenos y líneas vectoriales); `get_pixmap` (renderizar páginas y regiones a PNG); `get_textpage_ocr` (OCR de Tesseract integrado con coordenadas); crear un documento temporal con `open()` + `insert_image` para la copia binarizada y enderezada |
| `app/converters/ocr.py` | Abrir el PDF, `get_pixmap` en gris a 300 dpi, rotar la imagen de la página, detectar rotación |
| `app/converters/pdf_to_excel.py` | `pymupdf.open(src)` para recorrer las páginas y construir el modelo |
| `app/converters/pdf_to_word.py` | Detección de escaneo, apertura del PDF; además la ruta `flow` usa pdf2docx, que a su vez exige PyMuPDF (si se quita PyMuPDF, la ruta `flow` desaparece también) |
| `app/converters/pdf_to_pptx.py` | `pymupdf.open(src)` para recorrer las páginas |
| `app/converters/verify.py` | `pymupdf.open` + `get_text("words")` para medir la cobertura de texto y cifras |
| `app/processing.py` | `pymupdf.open`, `needs_pass` (PDF con contraseña), `page_count`, `xref_get_key` para detectar formularios XFA |

### Estimación honesta del esfuerzo

- **Tiempo: de 2 a 4 semanas de trabajo concentrado** para una persona con
  experiencia (o 3 a 6 semanas a ritmo parcial). No es un presupuesto, es
  una estimación: la mayor parte es reescribir `extract.py` y volver a medir
  la fidelidad.
- **Archivos afectados:** los 7 de la tabla, más `requirements.txt`
  (quitar `pymupdf` y `pdf2docx`, añadir `pypdfium2`, `pdfminer.six`,
  `pdfplumber`), `Dockerfile` (quizá nada, Tesseract seguiría), los 7
  fixtures de `tests/fixtures/` y las 33 pruebas (habría que reescribir las
  que dependen del modelo de PyMuPDF).
- **Pasos:** (1) reescribir `extract.py` con pdfminer.six/pypdfium2;
  (2) rehacer el OCR (hoy `get_textpage_ocr` lo hace PyMuPDF por dentro:
  habría que llamar a Tesseract por línea de comandos y convertir sus
  coordenadas a puntos PDF); (3) rehacer la extracción de imágenes y el
  renderizado con pypdfium2; (4) eliminar la ruta `flow` de Word o
  reescribirla con código propio; (5) volver a medir la fidelidad en los 7
  fixtures × 3 destinos (`docs/METRICAS.md`) y corregir hasta recuperar el
  1.0 en texto y cifras; (6) volver a pasar las 33 pruebas y la prueba de
  carga.

### Qué se perdería (riesgo para la fidelidad)

- **OCR integrado con coordenadas:** hoy PyMuPDF devuelve el texto del OCR
  ya colocado en coordenadas de página. Con Tesseract por línea de comandos
  hay que mapear las coordenadas a mano (escala píxel → punto, página
  enderezada), y es fácil introducir desplazamientos de 1–2 mm que rompen
  las tablas.
- **Texto con estilo a nivel de carácter:** `rawdict` da cada carácter con
  su fuente, tamaño, color y negrita/cursiva (por bits de `flags`).
  pdfminer.six también da caracteres con fuente y tamaño, pero la
  detección de negrita/cursiva es heurística (por el nombre de la fuente) y
  menos fiable.
- **Vectores (rellenos y líneas de tabla):** `get_drawings` da rectángulos,
  líneas y curvas con relleno y trazo en una sola llamada. pdfminer.six da
  `LTLine`/`LTRect`/`LTCurve`, pero no distingue igual de bien un
  rectángulo de relleno de un borde, ni rasteriza los logotipos vectoriales
  complejos (hoy se convierten a imagen en su posición).
- **Imágenes incrustadas con transparencia:** la extracción con `smask`
  (máscara de transparencia) es específica de PyMuPDF; con pypdfium2 el
  camino habitual es renderizar la página, que pierde la imagen original
  como objeto editable.
- **Renderizado de páginas:** pypdfium2 renderiza bien (es el motor de
  Chrome), así que esta parte es la de menor riesgo.
- **Detección de XFA y de contraseña:** hay que reimplementarla con otra
  librería (`pypdf`, BSD-3-Clause, por ejemplo), porque es una comprobación
  de `xref` propia de PyMuPDF.
- **Conclusión:** el cambio es viable, pero la fidelidad medida hoy
  (1.0/1.0 en texto y cifras en los 7 fixtures, 100 % de cifras en OCR a
  200 dpi) **no se conservaría automáticamente**: habría que volver a
  medirlo todo y aceptar que algunos PDFs queden algo peor, sobre todo los
  escaneados y los que usan vectores.

## Qué hacer antes de lanzar (lista de comprobación)

- [ ] Archivo `LICENSE` con el texto completo de la AGPL-3.0 en la raíz del
      repositorio (ya creado en esta ronda).
- [ ] Archivo `NOTICE` con los avisos de terceros (ya creado en esta ronda).
- [ ] Repositorio en **público** (hoy es privado).
- [ ] Enlace **«Código fuente»** visible en la web, apuntando al repositorio
      público.
- [ ] Comprobar que el repositorio público contiene exactamente el código
      desplegado (sin el `.env`).
- [ ] Si se actualiza cualquier dependencia, revisar su licencia en esta
      tabla y actualizarla.
