/**
 * Mide los tamaños reales descargados del motor y calcula cuántas visitas
 * nuevas por mes caben en 100 GB/mes del plan Hobby de Vercel.
 *
 * Uso: npm run sizes
 * Salida: tabla en consola + web/engine/sizes.json (para el README).
 */
import { brotliCompressSync, constants as zlibConstants, gzipSync } from "node:zlib";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const VERCEL_HOBBY_BYTES_MONTH = 100 * 1024 ** 3;

function stat(p) {
  return fs.existsSync(p) ? fs.statSync(p).size : null;
}

function compressSizes(buf) {
  return {
    raw: buf.length,
    gzip: gzipSync(buf, { level: 9 }).length,
    brotli: brotliCompressSync(buf, { params: { [zlibConstants.BROTLI_PARAM_QUALITY]: 11 } }).length,
  };
}

function file(p) {
  const full = path.join(ROOT, p);
  const size = stat(full);
  if (size === null) return { path: p, missing: true };
  const buf = fs.readFileSync(full);
  return { path: p, ...compressSizes(buf), shippedBr: stat(`${full}.br`) };
}

function dirSize(dir, pattern) {
  let total = 0;
  for (const f of fs.readdirSync(dir)) {
    if (pattern.test(f)) total += fs.statSync(path.join(dir, f)).size;
  }
  return total;
}

const items = {
  mupdfWasm: file("node_modules/mupdf/dist/mupdf-wasm.wasm"),
  mupdfJs: file("node_modules/mupdf/dist/mupdf.js"),
  tesseractCoreWasm: file("node_modules/tesseract.js-core/tesseract-core.wasm"),
  tesseractCoreJs: file("node_modules/tesseract.js-core/tesseract-core.wasm.js"),
  tesseractWorker: file("node_modules/tesseract.js/dist/worker.min.js"),
  tesseractMain: file("node_modules/tesseract.js/dist/tesseract.min.js"),
  exceljs: file("node_modules/exceljs/dist/exceljs.min.js"),
  docx: file("node_modules/docx/dist/index.umd.cjs"),
  pptxgenjs: file("node_modules/pptxgenjs/dist/pptxgen.bundle.js"),
  fflate: file("node_modules/fflate/umd/index.js"),
};

// Datos de idioma (si están descargados en .tessdata/)
const tessdata = {};
for (const lang of ["spa", "eng"]) {
  const p = path.join(ROOT, ".tessdata", `${lang}.traineddata.gz`);
  tessdata[lang] = stat(p);
}

// Código propio del motor (sin empaquetar; el bundle final depende del empaquetador).
const srcDir = path.join(ROOT, "src");
let srcRaw = 0;
for (const f of fs.readdirSync(srcDir)) {
  if (f.endsWith(".js")) srcRaw += fs.statSync(path.join(srcDir, f)).size;
}
const srcBuf = Buffer.concat(
  fs.readdirSync(srcDir).filter((f) => f.endsWith(".js")).map((f) => fs.readFileSync(path.join(srcDir, f))),
);
const srcSizes = compressSizes(srcBuf);

function fmt(n) {
  if (n === null || n === undefined) return "—";
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(2)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

function visits(bytesPerVisit) {
  return Math.floor(VERCEL_HOBBY_BYTES_MONTH / bytesPerVisit);
}

const brotli = (it) => it.shippedBr ?? it.brotli;

// Escenarios de primera visita (sin caché): lo que descarga un visitante nuevo.
const scenarios = {
  // Solo el motor MuPDF + código propio (PDF nativo a Excel/Word/PPTX).
  soloMotor: brotli(items.mupdfWasm) + brotli(items.mupdfJs) + srcSizes.brotli,
  // + librerías de generación (van en el bundle de la app).
  conLibrerias:
    brotli(items.mupdfWasm) + brotli(items.mupdfJs) + srcSizes.brotli +
    brotli(items.exceljs) + brotli(items.docx) + brotli(items.pptxgenjs) + brotli(items.fflate),
  // + OCR completo (núcleo Tesseract + datos spa+eng).
  conOcr:
    brotli(items.mupdfWasm) + brotli(items.mupdfJs) + srcSizes.brotli +
    brotli(items.exceljs) + brotli(items.docx) + brotli(items.pptxgenjs) + brotli(items.fflate) +
    brotli(items.tesseractCoreWasm) + brotli(items.tesseractCoreJs) + brotli(items.tesseractWorker) +
    brotli(items.tesseractMain) + (tessdata.spa ?? 0) + (tessdata.eng ?? 0),
};

const result = {
  measuredAt: new Date().toISOString(),
  items,
  tessdata,
  engineSrc: { raw: srcRaw, ...srcSizes },
  scenarios: {
    soloMotor: { bytesPerFirstVisit: scenarios.soloMotor, visitsPerMonthAt100GB: visits(scenarios.soloMotor) },
    conLibrerias: { bytesPerFirstVisit: scenarios.conLibrerias, visitsPerMonthAt100GB: visits(scenarios.conLibrerias) },
    conOcr: { bytesPerFirstVisit: scenarios.conOcr, visitsPerMonthAt100GB: visits(scenarios.conOcr) },
  },
  notes: [
    "Los tamaños Brotli de mupdf-wasm.wasm son los .br que ya trae el paquete (comprimidos por el autor).",
    "Las visitas suponen una primera visita sin caché por visitante; las visitas repetidas descargan ~0 (activos inmutables con caché).",
    "El plan Hobby de Vercel incluye 100 GB/mes de ancho de banda; el exceso se cobra o se bloquea según la configuración.",
  ],
};

fs.writeFileSync(path.join(ROOT, "sizes.json"), JSON.stringify(result, null, 2));

console.log("Tamaños descargados (Brotli = lo que sirve Vercel si hay .br o compresión):\n");
console.log("| Archivo | crudo | gzip | brotli |");
console.log("|---|---|---|---|");
for (const [name, it] of Object.entries(items)) {
  if (it.missing) {
    console.log(`| ${name} | FALTA | | |`);
    continue;
  }
  console.log(`| ${name} | ${fmt(it.raw)} | ${fmt(it.gzip)} | ${fmt(brotli(it))}${it.shippedBr ? " (con .br del paquete)" : ""} |`);
}
console.log(`| motor propio (src/*.js) | ${fmt(srcRaw)} | ${fmt(srcSizes.gzip)} | ${fmt(srcSizes.brotli)} |`);
console.log(`| tessdata spa.traineddata.gz | ${fmt(tessdata.spa)} | | |`);
console.log(`| tessdata eng.traineddata.gz | ${fmt(tessdata.eng)} | | |`);
console.log("\nCapacidad en 100 GB/mes (Vercel Hobby), por primera visita sin caché:\n");
console.log(`| Escenario | por visita | visitas/mes |`);
console.log(`|---|---|---|`);
console.log(`| Solo motor (PDF nativo) | ${fmt(scenarios.soloMotor)} | ${visits(scenarios.soloMotor).toLocaleString("es")} |`);
console.log(`| + librerías de generación | ${fmt(scenarios.conLibrerias)} | ${visits(scenarios.conLibrerias).toLocaleString("es")} |`);
console.log(`| + OCR completo (spa+eng) | ${fmt(scenarios.conOcr)} | ${visits(scenarios.conOcr).toLocaleString("es")} |`);
console.log("\nGuardado en sizes.json");
