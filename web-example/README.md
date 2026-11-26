# Frontend de ejemplo (copiar al proyecto de Vercel)

HTML + JavaScript puro, sin frameworks: `index.html`, `app.js`, `styles.css`.

## Flujo nuevo: subida directa al backend (recomendado)

El PDF ya **no** pasa por Vercel (el plan Hobby limita el cuerpo de las
funciones serverless a 4,5 MB). El flujo es:

1. El navegador pide un token de subida a la función serverless
   `POST /api/upload-token` (`api/upload-token.js`).
2. Esa función, en el servidor, pide `POST /api/v1/upload-token` al backend
   con la API key (`CONVERTER_API_KEY`) y devuelve el token al navegador.
   La clave **nunca** llega al navegador.
3. El navegador sube el PDF **directo** al backend con
   `POST {CONVERTER_BACKEND_URL}/api/v1/upload` y el header
   `X-Upload-Token: <token>`. El token vale 5 minutos, permite hasta
   `MAX_UPLOAD_MB` (50 MB) y solo se puede usar una vez.
4. El navegador consulta el estado directo al backend
   (`GET {CONVERTER_BACKEND_URL}/api/v1/jobs/{id}`) y descarga también
   directo al backend (enlace firmado, ver `api/download.js`).
5. Si no se puede obtener el token (p. ej. el backend aún no tiene subida
   directa), el frontend usa como respaldo el flujo antiguo por
   `/api/convert` (ver abajo).

## Uso local (contra el backend en local)
```bash
STORAGE_DIR=./data REDIS_URL= uvicorn app.main:app --reload   # desde la raíz del repo
python3 -m http.server 8080 --directory web-example
# abre http://localhost:8080 (el frontend llama a /api/* del mismo origen)
```

## En Vercel
1. Copia `index.html`, `app.js` y `styles.css` a la raíz del proyecto web y
   la carpeta `api/` (`convert.js`, `jobs.js`, `download.js`,
   `upload-token.js`) a `api/` del proyecto.
2. En Vercel → Settings → Environment Variables:
   - `CONVERTER_BACKEND_URL`: URL pública del backend, p. ej. `https://convertidor.tu-dominio.com`
   - `CONVERTER_API_KEY`: la misma clave que `API_KEY` del backend (si está configurada).
3. En el backend, configura además:
   - `UPLOAD_SECRET`: secreto para firmar los tokens de subida (cualquier
     valor largo y aleatorio; distinto de `API_KEY` y de `DOWNLOAD_SECRET`).
   - `ALLOWED_ORIGINS`: debe incluir el origen del sitio en Vercel
     (p. ej. `https://tu-sitio.vercel.app`), porque el navegador habla
     directo con el backend y el navegador aplica CORS.
4. Despliega. El navegador nunca ve la clave: solo la función serverless la añade.

## Flujo antiguo (respaldo, solo hasta 4,5 MB)

`app.js` usa `POST /api/convert` (`api/convert.js`), que reenvía el PDF al
backend con la API key, y consulta el estado por `api/jobs.js`. En el plan
Hobby de Vercel este flujo falla con 413 por encima de 4,5 MB: para PDFs
grandes usa el flujo nuevo de subida directa (arriba) o el plan Pro.

## Notas
- El frontend consulta el estado cada segundo y muestra el informe de
  calidad (`quality.text_coverage`, `quality.number_coverage` y
  `missing_sample`) cuando la conversión termina.
- El token de subida caduca a los 5 minutos y solo vale para una subida: si
  caduca o ya se usó, el backend responde 401 y el frontend debe pedir
  otro token (p. ej. volviendo a pulsar «Convertir»).
