#!/usr/bin/env node
/**
 * Empaqueta el motor para el navegador (web/engine/index.js + dist/).
 *
 *   npm run build          (desde web/engine/)
 *
 * Produce:
 *   web/engine/index.js            adaptador (src/browser-entry.js)
 *   web/engine/dist/worker.js      worker con el motor completo (ESM)
 *   web/engine/vendor/mupdf/       MuPDF.js + WASM, servidos aparte
 *   web/engine/dist/tesseract-*.js/.wasm      núcleo y script de Tesseract
 *   web/engine/.tessdata/*.traineddata.gz     datos de idioma spa/eng
 *
 * Herramienta: Vite 8 (MIT, gratis, ya instalada como dependencia de
 * desarrollo de Vitest). No hay servidor ni servicio de pago: todo el
 * trabajo ocurre en esta máquina y los archivos resultantes son estáticos.
 *
 * MuPDF NO se empaqueta: su salida de Emscripten (top-level await +
 * `import("module")` en la rama de Node) se rompe al empaquetarla con
 * Vite/Rolldown (probado el 26 nov 2026: el worker empaquetado con MuPDF
 * dentro no responde ni pide el .wasm, y en Node falla con
 * "e is not a function"). Se copia tal cual a web/engine/vendor/mupdf/
 * y el worker la carga con import dinámico. Lo mismo para el núcleo
 * de Tesseract, que carga su .wasm junto a su .js.
 */
import { copyFile, mkdir, readdir, rm, stat, rename } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const engineDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const root = engineDir;
const distDir = join(engineDir, "dist");
const tessDir = join(engineDir, ".tessdata");

const TESSDATA_BASE =
  "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main";

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

async function ensureTessdata() {
  await mkdir(tessDir, { recursive: true });
  for (const lang of ["spa", "eng"]) {
    const dest = join(tessDir, `${lang}.traineddata.gz`);
    if (await exists(dest)) {
      console.log(`tessdata: ${lang} ya existe, se reutiliza.`);
      continue;
    }
    const url = `${TESSDATA_BASE}/${lang}.traineddata.gz`;
    console.log(`tessdata: descargando ${url} …`);
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(
        `No se pudo descargar ${url} (HTTP ${res.status}). ` +
          `Sin estos datos el OCR no funciona. Descárgalos a mano en web/engine/.tessdata/ ` +
          `desde https://github.com/tesseract-ocr/tessdata_fast (gratis, sin cuenta).`,
      );
    }
    const bytes = new Uint8Array(await res.arrayBuffer());
    const { writeFile } = await import("node:fs/promises");
    await writeFile(dest, bytes);
    console.log(`tessdata: ${lang} guardado (${bytes.length} bytes).`);
  }
}

async function copyAssets() {
  await mkdir(distDir, { recursive: true });
  const vendorDir = join(engineDir, "vendor", "mupdf");
  await mkdir(vendorDir, { recursive: true });
  const copies = [
    // MuPDF: se sirve aparte, sin empaquetar (ver cabecera).
    ["node_modules/mupdf/dist/mupdf.js", join(vendorDir, "mupdf.js")],
    ["node_modules/mupdf/dist/mupdf-wasm.js", join(vendorDir, "mupdf-wasm.js")],
    ["node_modules/mupdf/dist/mupdf-wasm.wasm", join(vendorDir, "mupdf-wasm.wasm")],
    ["node_modules/mupdf/dist/mupdf-wasm.wasm.br", join(vendorDir, "mupdf-wasm.wasm.br")],
    ["node_modules/mupdf/LICENSE", join(vendorDir, "LICENSE")],
    // Tesseract: el núcleo carga su .wasm junto a su .js.
    [
      "node_modules/tesseract.js-core/tesseract-core-lstm.js",
      join(distDir, "tesseract-core-lstm.js"),
    ],
    [
      "node_modules/tesseract.js-core/tesseract-core-lstm.wasm",
      join(distDir, "tesseract-core-lstm.wasm"),
    ],
    [
      "node_modules/tesseract.js-core/tesseract-core-lstm.wasm.js",
      join(distDir, "tesseract-core-lstm.wasm.js"),
    ],
    ["node_modules/tesseract.js/dist/worker.min.js", join(distDir, "tesseract-worker.min.js")],
  ];
  for (const [from, to] of copies) {
    const src = join(root, from);
    if (!(await exists(src))) {
      throw new Error(`Falta el archivo ${src}. Ejecuta primero: npm ci`);
    }
    await copyFile(src, to);
    console.log(`copiado: ${to.replace(engineDir + "/", "")}`);
  }
}

async function main() {
  // 1. Adaptador del hilo principal → web/engine/index.js
  // Vite no permite outDir = root, así que se construye en .build-tmp y
  // se mueve el archivo a su lugar.
  const tmpDir = join(engineDir, ".build-tmp");
  await build({
    root,
    logLevel: "warn",
    build: {
      emptyOutDir: true,
      outDir: tmpDir,
      lib: {
        entry: join(engineDir, "src/browser-entry.js"),
        formats: ["es"],
        fileName: () => "index.js",
      },
      rollupOptions: {
        output: { codeSplitting: false },
      },
    },
  });
  await rename(join(tmpDir, "index.js"), join(engineDir, "index.js"));
  await rm(tmpDir, { recursive: true, force: true });
  console.log("build: web/engine/index.js listo.");

  // 2. Worker con el motor completo → web/engine/dist/worker.js
  await build({
    root,
    logLevel: "warn",
    build: {
      emptyOutDir: true,
      outDir: distDir,
      lib: {
        entry: join(engineDir, "src/worker.js"),
        formats: ["es"],
        fileName: () => "worker.js",
      },
      rollupOptions: {
        output: { codeSplitting: false },
      },
    },
  });
  console.log("build: web/engine/dist/worker.js listo.");

  await copyAssets();
  await ensureTessdata();

  const files = await readdir(distDir);
  let total = 0;
  for (const f of files) total += (await stat(join(distDir, f))).size;
  console.log(
    `build: dist/ tiene ${files.length} archivos, ${(total / 1024 / 1024).toFixed(2)} MB en total.`,
  );
}

main().catch((err) => {
  console.error(`build falló: ${err.message}`);
  process.exit(1);
});
