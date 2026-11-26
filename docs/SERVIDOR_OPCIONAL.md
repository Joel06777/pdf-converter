# Servidor opcional (respaldo): FastAPI + Celery + Redis + Docker

> **Por defecto, no hay servidor.** La web (`web/`) convierte en el
> navegador y el archivo no sale del dispositivo. Este servidor existe
> solo como **respaldo opcional**, para los casos que el navegador no
> resuelva. **No lo actives salvo que lo necesites**: cada activación
> añade un servidor que mantener, una clave que cuidar y datos que
> viajan por internet. La web funciona sin él.
>
> **Nada de este documento borra ni cambia el servidor:** el código de
> `app/`, `Dockerfile`, `docker-compose.yml` y `scripts/bootstrap.sh`
> sigue exactamente igual. Este documento solo explica qué es, cuándo
> usarlo y cómo activarlo.

## Cuándo hace falta (y cuándo no)

| Caso | ¿Hace falta el servidor? |
|---|---|
| PDF normal con texto o tablas, en cualquier destino | **No.** Lo hace el navegador. |
| PDF escaneado (OCR) de pocas páginas | **No.** El motor del navegador tiene OCR. |
| Word de **texto corrido complejo** (varias columnas, tablas y texto mezclados, documentos largos) | **Sí, puede ayudar.** El servidor usa la ruta `flow` (pdf2docx) y la reconstrucción de tablas de Python, más potente que la del navegador. |
| Escaneos **enormes** (decenas de páginas escaneadas) | **Sí.** El servidor limita el OCR a 20 páginas por trabajo (`MAX_OCR_PAGES=20`) y tiene más memoria que un celular. |
| PDF de más de 200 páginas o más de 50 MB | **Sí, si se suben los límites** en el servidor (ver abajo). El navegador recomienda como máximo 200 páginas / 50 MB en PC y menos en celular. |
| PDF con contraseña | **No, en ningún caso.** Ni el navegador ni el servidor intentan adivinar contraseñas. Quítale la contraseña antes. |
| Formularios XFA | **No.** Tampoco el servidor los convierte. |

## Qué es el servidor (lo que ya existe en este repositorio)

- **API con FastAPI** (`app/main.py`): recibe el PDF, lo pone en cola
  y devuelve el resultado. Versión de la API: `1.1.0`.
- **Cola con Celery + Redis** (`app/worker.py`, `docker-compose.yml`):
  los trabajos se procesan en segundo plano, en workers separados.
  Sin Redis, la API funciona en «modo inline» (convierte en el mismo
  proceso; solo para desarrollo, no para carga).
- **Motor en Python** (`app/converters/`): PyMuPDF para leer el PDF,
  Tesseract + OCRmyPDF para escaneados, openpyxl / python-docx /
  python-pptx para escribir los resultados, pdf2docx para el texto
  corrido de Word.
- **Docker** (`Dockerfile`, `docker-compose.yml`): todo empaquetado
  en contenedores. Servicios: `api`, `worker` (2 por defecto en
  Oracle Always Free), `redis` y `beat` (limpiador).
- **Límites por defecto** (`app/config.py`): 50 MB y 200 páginas por
  archivo, 60 conversiones/hora por IP, 20 páginas con OCR por
  trabajo, cola máxima de 50 trabajos (por encima, la API responde
  503 «Estamos con mucha demanda»), resultados borrados a los
  60 minutos.

### Endpoints (los que usa la web si el servidor está activo)

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/health` | Saber si el servidor está vivo (esto es lo que comprueba la web) |
| `POST` | `/api/v1/upload-token` | Pedir un token de subida firmado (lo pide la función de Vercel, nunca el navegador) |
| `POST` | `/api/v1/upload` | Subir el PDF directo al backend con el token (sin límite de 4,5 MB) |
| `POST` | `/api/v1/convert` | Subir el PDF y convertirlo (`target` = `excel`/`word`/`pptx`, `layout` = `pages`/`continuous`) |
| `POST` | `/api/v1/convert-many` | Varios archivos a la vez (máx. 20) |
| `GET` | `/api/v1/jobs/{id}` | Estado y progreso por página, informe de calidad |
| `POST` | `/api/v1/jobs/{id}/cancel` | Cancelar un trabajo |
| `GET` | `/api/v1/jobs/{id}/download` | Descargar el resultado (enlace firmado, caduca a los 15 min) |
| `GET` | `/metrics` | Métricas Prometheus (contadores, sin contenido de documentos) |

Detalle completo en `README.md` y en `docs/DESPLIEGUE.md`.

## Cómo la web detecta si el servidor está disponible

1. En `web/config.js`, el dueño pone la URL pública del servidor en
   `serverUrl` (por defecto está vacío: servidor apagado).
2. Al abrir la página, `web/app.js` llama a `{serverUrl}/health`.
   - Si responde, la página muestra: «Servidor opcional disponible.
     Solo se usará si el motor del navegador no puede con tu PDF, y
     te avisará antes.»
   - Si no responde, muestra: «Servidor opcional no disponible
     ahora. No pasa nada: el convertidor del navegador sigue
     funcionando solo.»
3. **La web nunca envía un archivo al servidor sin avisar antes.**
   Hoy, además, la web todavía no envía nada al servidor por sí
   misma: el flujo de subida directa existe en `web-example/` (con
   funciones serverless de Vercel) y está pendiente de conectarse a
   `web/` cuando el motor del navegador esté listo. Si activas el
   servidor antes de eso, la web seguirá convirtiendo en el navegador
   y el servidor quedará esperando a que se conecte ese flujo.

**Ojo con la seguridad del navegador (CSP):** si activas el
servidor, añade su origen a `connect-src` en `web/vercel.json` y en
la etiqueta `<meta http-equiv="Content-Security-Policy">` de
`web/index.html` (por ejemplo,
`connect-src 'self' https://convertidor.tu-dominio.com`). Si no lo
haces, el navegador bloqueará la llamada al servidor y la página
dirá que no está disponible.

## Cómo activarlo (resumen; detalle en `docs/DESPLIEGUE.md`)

### Opción 1 — Oracle Cloud Always Free (gratis)

La guía paso a paso completa de Oracle (crear la cuenta, la
instancia, DuckDNS, Caddy y HTTPS) estaba en la versión anterior de
`docs/DESPLIEGUE_GRATIS.md`; el camino corto y reproducible es el
script `scripts/bootstrap.sh`, que hace todo lo del servidor en un
solo comando una vez creada la instancia:

```bash
# En el servidor (Ubuntu 24.04), con el repositorio clonado:
bash scripts/bootstrap.sh convertidor-pdf-fabian.duckdns.org
# Con token de DuckDNS (opcional, para actualizar el dominio):
DUCKDNS_TOKEN=<redacted> bash scripts/bootstrap.sh convertidor-pdf-fabian.duckdns.org
```

El script instala Docker, crea el `.env` con claves aleatorias,
crea el `Caddyfile` con tu dominio, levanta el servicio y Caddy
(HTTPS automático con Let's Encrypt). **No toca la consola de
Oracle**: la instancia y los puertos 80/443 hay que abrirlos a mano
en la consola (ver `docs/DESPLIEGUE.md`).

Números del plan Always Free (verificados el 26 nov 2026 en la
documentación oficial de Oracle): 2 OCPU y 12 GB de memoria en
total, 200 GB de disco, 10 TB de salida al mes. Configuración
recomendada: 2 workers × concurrency 2 = 4 conversiones a la vez
(`docker compose up -d --scale worker=2`). **Riesgo que tienes que
conocer:** si el servidor está sin uso 7 días (CPU, red y memoria
por debajo del 20 %), Oracle puede reclamarlo (borrarlo). Un
servicio con visitas normales supera esos umbrales; uno sin ninguna
visita en una semana, no. No uses trucos de «carga falsa» para
parecer activo: varias guías advierten de que es una zona gris en
los términos de Oracle.

### Opción 2 — Cualquier VPS con Docker

Ver `docs/DESPLIEGUE.md` (opción A):

```bash
git clone https://github.com/Joel06777/pdf-converter.git
cd pdf-converter
cp .env.example .env   # edita ALLOWED_ORIGINS, API_KEY, DOWNLOAD_SECRET y UPLOAD_SECRET
docker compose up -d --build --scale worker=2
```

Y un proxy con HTTPS (Caddy o Nginx + certbot) delante del puerto
8000. Verifica con `curl https://tu-servidor/health`.

### Variables que hay que poner (`.env` del servidor)

| Variable | Para qué |
|---|---|
| `ALLOWED_ORIGINS` | El dominio exacto de tu web (p. ej. `https://tu-sitio.vercel.app`). Solo esa web podrá llamar al backend. |
| `API_KEY` | Clave que la función serverless de Vercel usa para pedir tokens. Nunca va en el navegador. |
| `DOWNLOAD_SECRET` | Secreto para firmar los enlaces de descarga (15 min). |
| `UPLOAD_SECRET` | Secreto para firmar los tokens de subida (5 min, un solo uso). Distinto de los otros dos. |
| `MAX_UPLOAD_MB` / `MAX_PAGES` | Límites por archivo (por defecto 50 / 200). |
| `RATE_LIMIT_PER_HOUR` | Conversiones por hora y por IP (por defecto 60). |
| `MAX_QUEUE_JOBS` / `MAX_OCR_PAGES` | Tope de cola (50) y páginas con OCR por trabajo (20). |

Genera cada secreto con `openssl rand -hex 32`. **Nunca subas el
`.env` al repositorio** (ya está en `.gitignore`) ni lo pegues en
ningún chat.

## Privacidad cuando el servidor está activo

Lo que cambia respecto al modo navegador (ver `docs/PRIVACIDAD.md`):

- El PDF **sí sale del dispositivo**: viaja cifrado (HTTPS) al
  servidor y se procesa allí.
- El **PDF original se borra al terminar** la conversión (también si
  da error o si cancelas). El resultado y el trabajo completo se
  **borran a los 60 minutos**. Los enlaces de descarga caducan a los
  15 minutos.
- Los **logs no contienen el contenido de los documentos**: solo
  identificador del trabajo, formato, estado, duración, páginas y
  tipo de error. El nombre del archivo sí queda en el log.
- La IP se guarda solo como contador de uso (60 conversiones/hora),
  con caducidad de 1 hora.
- No se usa ningún servicio externo de conversión: el motor es
  propio y corre en tu servidor.

## Cuándo apagarlo

Si el motor del navegador ya resuelve todos tus casos, apaga el
servidor: es un ordenador menos que mantener, una clave menos que
cuidar y cero datos que viajen. Para apagarlo, borra `serverUrl` de
`web/config.js` y detén los contenedores (`docker compose down`).
La web seguirá funcionando igual.
