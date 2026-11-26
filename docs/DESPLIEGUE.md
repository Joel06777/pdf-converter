# Despliegue

## Opción A — VPS con Docker Compose + Caddy (recomendado)

Requisitos: VPS con 2 vCPU / 4 GB RAM (para ~200 conversiones concurrentes en
pico, sube a 4 vCPU / 8 GB y `worker=8`), Docker, un dominio apuntando al VPS.

1. Clona el repositorio y crea el entorno:
```bash
git clone https://github.com/TU-USUARIO/pdf-converter.git
cd pdf-converter
cp .env.example .env
```
2. Edita `.env`:
```
ALLOWED_ORIGINS=https://tu-sitio.vercel.app
API_KEY=<redacted>
DOWNLOAD_SECRET=<redacted>
RATE_LIMIT_PER_HOUR=60
```
   Genera los secretos con `openssl rand -hex 32`.
3. Levanta el servicio:
```bash
docker compose up -d --build
docker compose up -d --scale worker=4   # más workers = más conversiones en paralelo
```
4. HTTPS con Caddy (en el mismo VPS, puerto 80/443):
```caddyfile
convertidor.tu-dominio.com {
    reverse_proxy localhost:8000
}
```
```bash
docker run -d --name caddy --network host -v $PWD/Caddyfile:/etc/caddy/Caddyfile caddy:2
```
   Caddy emite el certificado Let's Encrypt solo. Alternativa con Nginx: proxy
   a `localhost:8000` + `certbot --nginx`.
5. Verifica:
```bash
curl https://convertidor.tu-dominio.com/health
curl https://convertidor.tu-dominio.com/metrics
```
6. En Vercel, pon `CONVERTER_BACKEND_URL=https://convertidor.tu-dominio.com`
   y `CONVERTER_API_KEY` con el mismo valor de `API_KEY`.

### Escalar
- Cada worker convierte un archivo a la vez (`concurrency=2` en
  docker-compose.yml). Para 200 conversiones concurrentes en pico, calcula
  ~1 worker por cada 2–4 conversiones simultáneas según el tamaño de los PDF
  (un PDF de 50 páginas con OCR tarda ~5 s por página en una CPU).
- La API es sin estado (el estado vive en el volumen `/data/jobs`): puedes
  tener varias réplicas con `docker compose up --scale api=2` detrás de Caddy.
- Limpieza: el worker `beat` borra trabajos de más de 60 min cada 5 min.

## Opción B — Google Cloud Run
```bash
gcloud run deploy pdf-converter \
  --source . \
  --region us-central1 \
  --set-env-vars REDIS_URL=redis://<redacted>,STORAGE_DIR=/tmp/jobs \
  --memory 2Gi --cpu 2 --concurrency 2 --timeout 600
```
Necesitas Redis externo (Memorystore) y almacenamiento compartido para
`/data/jobs` si usas más de una instancia. Para un despliegue simple de una
sola instancia, `REDIS_URL=` (modo inline) funciona sin Redis.

## Opción C — Fly.io
```bash
fly launch --no-deploy
fly redis create
fly secrets set API_KEY=<redacted> DOWNLOAD_SECRET=<redacted> REDIS_URL=<redacted>
fly deploy
fly scale count worker=4
```

## Variables de entorno (ver .env.example)
| Variable | Defecto | Descripción |
|---|---|---|
| STORAGE_DIR | /data/jobs | trabajos y resultados (se borran a los 60 min) |
| REDIS_URL | (vacío = inline) | cola Celery; vacío = conversión en la API |
| MAX_UPLOAD_MB | 50 | tamaño máximo del PDF |
| MAX_PAGES | 200 | páginas máximas |
| JOB_TTL_MINUTES | 60 | vida del resultado |
| ALLOWED_ORIGINS | * | CORS: pon el dominio de Vercel |
| API_KEY | (vacío = sin clave) | clave en `X-API-Key` |
| DOWNLOAD_SECRET | (vacío = enlace directo) | firma HMAC de descargas (15 min) |
| RATE_LIMIT_PER_HOUR | 60 | conversiones por IP y hora |
| OCR_LANG | spa+eng | idiomas de Tesseract |
| TASK_TIME_LIMIT | 600 | segundos máximos por trabajo |
