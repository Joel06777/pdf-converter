/**
 * Tamaños reales del motor y capacidad en Vercel Hobby (100 GB/mes).
 * Ejecuta scripts/measure-sizes.mjs y comprueba los números que van al README.
 */
import { brotliCompressSync, constants as zlibConstants } from "node:zlib";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function size(p) {
  return fs.statSync(path.join(ROOT, p)).size;
}

describe("tamaños del motor (medidos, no estimados)", () => {
  it("mupdf wasm: ~10,4 MB crudo, ~3,6 MB Brotli (el .br lo trae el paquete)", () => {
    const raw = size("node_modules/mupdf/dist/mupdf-wasm.wasm");
    const br = size("node_modules/mupdf/dist/mupdf-wasm.wasm.br");
    expect(raw).toBeGreaterThan(10_000_000);
    expect(raw).toBeLessThan(11_000_000);
    expect(br).toBeGreaterThan(3_000_000);
    expect(br).toBeLessThan(4_000_000);
    expect(br / raw).toBeLessThan(0.4);
  });

  it("mupdf js: ~100 KB crudo, ~19 KB Brotli", () => {
    const raw = size("node_modules/mupdf/dist/mupdf.js");
    const br = size("node_modules/mupdf/dist/mupdf.js.br");
    expect(raw).toBeGreaterThan(90_000);
    expect(raw).toBeLessThan(120_000);
    expect(br).toBeLessThan(30_000);
  });

  it("el núcleo de Tesseract y los datos de idioma existen y pesan lo esperado", () => {
    const core = size("node_modules/tesseract.js-core/tesseract-core.wasm");
    expect(core).toBeGreaterThan(3_000_000);
    expect(core).toBeLessThan(4_000_000);
    // Los datos de idioma se descargan en .tessdata/ (ver tests/ocr.test.js).
    const spa = path.join(ROOT, ".tessdata", "spa.traineddata.gz");
    const eng = path.join(ROOT, ".tessdata", "eng.traineddata.gz");
    if (fs.existsSync(spa) && fs.existsSync(eng)) {
      expect(fs.statSync(spa).size).toBeGreaterThan(1_000_000);
      expect(fs.statSync(eng).size).toBeGreaterThan(1_500_000);
    }
  });

  it("una primera visita cabe decenas de miles de veces en 100 GB/mes", () => {
    // Peor caso medido: motor + librerías + OCR completo, todo en Brotli.
    const wasmBr = size("node_modules/mupdf/dist/mupdf-wasm.wasm.br");
    const jsBr = size("node_modules/mupdf/dist/mupdf.js.br");
    const coreWasm = fs.readFileSync(path.join(ROOT, "node_modules/tesseract.js-core/tesseract-core.wasm"));
    const coreBr = brotliCompressSync(coreWasm, { params: { [zlibConstants.BROTLI_PARAM_QUALITY]: 11 } }).length;
    const firstVisitWorst = wasmBr + jsBr + coreBr;
    const visits = Math.floor((100 * 1024 ** 3) / firstVisitWorst);
    console.log(`  primera visita (motor + núcleo OCR, Brotli): ${(firstVisitWorst / 1024 / 1024).toFixed(2)} MB → ${visits.toLocaleString("es")} visitas/mes en 100 GB`);
    expect(visits).toBeGreaterThan(10_000);
  });
});
