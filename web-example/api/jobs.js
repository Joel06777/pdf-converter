// Función serverless de Vercel: consulta el estado de un trabajo (y la
// descarga, redirigiendo al enlace firmado del backend). Sin clave en el
// navegador: la clave solo se usa en /api/convert; el estado es público por
// job_id (un id aleatorio de 32 caracteres hexadecimales).

const BACKEND = process.env.CONVERTER_BACKEND_URL;

export default async function handler(req, res) {
  if (!BACKEND) {
    return res.status(500).json({ detail: "Falta configurar CONVERTER_BACKEND_URL en Vercel." });
  }
  const id = String(req.query.id || "");
  if (!/^[a-f0-9]{32}$/.test(id)) {
    return res.status(404).json({ detail: "Trabajo no encontrado." });
  }
  try {
    const upstream = await fetch(`${BACKEND}/api/v1/jobs/${id}`);
    const job = await upstream.json();
    if (!upstream.ok) return res.status(upstream.status).json(job);
    // El enlace de descarga del backend es relativo: se reescribe a /api/download.
    if (job.download_url) {
      job.download_url = `/api/download?id=${id}`;
    }
    return res.status(200).json(job);
  } catch (err) {
    console.error("jobs proxy error:", err);
    return res.status(502).json({ detail: "No se pudo contactar al servicio de conversión." });
  }
}
