#!/usr/bin/env node
/* Genera PDFs defectuosos, cifrados y hostiles para probar el motor del
   navegador, SIN dependencias: construye los bytes a mano.
   Uso:  node web/tests/generate-hostile-pdfs.mjs [carpeta de salida]
   Salida por defecto: web/tests/fixtures/
   Los casos y el resultado esperado de cada uno están en hostile-cases.md.
   Estos PDFs NO se suben a ningún sitio: son solo para pruebas locales. */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const outDir = process.argv[2] || join(dirname(fileURLToPath(import.meta.url)), "fixtures");
mkdirSync(outDir, { recursive: true });

/* Construye un PDF mínimo válido con los objetos dados. */
function buildPdf(objects, opts = {}) {
  const parts = ["%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"];
  const offsets = [0];
  let pos = Buffer.byteLength(parts[0]);
  for (let i = 0; i < objects.length; i++) {
    const body = `${i + 1} 0 obj\n${objects[i]}\nendobj\n`;
    offsets.push(pos);
    parts.push(body);
    pos += Buffer.byteLength(body);
  }
  const xrefPos = pos;
  let xref = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let i = 1; i <= objects.length; i++) {
    xref += String(offsets[i]).padStart(10, "0") + " 00000 n \n";
  }
  const trailer = opts.trailer || `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\n`;
  const tail = xref + trailer + `startxref\n${xrefPos}\n%%EOF\n`;
  return Buffer.from(parts.join("") + tail, "latin1");
}

const PAGE = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>`;
const PAGES = `<< /Type /Pages /Kids [3 0 R] /Count 1 >>`;
const CATALOG = `<< /Type /Catalog /Pages 2 0 R >>`;
const CONTENT = `<< /Length 44 >>\nstream\nBT /F1 24 Tf 100 700 Td (Hola) Tj ET\nendstream`;
const FONT = `<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>`;

const cases = {};

/* 1. PDF válido de referencia (control: debe convertir bien). */
cases["01-valido.pdf"] = buildPdf([CATALOG, PAGES, PAGE, CONTENT, FONT]);

/* 2. PDF truncado: faltan el xref, el trailer y el %%EOF. */
cases["02-truncado.pdf"] = Buffer.from(
  "%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n",
  "latin1"
);

/* 3. PDF con contraseña: NO se puede construir a mano (el cifrado real
   exige cifrar los objetos). Se genera aparte con PyMuPDF y se guarda
   en el repositorio; este script NO lo sobrescribe. Para regenerarlo:
     .venv/bin/python -c "import fitz; d=fitz.open('web/tests/fixtures/01-valido.pdf'); d.save('web/tests/fixtures/03-cifrado.pdf', encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='secreta', owner_pw='dueno')"
   Contraseña de usuario: «secreta». */

/* 4. PDF con xref roto (offsets que apuntan a cualquier parte). */
{
  const good = buildPdf([CATALOG, PAGES, PAGE, CONTENT, FONT]).toString("latin1");
  cases["04-xref-roto.pdf"] = Buffer.from(good.replace(/0000000\d{3} 00000 n /g, "0000000001 00000 n "), "latin1");
}

/* 5. PDF con conteo de páginas mentiroso (declara 10.000 páginas, tiene 1). */
cases["05-paginas-mentirosas.pdf"] = buildPdf([
  CATALOG,
  `<< /Type /Pages /Kids [3 0 R] /Count 10000 >>`,
  PAGE, CONTENT, FONT,
]);

/* 6. PDF con formulario XFA (dinámico de Adobe): debe rechazarse con mensaje claro. */
cases["06-xfa.pdf"] = buildPdf([
  `<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [] /XFA [ (preamble) 6 0 R (config) 7 0 R ] >> >>`,
  PAGES, PAGE, CONTENT, FONT,
  `<< /Length 10 >>\nstream\n<xdp:xdp/>\nendstream`,
  `<< /Length 10 >>\nstream\n<xdp:xdp/>\nendstream`,
]);

/* 7. PDF con un flujo que dice ser larguísimo (Length mentiroso). */
cases["07-length-mentiroso.pdf"] = buildPdf([
  CATALOG, PAGES, PAGE,
  `<< /Length 999999999 >>\nstream\nBT /F1 24 Tf 100 700 Td (Hola) Tj ET\nendstream`,
  FONT,
]);

/* 8. PDF con un objeto que se referencia a sí mismo (bucle). */
cases["08-bucle.pdf"] = buildPdf([
  `<< /Type /Catalog /Pages 1 0 R >>`, // el catálogo apunta a sí mismo
  PAGES, PAGE, CONTENT, FONT,
]);

/* 9. PDF vacío (0 bytes) y PDF que solo es la cabecera. */
cases["09-vacio.pdf"] = Buffer.alloc(0);
cases["10-solo-cabecera.pdf"] = Buffer.from("%PDF-1.7\n", "latin1");

/* 10. Archivo que no es PDF pero tiene extensión .pdf. */
cases["11-no-es-pdf.pdf"] = Buffer.from("Esto no es un PDF, es texto plano con extensión .pdf\n".repeat(20), "latin1");

/* 11. PDF con una página gigante (MediaBox de 100.000 x 100.000 puntos). */
cases["12-pagina-gigante.pdf"] = buildPdf([
  CATALOG, PAGES,
  `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100000 100000] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>`,
  CONTENT, FONT,
]);

for (const [name, buf] of Object.entries(cases)) {
  writeFileSync(join(outDir, name), buf);
  console.log(name.padEnd(28), String(buf.length).padStart(10), "bytes");
}
console.log("\nGenerados", Object.keys(cases).length, "casos en", outDir);
console.log("Ver el resultado esperado de cada uno en web/tests/hostile-cases.md");
