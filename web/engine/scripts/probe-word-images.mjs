// Diagnóstico: ¿de dónde sale la segunda imagen en el .docx de un escaneo?
import * as mupdf from "mupdf";
import { unzipSync } from "fflate";
import { extractPage } from "../src/extract.js";
import { modelsToWord } from "../src/word.js";
import { readFixture } from "../tests/helpers.js";

const doc = mupdf.Document.openDocument(readFixture("escaneado.pdf"), "application/pdf");
const model = await extractPage(doc, 0, { mupdf, ocr: false });
console.log("modelo: scanned=", model.scanned, "images=", model.images.length);
for (const img of model.images) {
  console.log("  img:", JSON.stringify({ x0: img.x0, y0: img.y0, x1: img.x1, y1: img.y1, fullPage: img.fullPage, width: img.width, height: img.height }));
}
const out = await modelsToWord([model], { mode: "grid" });
const files = unzipSync(new Uint8Array(out.buffer));
const media = Object.keys(files).filter((n) => n.startsWith("word/media/"));
console.log("engine:", out.info.engine, "media en docx:", media);
const xml = new TextDecoder("utf-8").decode(files["word/document.xml"]);
// Contexto de cada referencia a imagen (blip r:embed)
const re = /<a:blip[^>]*r:embed="([^"]+)"/g;
let m;
while ((m = re.exec(xml)) !== null) {
  const i = m.index;
  console.log("blip", m[1], "contexto:", xml.slice(Math.max(0, i - 120), i + 60).replace(/\s+/g, " "));
}
