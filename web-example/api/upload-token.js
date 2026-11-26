// Función serverless de Vercel: pide al backend un token de subida firmado.
//
// La clave de API vive SOLO en la variable de entorno CONVERTER_API_KEY de
// Vercel (nunca en el navegador ni en el repositorio). El navegador usa el
// token devuelto para subir el PDF DIRECTO al backend, sin pasar por esta
// función: así no aplica el límite de 4,5 MB del plan Hobby de Vercel y se
// pueden subir PDFs de hasta 50 MB.
// Requiere Node 18+ (fetch global).

const BACKEND = process.env.CONVERTER_BACKEND_URL;
const API_KEY = process.env.CONVERTER_API_KEY;

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ detail: "Método no permitido." });
  }
  if (!BACKEND) {
    return res.status(500).json({ detail: "Falta configurar CONVERTER_BACKEND_URL en Vercel." });
  }
  try {
    const upstream = await fetch(`${BACKEND}/api/v1/upload-token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      },
      body: JSON.stringify({}),
    });
    const text = await upstream.text();
    let payload = null;
    try { payload = JSON.parse(text); } catch { /* respuesta no JSON */ }
    if (!upstream.ok) {
      return res.status(upstream.status).json(payload || { detail: "No se pudo obtener el token de subida." });
    }
    const backend = BACKEND.replace(/\/$/, "");
    // upload_url absoluto: el navegador sube directo al backend con el token.
    // backend_url se devuelve para que el navegador consulte el estado y
    // descargue también directo al backend (sin pasar por Vercel).
    return res.status(200).json({
      upload_token: payload.upload_token,
      expires_in: payload.expires_in,
      max_mb: payload.max_mb,
      upload_url: `${backend}/api/v1/upload`,
      backend_url: backend,
    });
  } catch (err) {
    console.error("upload-token proxy error:", err);
    return res.status(502).json({ detail: "No se pudo contactar al servicio de conversión." });
  }
}
