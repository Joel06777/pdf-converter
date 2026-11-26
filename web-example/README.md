# Frontend de ejemplo (copiar al proyecto de Vercel)

HTML + JavaScript puro, sin frameworks: `index.html`, `app.js`, `styles.css`.

## Uso local (contra el backend en local)
```bash
STORAGE_DIR=./data REDIS_URL= uvicorn app.main:app --reload   # desde la raíz del repo
python3 -m http.server 8080 --directory web-example
# abre http://localhost:8080 (el frontend llama a /api/* del mismo origen)
```

## En Vercel
1. Copia `index.html`, `app.js` y `styles.css` a la raíz del proyecto web y
   la carpeta `api/` (convert.js, jobs.js, download.js) a `api/` del proyecto.
2. En Vercel → Settings → Environment Variables:
   - `CONVERTER_BACKEND_URL`: URL pública del backend, p. ej. `https://convertidor.tu-dominio.com`
   - `CONVERTER_API_KEY`: la misma clave que `API_KEY` del backend (si está configurada).
3. Despliega. El navegador nunca ve la clave: solo la función serverless la añade.

## Notas
- El plan Hobby de Vercel limita el cuerpo de las funciones serverless a 4,5 MB.
  Para PDFs de hasta 50 MB usa el plan Pro o sube directo al backend (ver
  `docs/DESPLIEGUE.md`).
- El frontend consulta el estado cada segundo en `/api/jobs/{id}` y muestra el
  informe de calidad (`quality.text_coverage`, `quality.number_coverage` y
  `missing_sample`) cuando la conversión termina.
