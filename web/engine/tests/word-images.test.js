/**
 * Imágenes en Word: regresión de paridad.
 *
 * El motor del navegador no incrustaba las imágenes de página completa de
 * un escaneo en Word (0/1 y 0/2 en paridad), aunque Python sí y aunque
 * PowerPoint sí lo hacía. Además `Packer.toBuffer` de docx lanza en el
 * navegador "nodebuffer is not supported by this platform": el empaquetado
 * usa ahora `toArrayBuffer`, que funciona en Node y en el navegador.
 *
 * El caso de escaneo se prueba sin OCR (unitario, rápido): se extrae el
 * modelo de una página nativa, se marca como escaneada y su imagen como
 * de página completa, y se comprueba que el .docx la incrusta. El OCR
 * completo de un escaneo en esta VM tarda minutos con tesseract.js, por
 * lo que el extremo a extremo de escaneo se verifica en scripts/parity.py,
 * no aquí.
 */
import * as mupdf from "mupdf";
import { unzipSync } from "fflate";
import { describe, expect, it } from "vitest";
import { extractPage } from "../src/extract.js";
import { convertPdf } from "../src/index.js";
import { modelsToWord } from "../src/word.js";
import { readFixture } from "./helpers.js";

function mediaFiles(buffer) {
  const files = unzipSync(new Uint8Array(buffer));
  return Object.keys(files).filter((n) => n.startsWith("word/media/"));
}

/** Veces que cada imagen (rId) se dibuja en document.xml. */
function blipCounts(buffer) {
  const files = unzipSync(new Uint8Array(buffer));
  const xml = new TextDecoder("utf-8").decode(files["word/document.xml"]);
  const counts = {};
  for (const m of xml.matchAll(/<a:blip[^>]*r:embed="([^"]+)"/g)) {
    counts[m[1]] = (counts[m[1]] ?? 0) + 1;
  }
  return counts;
}

describe("Word: imágenes incrustadas", () => {
  it("escaneado: la imagen de página completa va en el .docx", async () => {
    const doc = mupdf.Document.openDocument(readFixture("factura_real_logo_sello.pdf"), "application/pdf");
    const model = await extractPage(doc, 0, { mupdf, ocr: false });
    expect(model.images.length).toBeGreaterThanOrEqual(1);
    // Simula un escaneo: la imagen cubre toda la página y hay texto OCR.
    model.scanned = true;
    model.images[0].fullPage = true;
    model.images[0].x0 = 0;
    model.images[0].y0 = 0;
    model.images[0].x1 = model.width;
    model.images[0].y1 = model.height;
    const { buffer } = await modelsToWord([model], { mode: "grid" });
    expect(mediaFiles(buffer).length).toBeGreaterThanOrEqual(1);
    doc.destroy?.();
  });

  it("factura con logo y sello: el logo va en el .docx", async () => {
    const { buffer } = await convertPdf(readFixture("factura_real_logo_sello.pdf"), "word");
    expect(mediaFiles(buffer).length).toBeGreaterThanOrEqual(1);
  }, 120_000);

  it("escaneado en grid: la imagen de página completa se dibuja una sola vez", async () => {
    // Regresión: sin OCR (sin filas) la imagen iba en línea (párrafo de
    // escaneo) y además flotante en la cola, así que la página aparecía
    // dos veces en el documento (2 <a:blip> para 1 archivo en media).
    const doc = mupdf.Document.openDocument(readFixture("escaneado.pdf"), "application/pdf");
    const model = await extractPage(doc, 0, { mupdf, ocr: false });
    expect(model.scanned).toBe(true);
    expect(model.images.length).toBe(1);
    expect(model.images[0].fullPage).toBe(true);
    const { buffer } = await modelsToWord([model], { mode: "grid" });
    expect(mediaFiles(buffer).length).toBe(1);
    const counts = blipCounts(buffer);
    expect(Object.values(counts)).toEqual([1]);
    doc.destroy?.();
  });
});
