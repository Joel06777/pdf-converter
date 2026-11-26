// Función serverless de Vercel: reenvía la subida al backend de conversión.
//
// La clave de API vive SOLO en la variable de entorno CONVERTER_API_KEY de
// Vercel (nunca en el navegador ni en el repositorio). El backend está en
// CONVERTER_BACKEND_URL, p. ej. https://convertidor.tu-dominio.com
// Requiere Node 18+ (fetch y FormData globales).

const BACKEND = process.env.CONVERTER_BACKEND_URL;
const API_KEY = process.env.CONVERTER_API_KEY;

export const config = {
  api: { bodyParser: false }, // el cuerpo es multipart: se reenvía tal cual
};

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ detail: "Método no permitido." });
  }
  if (!BACKEND) {
    return res.status(500).json({ detail: "Falta configurar CONVERTER_BACKEND_URL en Vercel." });
  }
  try {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    const upstream = await fetch(`${BACKEND}/api/v1/convert`, {
      method: "POST",
      headers: {
        "Content-Type": req.headers["content-type"] || "multipart/form-data",
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      },
      body,
      // Vercel: el límite de cuerpo de las funciones serverless es 4,5 MB en
      // el plan Hobby. Para PDFs de hasta 50 MB usa el plan Pro o sube el
      // archivo directo al backend con URL firmada (ver docs/DESPLIEGUE.md).
      duplex: "half",
    });
    const text = await upstream.text();
    res.status(upstream.status);
    res.setHeader("Content-Type", upstream.headers.get("content-type") || "application/json");
    return res.send(text);
  } catch (err) {
    console.error("convert proxy error:", err);
    return res.status(502).json({ detail: "No se pudo contactar al servicio de conversión." });
  }
}
