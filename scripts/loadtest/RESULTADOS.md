# Resultados de la prueba de carga — 26 nov 2026

> **Estos números son de ESTA VM y NO de Oracle.** No se extrapolan a
> Oracle Always Free (2 OCPU ARM / 12 GB) sin decirlo: la sección
> «Recomendaciones para Oracle» marca explícitamente lo extrapolado.
> Tampoco son números de producción: la prueba corrió en **modo inline**
> (sin Redis ni workers Celery), que no es el modo de despliegue.

## Entorno exacto de la prueba

| Dato | Valor |
|---|---|
| VM | 4 vCPU nominales, **CPU compartida con cuota de 1,5** (según el runtime), 7,7 GB RAM, x86_64 |
| Disco | `/health` reportó solo **228–290 MB libres** en el volumen de trabajos durante las pruebas (disco de la VM casi lleno; posible factor de distorsión, no se pudo evitar) |
| Docker | **No instalado** (`docker: command not found`) |
| Redis | **No instalado ni en ejecución** |
| Modo API | Inline (`REDIS_URL=` vacío, `STORAGE_DIR=/tmp/carga-jobs`, `uvicorn --workers 1`, puerto 8000) |
| Locust | 2.47.0 (de `requirements-dev.txt`, en `.venv`) |
| Fecha/hora | 26 nov 2026, ~04:01–04:10 America/Guayaquil |
| Variables de la prueba | `RATE_LIMIT_PER_HOUR=100000`, `MAX_QUEUE_JOBS=100000` (pruebas de capacidad) o `5` (prueba de protección), `API_KEY=` vacía |

## Corrección de los fixtures (hallazgo)

El `locustfile.py` anterior usaba como «10 páginas»
`tests/fixtures/estado_cuenta_multipagina.pdf` (**3 páginas reales**) y
como «50 páginas» `estado_ingresos_octubre_2026.pdf` (**1 página real**),
verificado con PyMuPDF. Corregido: `scripts/loadtest/locustfile.py`
genera ahora al arrancar PDFs reales de 10 y 50 páginas repitiendo la
página de `tests/fixtures/factura.pdf` con PyMuPDF, en
`scripts/loadtest/generated/carga_10p.pdf` (10 págs., 6,1 KB) y
`carga_50p.pdf` (50 págs., 25,0 KB); si el conteo no es el esperado, el
script falla en arranque en vez de medir con el PDF equivocado. Los
PDFs generados están ignorados por git (`.gitignore`). Son páginas con
texto nativo (sin OCR): la prueba mide conversión de texto, no OCR de
escaneos. Además cada conversión completa registra un evento propio
`E2E / convert_e2e` (subida → estado done → descarga) para leer el
tiempo de extremo a extremo.

## Línea base: una conversión, un usuario (modo inline)

| Conversión | POST | Extremo a extremo | Descarga |
|---|---|---|---|
| factura 1 pág. → Excel | 0,08 s | **0,30 s** | 5,8 KB |
| 10 págs. → Excel | 0,00 s | **0,44 s** | 17,0 KB |
| 50 págs. → Excel | 0,00 s | **1,30 s** | 66,7 KB |
| 50 págs. → Word | 0,00 s | **11,25 s** | 44,9 KB |

El POST solo encola (responde 202). **Word es el destino más caro**:
50 páginas a Word tardan ~9× más que a Excel (pdf2docx). El OCR no se
midió aquí (los PDFs de carga tienen texto nativo); un escaneo real con
OCR es más lento y está acotado por `MAX_OCR_PAGES=20`.

## Humo: 10 usuarios, 1 minuto (modo inline)

Comando: `locust -f scripts/loadtest/locustfile.py --headless -u 10 -r 2
-t 1m --host http://127.0.0.1:8000 --csv scripts/loadtest/resultados/humo`

| Métrica | Valor |
|---|---|
| POST /api/v1/convert | 83 peticiones, **0 fallos**, mediana 100 ms, p95 2,6 s, p99 3,5 s, máx. 3,5 s |
| E2E (subida → descarga) | 73 conversiones, **0 fallos**, mediana 3,1 s, p95 11,0 s, p99 23,0 s, máx. 22,7 s |
| Consultas de estado / descargas | 236 / 73, 0 fallos |
| Total | 465 peticiones, **0 fallos** |
| RSS de uvicorn | ~114 MB en reposo → **347–388 MB** durante el humo |

## Carga: 200 usuarios, rampa 10/s, 2 minutos (modo inline)

Comando: `locust -f scripts/loadtest/locustfile.py --headless -u 200
-r 10 -t 2m --host http://127.0.0.1:8000 --csv
scripts/loadtest/resultados/carga200`

| Métrica (lo que vio Locust) | Valor |
|---|---|
| POST /api/v1/convert | 169 completadas, **0 fallos**, mediana 35 s, p95 99 s, p99 104 s, máx. 105,4 s |
| E2E (subida → descarga) | 34 completadas, **0 fallos**, mediana 40 s, p95 103 s, p99 114 s, máx. 113,9 s |
| Consultas de estado / descargas | 291 / 34, 0 fallos |
| Total | 528 peticiones, **0 fallos** (ni 429, ni 5xx, ni timeouts) |

Lo que vio el servidor (reconteo de `/tmp/carga-jobs`):

- **234 trabajos creados** en la ventana de la prueba, 65 más que los
  169 POST que Locust contó como completados: con respuestas de POST de
  hasta 105 s, esos 65 trabajos ya estaban creados en el servidor pero
  su respuesta 202 aún estaba en vuelo cuando Locust cortó el
  temporizador de 2 min. **0 trabajos terminaron en error.**
- Trabajos terminados por minuto (servidor): ~44, ~43 y ~42 en los
  minutos centrales → **~43 conversiones/min sostenidas en modo inline
  en esta VM** (no es la cifra de producción con workers; ver abajo).
- Latencia creado → terminado (incluye espera en cola; solo trabajos
  terminados): factura 1 pág. n=163, mediana 17,5 s, p95 103,8 s;
  10 págs. n=97, mediana 42,8 s, p95 152,9 s; 50 págs. n=32, mediana
  12,0 s, p95 89,7 s (n parcial y con sesgo: solo los que terminaron).
- La cola drenó sola tras la prueba: 292 trabajos done a los ~4 min
  del fin, 307 done + 14 en proceso a los ~5 min; el proceso uvicorn
  terminó solo cuando acabó el drenaje. La API siguió respondiendo
  `/health` con `ok: true` durante y después de la prueba.

### CPU y memoria observados (uvicorn, proceso único)

Muestreo cada 5 s con `ps` (`/tmp/carga-recursos2.log`; no hay
`/usr/bin/time` en esta VM):

| Métrica | Valor |
|---|---|
| CPU | mediana **51 % de un núcleo**, máx. 58 % (VM con cuota compartida; el resto de CPU lo consumen otros procesos de la VM) |
| RSS | 114 MB en reposo → 448 MB mediana → **805 MB máx. durante la prueba, 1,03 GB a los ~2 min del fin y 1,20 GB al final del drenaje** |

Dos hallazgos importantes:

1. **En modo inline las conversiones no son secuenciales**: Starlette
   ejecuta las `BackgroundTasks` síncronas en un pool de hilos (límite
   40 por defecto), así que hasta 40 conversiones corrían a la vez en
   un solo proceso, limitadas por la GIL y la CPU. Por eso el POST
   (que solo encola) llegó a tardar 35 s de mediana: el hilo del loop
   de eventos apenas consigue la GIL entre 40 hilos haciendo trabajo
   pesado de CPU. **El modo inline no es apto para carga**; en
   producción la conversión va a workers Celery, donde la
   concurrencia es explícita (`--concurrency=2`).
2. **La RSS creció de forma monótona y no bajó al drenar la cola**
   (114 MB → 1,2 GB). Es compatible con arenas de Python no devueltas
   al SO y con 40 conversiones concurrentes reteniendo documentos, no
   se demostró una fuga por trabajo. Por eso se mantiene
   `max-tasks-per-child=50` en el worker (recicla el proceso cada 50
   trabajos) y el límite de memoria por worker en 1g (ver
   `docker-compose.yml`).

## Protección: tope de cola con MAX_QUEUE_JOBS=5

API reiniciada con `MAX_QUEUE_JOBS=5` (mismo resto de variables) y
`locust --headless -u 20 -r 5 -t 1m --csv
scripts/loadtest/resultados/proteccion`:

| Métrica | Valor |
|---|---|
| POST /api/v1/convert | 327 intentos, **285 rechazados con 503 (87 %)**, 42 aceptados |
| E2E | 36 completadas, 0 fallos, mediana 6,4 s, p95 18,0 s |
| Total | 574 peticiones; los 285 fallos son todos 503 esperados (`CatchResponseError: convert devolvió 503`) |

El tope de cola funciona bajo carga: con la cola llena la API
rechaza rápido (mediana de POST 290 ms) con el mensaje «Estamos con
mucha demanda, intenta en unos minutos», sin consumir el token de
subida y sin aceptar trabajo que no puede atender. Con la cola corta,
las conversiones aceptadas terminan mucho antes (E2E mediana 6,4 s
frente a 40 s en la prueba de 200).

## Anti-abuso: Cloudflare Turnstile (opcional, no implementado)

Verificado el 26 nov 2026 en la página oficial de Cloudflare
(`cloudflare.com/products/turnstile`): **Turnstile Free cuesta 0 $/mes,
con retos ilimitados, hasta 20 widgets por cuenta y sin tarjeta de
crédito**; solo exige una cuenta gratuita de Cloudflare (el sitio no
tiene que usar el DNS ni el proxy de Cloudflare). No se implementa
ahora: el límite por IP (60/hora) y el tope de cola (503) ya cubren el
abuso básico. Si el abuso persiste, el camino documentado es: añadir el
widget de Turnstile en `web-example/` y verificar el token en el
servidor contra
`https://challenges.cloudflare.com/turnstile/v0/siteverify` antes de
aceptar el trabajo (claves `TURNSTILE_SITE_KEY` /
`TURNSTILE_SECRET_KEY`). Hay un comentario con este resumen en
`app/main.py`. Antes de activarlo, conviene re-verificar el precio en
la página oficial, porque los planes gratuitos cambian.

## Conclusiones de capacidad y recomendaciones

### Valores recomendados (para fusionar en `docs/LIMITES.md` / `docs/METRICAS.md`)

| Parámetro | Recomendado | Justificación (medido o extrapolado) |
|---|---|---|
| Workers / `--concurrency` en Oracle 2 OCPU / 12 GB | **2 workers × concurrency 2 = 4 conversiones a la vez** (`docker compose up -d --scale worker=2`) | **Extrapolación.** La conversión es CPU y la GIL impide aprovechar más hilos por worker. Medido en inline: 40 hilos a la vez saturan la GIL y disparan la latencia (POST p95 99 s). Con 4 conversiones a la vez y 1–3 s por conversión típica (Excel, texto), el caudal teórico es ~80–240/min; con Word de 50 págs. (11,25 s medidos) el peor caso baja a ~22/min para esa mezcla. **Hay que medirlo en Oracle**: esta VM no es equivalente (x86_64, CPU compartida, sin Redis). |
| `MAX_PAGES` | **200 (sin cambio)** | Sin cambio: el límite ya existe y ningún fixture ni prueba lo supera; la prueba de 50 págs. es cómoda. |
| `MAX_UPLOAD_MB` | **50 (sin cambio)** | Sin cambio: la prueba usó PDFs de hasta 25 KB; el caso de 40 MB ya está cubierto por `test_upload_token.py`. No hay datos nuevos para subirlo o bajarlo. |
| Límite por IP/hora (`RATE_LIMIT_PER_HOUR`) | **60 (sin cambio)** | Sin cambio: con 200 usuarios desde una sola IP, el límite de 60/hora habría devuelto 429 a casi todo (ya se vio en el humo anterior del README); para carga se subió a 100000 solo en la prueba. En producción protege del abuso; el tope de cola absorbe los picos legítimos. |
| `TASK_TIME_LIMIT` | **600 s (sin cambio)** | Sin cambio: el worker ya lo respeta (`app/worker.py` lo pasa a Celery como `task_time_limit`). La conversión más lenta medida (Word 50 págs., 11,25 s) está 50× por debajo; el límite solo caza trabajos colgados (p. ej. OCR de 20 págs. escaneadas). |
| Tope de cola (`MAX_QUEUE_JOBS`) | **50 (sin cambio)** | Medido: con 5, el 87 % de intentos se rechaza con 503 y lo aceptado termina rápido (E2E mediana 6,4 s). Con 4 workers, 50 en cola ≈ 12× la concurrencia y drena en <1 min al caudal medido (~43/min en inline; en workers será mayor). 50 es el equilibrio entre no rechazar picos legítimos y no dejar esperando minutos. |
| `MAX_OCR_PAGES` | **20 (nuevo, implementado)** | El OCR es el paso más caro (Tesseract a 300 dpi + confianza por palabra). Por encima de 20 págs. escaneadas el trabajo termina en error con mensaje claro, en vez de ocupar un worker minutos. Implementado en `app/processing.py` con la misma condición del convertidor (imagen ≥80 % de la página y <20 caracteres nativos). |
| Memoria por worker | **1g** (antes 2g) | Medido: 40 conversiones concurrentes en un proceso llegaron a 1,2 GB (~30 MB por conversión de media); con concurrency=2 el pico realista es 200–400 MB, así que 1g deja 2–3× de margen. API 1g, redis 256m, beat 256m: total de topes ~2,5g en 12 GB. |
| `max-tasks-per-child` | **50 (sin cambio)** | Medido: la RSS creció de forma monótona sin bajar al drenar; reciclar cada 50 trabajos acota esa acumulación. |

### Lo que estos números NO dicen

- **No miden Oracle.** La VM de la prueba es x86_64 con CPU compartida
  (cuota 1,5) y 7,7 GB; Oracle Always Free es ARM Ampere (2 OCPU, 12
  GB). El rendimiento por núcleo ARM puede diferir; la única forma de
  saberlo es repetir esta misma prueba en la instancia Oracle con
  Redis + workers Celery.
- **No miden OCR ni PDFs escaneados grandes.** Los PDFs de carga
  tienen texto nativo. Un escaneo de 20 págs. con OCR será mucho más
  lento que los 1,3 s de 50 págs. a Excel medidos aquí.
- **No miden Redis/Celery.** Sin Redis no hay cola real entre API y
  workers; el caudal de ~43/min es del modo inline, no del despliegue.
- **Disco casi lleno** (228–290 MB libres) durante las pruebas: no se
  observó un fallo por disco, pero es un factor de distorsión que no se
  pudo eliminar en esta VM.

## Archivos de esta prueba

- `scripts/loadtest/locustfile.py` (corregido: PDFs reales de 10/50 págs. + métrica E2E)
- `scripts/loadtest/resultados/humo_stats.csv` (10 usuarios, 1 min)
- `scripts/loadtest/resultados/carga200_stats.csv` (200 usuarios, 2 min)
- `scripts/loadtest/resultados/proteccion_stats.csv` (20 usuarios, 1 min, `MAX_QUEUE_JOBS=5`)
- Los CSV están ignorados por git (`.gitignore`: `resultados/`).
- Para repetir: arrancar la API en inline con
  `STORAGE_DIR=<tmp> REDIS_URL= RATE_LIMIT_PER_HOUR=100000
  MAX_QUEUE_JOBS=100000 .venv/bin/uvicorn app.main:app --host 127.0.0.1
  --port 8000 --workers 1` y luego
  `locust -f scripts/loadtest/locustfile.py --headless -u 200 -r 10 -t 2m
  --host http://127.0.0.1:8000 --csv scripts/loadtest/resultados/carga200`
