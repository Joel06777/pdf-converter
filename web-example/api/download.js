// Descarga: pide al backend el estado (que incluye el enlace firmado) y
// redirige al navegador a ese enlace. El token firmado nunca pasa por el
// JavaScript del frontend: vive solo en la redirección del servidor.

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
    if (!upstream.ok || !job.download_url) {
      return res.status(upstream.status || 404).json(job);
    }
    return res.redirect(302, `${BACKEND}${job.download_url}`);
  } catch (err) {
    console.error("download proxy error:", err);
    return res.status(502).json({ detail: "No se pudo contactar al servicio de conversión." });
  }
}
