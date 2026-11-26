// Sondeo: ¿cuántas cifras colocadas quedan como texto aislado en .docx
// en modo flow frente a grid? (criterio de celdas de scripts/parity.py)
import * as mupdf from "mupdf";
import { unzipSync } from "fflate";
import { extractPage } from "../src/extract.js";
import { buildLayout } from "../src/layout.js";
import { modelsToWord } from "../src/word.js";
import { parseNumber } from "../src/numbers.js";
import { readFixture } from "../tests/helpers.js";

function docxTexts(buffer) {
  const files = unzipSync(new Uint8Array(buffer));
  const xml = new TextDecoder("utf-8").decode(files["word/document.xml"]);
  const out = [];
  const re = /<w:t[^>]*>([^<]*)<\/w:t>/g;
  let m;
  while ((m = re.exec(xml)) !== null) out.push(m[1]);
  return out;
}

function cellScore(models, buffer) {
  const wanted = new Map();
  for (const model of models) {
    const lay = buildLayout(model);
    for (const pl of lay.placements) {
      if (!pl.parsed) continue;
      const v = Math.round(pl.parsed.value * 10000) / 10000;
      wanted.set(v, (wanted.get(v) ?? 0) + 1);
    }
  }
  const texts = docxTexts(buffer);
  const have = new Map();
  for (const t of texts) {
    const p = parseNumber(t.trim());
    if (!p) continue;
    const v = Math.round(p.value * 10000) / 10000;
    have.set(v, (have.get(v) ?? 0) + 1);
  }
  let found = 0;
  let total = 0;
  for (const [v, n] of wanted) {
    total += n;
    found += Math.min(n, have.get(v) ?? 0);
  }
  return total ? { found, total, score: Math.round((found / total) * 10000) / 10000 } : null;
}

const files = [
  "contrato_servicios.pdf",
  "dos_columnas_mixto.pdf",
  "informe_mensual_mixto.pdf",
  "tabla_encabezado_doble.pdf",
  "tabla_sin_lineas_nomina.pdf",
  "tabla_sin_lineas_ventas.pdf",
  "dos_columnas.pdf",
  "factura.pdf",
];
for (const f of files) {
  const doc = mupdf.Document.openDocument(readFixture(f), "application/pdf");
  const models = [];
  for (let n = 0; n < doc.countPages(); n++) {
    models.push(await extractPage(doc, n, { mupdf, ocr: false }));
  }
  const auto = await modelsToWord(models, { mode: "auto" });
  const flow = await modelsToWord(models, { mode: "flow" });
  const grid = await modelsToWord(models, { mode: "grid" });
  console.log(
    f,
    "| auto:", auto.info.engine,
    "| flow:", JSON.stringify(cellScore(models, flow.buffer)),
    "| grid:", JSON.stringify(cellScore(models, grid.buffer)),
  );
  doc.destroy?.();
}
