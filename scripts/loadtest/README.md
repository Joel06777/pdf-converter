# Prueba de carga

> Resultados reales (26 nov 2026, 200 usuarios, modo inline):
> ver [`RESULTADOS.md`](RESULTADOS.md). Resumen: 200 usuarios, 2 min —
> POST p95 99 s, E2E p95 103 s, 0 fallos, ~43 conversiones/min en modo
> inline en una VM x86_64 con CPU compartida (NO es Oracle). El
> `locustfile.py` ya genera PDFs reales de 10 y 50 páginas (antes los
> fixtures de «10» y «50» tenían 3 y 1 páginas).

## Ejecutar (contra un backend en local o en el VPS)
```bash
pip install -r requirements-dev.txt   # incluye locust
# 1) levanta el backend (con workers, como en producción):
docker compose up -d --build --scale worker=4
# 2) prueba de humo (10 usuarios, 1 minuto):
locust -f scripts/loadtest/locustfile.py --headless -u 10 -r 2 -t 1m --host http://localhost:8000
# 3) prueba completa (200 usuarios concurrentes):
locust -f scripts/loadtest/locustfile.py --headless -u 200 -r 10 -t 10m --host https://convertidor.tu-dominio.com --csv resultados/carga
```
Locust imprime al final los tiempos p50/p95/p99 por endpoint y el % de fallos.
Los CSV quedan en `resultados/carga_stats.csv`.

## Resultados
**No se ejecutó la prueba de 200 usuarios en este entorno** (una sola VM de
desarrollo, sin el despliegue con workers). No se inventan cifras: cuando se
ejecute contra el VPS, anota aquí los resultados reales con esta plantilla:

| Escenario | Usuarios | p50 | p95 | p99 | Fallos | Workers |
|---|---|---|---|---|---|---|
| 200 concurrentes (1/10/50 págs.) | 200 | — | — | — | — | — |

## Humo ejecutado en este entorno
Prueba de humo real (26 nov 2026): 5 usuarios, 30 s, contra la API en modo
inline (sin Redis ni workers, `uvicorn` local), con `RATE_LIMIT_PER_HOUR=100000`
(ver el hallazgo siguiente). Sirve solo para validar que el script funciona,
no como medida de capacidad:

| Métrica | Valor medido |
|---|---|
| POST /api/v1/convert (33 peticiones) | 0 fallos · p50 5 ms · p95 110 ms · p99 150 ms |
| Agregado (137 peticiones: subir + consultar + descargar) | 0 fallos · p50 7 ms · p95 83 ms · p99 170 ms |

Ojo: `POST /convert` solo encola (responde 202); la conversión es asíncrona.
Estas latencias son de la API, no el tiempo de conversión de extremo a extremo
(ver `docs/METRICAS.md`: 0,05–5,6 s por archivo según tamaño y OCR).

**Hallazgo:** con el límite por defecto (`RATE_LIMIT_PER_HOUR=60`), la mitad
de las peticiones de Locust devolvieron 429, porque todos los usuarios
comparten la misma IP. Para pruebas de carga, sube el límite
(`RATE_LIMIT_PER_HOUR=100000`) o pon Locust detrás de varias IPs.
