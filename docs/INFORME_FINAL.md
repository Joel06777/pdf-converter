# Informe final — Convertidor PDF (segunda ronda, 26 nov 2026)

Proyecto: convertidor de PDF a Word / Excel / PowerPoint con motor propio
(FastAPI + Celery + Redis, Docker). Repositorio privado:
https://github.com/Joel06777/pdf-converter (rama `main`, head `a44924d`
antes de esta ronda; el push de esta ronda lo hace el dueño con ayuda de
Snoop). Todo el trabajo se hizo con costo cero y sin servicios de pago.

> Esto no es asesoría legal. La sección de licencias resume lo auditado;
> ante duda legal, consulta a un abogado.

## 1. Qué se corrigió y cómo se verificó (comandos y resultados reales)

### 1.1 Estado base verificado por mí al empezar (no heredado)
```bash
cd ~/workspace/pdf-converter-work/pdf-converter
.venv/bin/python -m pytest -q
# 33 passed, 2 warnings, en 67,98 s
```
VM de verificación: 4 vCPU con cuota compartida, 7,7 GB RAM, x86_64,
sin Docker (`docker: command not found`), sin Redis, sin `.git` local.

### 1.2 Subida por Vercel: límite de 4,5 MB (corregido)
Antes, el PDF viajaba navegador → función Vercel → backend y cualquier
PDF de más de 4,5 MB fallaba con 413 (límite del plan Hobby de Vercel).
Ahora:
- `POST /api/v1/upload-token` (con API key, solo lo llama la función
  serverless de Vercel) entrega un token firmado HMAC-SHA256 con
  `UPLOAD_SECRET`: caduca en 5 minutos, de un solo uso (nonce guardado
  en disco o en Redis), con límite de tamaño `max_mb`.
- `POST /api/v1/upload` recibe el PDF directo del navegador con el
  header `X-Upload-Token`. La API key nunca llega al navegador
  (verificado con `grep` en `web-example/app.js` e `index.html`).
- El backend valida firma, caducidad y uso único; el nonce solo se
  consume tras aceptar el archivo (un 413 o 400 no lo consume).
- Estado y descarga firmada (15 min) van directo al backend.
- Nueva función `web-example/api/upload-token.js` y flujo nuevo en
  `web-example/app.js` (el flujo antiguo por `/api/v1/convert` queda
  como respaldo documentado, solo hasta 4,5 MB).

Verificación: `tests/test_upload_token.py` (9 pruebas): token válido
sube y descarga; sin API key → 401; sin token → 401; caducado → 401;
reutilizado tras consumo → 401; manipulado → 401; `max_mb=1` con PDF
de 2 MB → 413 y el token sigue valiendo; **PDF sintético de 40 MB de
principio a fin** (2 páginas con relleno, 40,00 MB medidos): subida
202 → trabajo `done` con cobertura de texto 1,0 → descarga 200;
sin `UPLOAD_SECRET` → 503.

### 1.3 QR solapado con texto en Word (corregido)
Reproducido renderizando el Word del documento de referencia con
LibreOffice a PDF: los textos de las firmas («SABEL MARITZA…»,
«Validar…») caían sobre los QR de 36×36 pt. Dos causas en
`app/converters/pdf_to_word.py`: la tabla usaba 12 columnas iguales
(`tblGrid` en 970 twips) y el texto desbordado invadía la fusión vecina.
Corrección: anchos reales de columna en la cuadrícula, fusiones vecinas
protegidas y las 5 imágenes ancladas a su propio párrafo vacío.
Verificación: LibreOffice renderiza **0 solapes >1 pt** en la zona de
firmas; los textos quedan en sus posiciones del PDF; cobertura de texto
y cifras sigue en **1,0**. Queda un roce de 0,35 pt (0,12 mm) entre el
borde del QR2 y el inicio de los textos de Sabel, porque el propio PDF
solo deja 0,7 pt de holgura ahí: invisible, no corregible sin sangrar
cada párrafo. Pruebas: `tests/test_word_qr.py` (2 pruebas: estructural
y de renderizado con LibreOffice, que se salta si no hay `soffice`).

### 1.4 Licencias (auditoría completa)
- `LICENSE` con el texto completo de la AGPL-3.0 (descargado de
  gnu.org, 34.523 bytes, 661 líneas) y `NOTICE` con avisos de terceros.
- `docs/LICENCIAS.md` reescrito: tabla auditada de todas las
  dependencias Python y del sistema, con licencia y enlace.
- Hallazgo: **pdf2docx 0.5.13 es MIT, no GPL-3.0** (Artifex lo
  relicenció; verificado en PyPI y en su repositorio oficial). No bajar
  la versión: las antiguas sí eran GPL. La barrera para un servicio
  cerrado sigue siendo PyMuPDF (AGPL) y Ghostscript (AGPL, dependencia
  de OCRmyPDF).
- Decisión gratuita: cumplir la AGPL — repositorio público, archivo
  `LICENSE` y enlace visible «Código fuente» en la web. Hoy el repo es
  privado: **no se hizo público en esta ronda**; es un paso manual del
  dueño (ver §4).
- Alternativa permisiva documentada sin implementar: reemplazar PyMuPDF
  por pypdfium2 + pdfminer.six/pdfplumber (7 archivos afectados,
  ~35 puntos de uso, estimación 2–4 semanas concentrado, con riesgos de
  fidelidad detallados en `docs/LICENCIAS.md`).
- Nota añadida en `README.md` y `docs/LICENCIAS.md`: esto no es
  asesoría legal.

### 1.5 Despliegue gratis y Plan B
- `docs/DESPLIEGUE_GRATIS.md` (593 líneas): guía paso a paso para no
  programador — Oracle Cloud Always Free (A1.Flex ARM), puertos 80/443,
  Docker y Docker Compose, dominio gratuito DuckDNS, HTTPS automático
  con Caddy (Let's Encrypt gratis), `.env` de producción, variables en
  Vercel, actualización y logs, y alternativa casera (PC vieja 24/7)
  con pros y contras honestos. No se usa Hugging Face Spaces (reportes
  2026 de cuota de CPU en cero en cuentas nuevas).
- `scripts/bootstrap.sh`: reconstruye el servidor en un solo comando
  (instala Docker, clona/actualiza el repo, genera `.env` si no existe,
  levanta Caddy). Validado con `bash -n` (correcto); `shellcheck` no
  existe en esta VM, así que no se validó con él.
- Fuentes oficiales verificadas en esta ronda: Oracle Always Free
  (docs.oracle.com — 2 OCPU/12 GB, 200 GB, 10 TB/mes, región principal
  no cambiable, reclamación por inactividad a los 7 días), Vercel Hobby
  y su límite de 4,5 MB, DuckDNS, Cloudflare Turnstile (verificado
  gratis: 0 $/mes, retos ilimitados, 20 widgets, sin tarjeta; solo
  documentado, no implementado). Lo no verificado está marcado como tal
  en la guía.

### 1.6 ARM y CI
- `.github/workflows/ci.yml`: nuevo trabajo `docker-build-arm64`
  (QEMU + buildx, `linux/arm64`, caché, timeout 60 min) que construye,
  verifica arquitectura y ruedas nativas, comprueba `/health`, hace un
  humo de conversión y ejecuta un subconjunto rápido de pytest dentro
  del contenedor. El build amd64 ganó el mismo humo de conversión.
  Sintaxis YAML verificada con `yaml.safe_load` (3 trabajos).
- Dockerfile: comentario con las ruedas `aarch64` verificadas en PyPI
  para las versiones fijadas (PyMuPDF, NumPy, Pillow, opencv); la base
  `python:3.12-slim` es multi-arquitectura.
- **No verificado: ningún build Docker se ejecutó aquí** (no hay Docker
  en esta VM). La CI queda lista para GitHub.

### 1.7 Capacidad real y protección
- `MAX_QUEUE_JOBS=50` (nuevo) y `MAX_OCR_PAGES=20` (nuevo) en
  `app/config.py` y `.env.example`.
- Tope de cola en `app/main.py` (`/convert`, `/convert-many`,
  `/upload`): si la cola supera el tope, la API responde **503
  «Estamos con mucha demanda, intenta en unos minutos»** sin consumir
  el token de subida. Medido con `MAX_QUEUE_JOBS=5`: 327 intentos,
  285 rechazados con 503 (87 %), 42 aceptados, E2E mediana 6,4 s.
- `app/jobs.py`: `count_active_jobs()` (cuenta `state.json`; no es
  atómico y puede incluir trabajos de workers caídos hasta el TTL).
- `app/processing.py`: más de 20 páginas escaneadas → error claro.
- `docker-compose.yml`: memoria por worker 2g → 1g (medido), límites
  en api (1g), redis y beat (256m); `max-tasks-per-child=50` se
  mantiene (la RSS creció sin bajar al drenar).
- Pruebas: `tests/test_capacidad.py` (5 pruebas).

### 1.8 Calidad: 5 fixtures nuevos y OCR mejorado
Fixtures nuevos (generados con `scripts/generate_fixtures.py`,
deterministas): factura real con logo y sello, tabla con fusiones
verticales y horizontales, documento a dos columnas con tablas,
escaneado en color con sello y marca de agua, foto de celular con
perspectiva. 20 pruebas nuevas en `tests/test_fixtures.py`.
- OCR: fusión `$` + cifra en la misma celda (era la causa real de la
  pérdida de texto), guarda de binarización por densidad de tinta y
  validación subtotal + IVA = total solo para marcar celdas dudosas
  (nunca cambia valores). Probado y revertido/documentado: binarización
  adaptativa NumPy y OpenCV (empeora), Otsu (baja cifras), 400 dpi
  (mixto, más lento), `tessdata_best` (peor: texto 97,9 % → 87,5 %),
  PSM 6 (innecesario). No se añade `opencv-python-headless`.
- `info["quality"]` incluye `missing_sample` con las palabras que
  faltan en los 3 destinos (verificado borrando «Pintura»).

### 1.9 Repositorio
- Escaneo de secretos: `grep` de claves, tokens y llaves privadas en
  `app/`, `scripts/` y `tests/` → **sin coincidencias**; no hay archivo
  `.env` en el proyecto (`.env` está en `.gitignore`). No hay historial
  git local (no existe `.git` en este equipo), así que **no se pudo
  revisar el historial de git**: el dueño debe revisar el historial en
  GitHub (ver §4, paso 6).
- `README.md` actualizado: 69 pruebas, endpoints de subida directa,
  despliegue gratis, `scale worker=2`.
- `CHANGELOG.md`: v1.0.0 «sin publicar aún» y sección «Sin publicar»
  con esta ronda. **No se creó el tag v1.0.0 en GitHub** (paso manual,
  ver §4).
- `docs/PRIVACIDAD.md`: política en español basada en el código real
  (el original se borra al terminar, resultados a los 60 minutos, logs
  sin contenido de documentos; matiz honesto: el log guarda el nombre
  del archivo y la IP se usa para el límite por hora).

## 2. Resultados de las verificaciones

### pytest (ejecutado por mí al final)
```bash
.venv/bin/python -m pytest -q
# 69 passed, 2 warnings, en 109,60 s
```
Base al empezar la ronda: 33 passed. Nuevas: 11 (token de subida 9 +
QR en Word 2) + 5 (capacidad) + 20 (fixtures nuevos) = 36; total 69.
Ninguna prueba existente se rompió ni se debilitó.

### CI en GitHub Actions
**No ejecutada aquí.** La CI está lista (`.github/workflows/ci.yml`
con 3 trabajos: `test`, `docker-build` amd64 y `docker-build-arm64`).
Ejecución en GitHub (tras el push):
https://github.com/Joel06777/pdf-converter/actions — el dueño debe
comprobar que esté en verde; si un trabajo falla, hay que corregirlo
sin desactivar pruebas.

### Build Docker amd64 / arm64
**No ejecutado aquí** (no hay Docker en esta VM). Queda para la CI de
GitHub. El Dockerfile es multi-arquitectura y las ruedas `aarch64` de
las dependencias fijadas se verificaron en PyPI.

## 3. Métricas

### Calidad por tipo de documento (medido; detalle en `docs/METRICAS.md`)
Texto nativo: cobertura de texto y cifras **1,0 / 1,0 en los 12
fixtures y los 3 destinos** (Excel, Word, PowerPoint), incluida la
referencia `estado_ingresos_octubre_2026.pdf`.

OCR (tokens de texto + cifras; cifras por separado: 100 % en todos
los casos):

| Caso | Antes (tokens) | Después (tokens) | Texto solo, después |
|---|---|---|---|
| Referencia escaneada 200 dpi | 90,3 % | 90,3 % | 88,6 % |
| Factura escaneada 200 dpi | 87,1 % | **98,4 %** | 97,9 % |
| Foto inclinada 3° | 85,5 % | **96,8 %** | 95,8 % |
| Escaneado color + sello + marca de agua (nuevo) | — | **98,4 %** | 97,9 % |
| Foto con perspectiva + 2° (nuevo) | — | **96,8 %** | 95,8 % |

Lo que queda por debajo del 100 % es casi todo el símbolo `Nº`
(Tesseract lo lee `N?`/`N*`/`N®`) y alguna palabra junto a líneas de
tabla; no se encontró una corrección segura sin riesgo de tocar valores.

Tiempos (1 página): Excel referencia 0,35 s; Word referencia 4,58 s;
OCR ~4–6 s por página; referencia escaneada 14,7 s.

### Carga (medido el 26 nov 2026; detalle en `scripts/loadtest/RESULTADOS.md`)
Entorno: VM de 4 vCPU con cuota compartida de 1,5, 7,7 GB RAM, x86_64,
sin Docker ni Redis, API en modo inline. **No es Oracle** (2 OCPU ARM /
12 GB): no trasladar estos números sin medir allí. PDFs con texto
nativo (sin OCR). Disco de la VM casi lleno durante la prueba (228–290
MB libres): posible distorsión, anotada en los resultados.

| Prueba | Resultado |
|---|---|
| 1 usuario, 1 pág. → Excel | extremo a extremo 0,30 s |
| 1 usuario, 10 págs. → Excel | extremo a extremo 0,44 s |
| 1 usuario, 50 págs. → Excel | extremo a extremo 1,30 s |
| 1 usuario, 50 págs. → Word | extremo a extremo 11,25 s |
| Humo, 10 usuarios, 1 min | POST 83, 0 fallos, mediana 100 ms, p95 2,6 s; E2E mediana 3,1 s, p95 11,0 s |
| Carga, 200 usuarios, rampa 10/s, 2 min | POST 169, **0 fallos**, mediana 35 s, p95 99 s; E2E 34, mediana 40 s, p95 103 s; **~43 conversiones/min sostenidas**; 0 trabajos en error |
| Protección, `MAX_QUEUE_JOBS=5` | 285 de 327 rechazados con 503 (87 %); E2E mediana 6,4 s |

Lectura: en modo inline Starlette usa un pool de 40 hilos y la GIL
satura la CPU; el modo inline no es apto para carga. En producción la
conversión va a workers Celery. Configuración recomendada para Oracle
(extrapolación, hay que medirla allí): 2 workers × concurrency 2,
`MAX_PAGES=200`, `MAX_UPLOAD_MB=50`, `RATE_LIMIT_PER_HOUR=60`,
`TASK_TIME_LIMIT=600`, `MAX_QUEUE_JOBS=50`, `MAX_OCR_PAGES=20`,
memoria por worker 1g. Caudal teórico: ~80–240/min en Excel,
~22/min en el peor caso (Word de 50 páginas).

## 4. Pasos manuales que solo el dueño puede hacer

### 4.1 Subir esta ronda a GitHub y comprobar la CI
1. En el chat, pedir a Snoop que suba los cambios (él hace el push).
2. Abrir https://github.com/Joel06777/pdf-converter/actions
3. Ver la ejecución más reciente: los 3 trabajos (`test`,
   `docker-build`, `docker-build-arm64`) deben estar en verde. Si
   alguno falla, no lanzar todavía: avisar a Snoop con el nombre del
   trabajo que falló.

### 4.2 Hacer público el repositorio (obligatorio antes de lanzar)
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

### 4.3 Crear la etiqueta v1.0.0
1. Cuando la CI esté en verde, abrir
   https://github.com/Joel06777/pdf-converter/releases/new
2. En «Choose a tag» escribir `v1.0.0` y pulsar «Create new tag».
3. Título: `v1.0.0`. Descripción: copiar la sección `[v1.0.0]` y
   `[Sin publicar]` de `CHANGELOG.md`.
4. Pulsar «Publish release».

### 4.4 Crear la cuenta de Oracle y la instancia (gratis)
Guía completa paso a paso en `docs/DESPLIEGUE_GRATIS.md`, sección 1.
Resumen: crear la cuenta en Oracle Cloud (pide tarjeta solo para
verificar la identidad; el plan Always Free no cobra mientras no se
cambie a pago), elegir la región principal (no se puede cambiar
después), crear una instancia A1.Flex ARM (2 OCPU, 12 GB), imagen
Ubuntu 24.04, y abrir los puertos 80 y 443. Si sale «sin capacidad»:
reintentarlo en otra hora o en otra zona de disponibilidad.

### 4.5 Generar los secretos y guardarlos (nunca subirlos a GitHub)
En el servidor Oracle, ejecutar y copiar cada valor:
```bash
openssl rand -hex 32   # API_KEY (ejecutar 1 vez)
openssl rand -hex 32   # DOWNLOAD_SECRET (ejecutar otra vez)
openssl rand -hex 32   # UPLOAD_SECRET (ejecutar otra vez)
```
Pegar los tres valores en el archivo `.env` del servidor, junto con
`ALLOWED_ORIGINS=https://tu-sitio.vercel.app` (tu dominio real de
Vercel). El archivo `.env` nunca se sube a GitHub (está en
`.gitignore`).

### 4.6 Revisar el historial de git en busca de secretos
En este equipo no había historial git local, así que no se pudo
revisar. En GitHub, abrir
https://github.com/Joel06777/pdf-converter/commits/main y revisar que
ningún commit contenga un `.env` ni claves reales. Si aparece alguno,
avisar a Snoop: hay que limpiar el historial y rotar esa clave.

### 4.7 Pegar las variables en Vercel
1. Abrir el proyecto web en https://vercel.com → Settings →
   Environment Variables.
2. Añadir: `CONVERTER_BACKEND_URL` = `https://tu-dominio.duckdns.org`
   (el dominio del servidor Oracle), `CONVERTER_API_KEY` = el valor de
   `API_KEY` del servidor, `UPLOAD_SECRET` = el mismo valor que en el
   `.env` del servidor.
3. Volver a desplegar la web (Deployments → Redeploy).

### 4.8 Probar la subida grande en la web real
Subir en la web un PDF de más de 4,5 MB (por ejemplo 10–20 MB) y
comprobar que convierte y descarga. Si falla con 413, revisar que
`UPLOAD_SECRET` sea el mismo en Vercel y en el servidor.

## 5. Límites conocidos y riesgos
- **Oracle puede reclamar la instancia** si está inactiva 7 días
  (CPU, red y memoria por debajo del 20 % en el percentil 95). Plan B:
  `scripts/bootstrap.sh` reconstruye todo en otro servidor en menos
  de 30 minutos; no hay datos de usuarios que respaldar (los archivos
  se borran a los 60 minutos).
- **«Sin capacidad» al crear la instancia**: es frecuente en el plan
  gratuito; reintentarlo en otra hora o zona (ver
  `docs/DESPLIEGUE_GRATIS.md`).
- **Capacidad**: con 2 OCPU la meta realista es una cola justa, no
  velocidad extrema. Word de 50 páginas tarda 11,25 s; el OCR es lo
  más pesado y está limitado a 20 páginas por trabajo.
- **PDF que no se convierten bien**: gráficos vectoriales dentro de
  tablas, fuentes raras sin mapa de caracteres, formularios XFA
  (error claro en español), texto rotado 180° en PowerPoint, escaneos
  borrosos o manuscritos (ver `docs/LIMITES.md`). En esos casos la
  aplicación avisa al usuario en vez de entregar un resultado malo.
- **Render en Microsoft Word**: el arreglo del QR se verificó solo con
  LibreOffice; Word debería respetar igual el `tblGrid` fijo, pero no
  se comprobó en Word.
- **Rama Redis del almacén de nonce**: sin Redis en esta VM; probada
  solo la ruta de disco.
- **Privacidad**: el correo de contacto de `docs/PRIVACIDAD.md` es un
  marcador (`privacidad@tu-dominio.com`) que el dueño debe reemplazar
  antes de publicar la política.
- **Turnstile**: verificado gratis el 26 nov 2026 (0 $/mes, sin
  tarjeta), pero solo documentado, no implementado; antes de activarlo
  hay que re-verificar el precio.

## 6. Lo que no se pudo hacer o verificar y por qué
- **Build Docker amd64/arm64**: sin Docker en esta VM. Queda para la
  CI de GitHub (trabajos `docker-build` y `docker-build-arm64`).
- **CI en GitHub**: no ejecutada aquí; el push y la comprobación en
  verde los hace el dueño tras esta ronda.
- **Prueba de carga en Oracle**: la carga medida es de esta VM en modo
  inline, no de Oracle con Redis + workers. Hay que repetirla en la
  instancia Oracle.
- **Flujo real en Vercel** (navegador → `upload-token.js` → backend
  directo, con CORS): solo verificado con `node --check` y pruebas de
  API; falta desplegar con `UPLOAD_SECRET` y probarlo en el navegador.
- **Render en Microsoft Word**: solo LibreOffice (ver §5).
- **Rama Redis del nonce**: sin Redis aquí.
- **`shellcheck`**: no existe en esta VM; `bootstrap.sh` solo se
  validó con `bash -n`.
- **Historial de git**: no había `.git` local; no se pudo revisar el
  historial (ver §4.6).
- **Ghostscript instalado en la imagen Docker**: no se pudo comprobar
  sin construir la imagen; la guía indica el comando para verificarlo
  en el servidor.
- **Despliegue real en Oracle**: no hay cuenta ni instancia; la guía
  está escrita con la documentación oficial, no probada de principio
  a fin aquí.
