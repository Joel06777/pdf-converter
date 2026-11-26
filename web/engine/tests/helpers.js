import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";

export const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../tests/fixtures");
export const TESSDATA_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../.tessdata");

export function readFixture(name) {
  return fs.readFileSync(path.join(FIXTURES, name));
}

const TESSDATA_URLS = {
  spa: "https://github.com/tesseract-ocr/tessdata_fast/raw/main/spa.traineddata",
  eng: "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata",
};

/**
 * Descarga los datos de idioma de Tesseract (tessdata_fast, gratis) a
 * .tessdata/ si faltan, en formato .traineddata.gz (el que exige
 * tesseract.js v7). Devuelve true si están disponibles, false si no hay red.
 * No forma parte del repo: es caché local de pruebas.
 */
export async function ensureTessdata() {
  fs.mkdirSync(TESSDATA_DIR, { recursive: true });
  let ok = true;
  for (const [lang, url] of Object.entries(TESSDATA_URLS)) {
    const gzPath = path.join(TESSDATA_DIR, `${lang}.traineddata.gz`);
    if (fs.existsSync(gzPath) && fs.statSync(gzPath).size > 100_000) continue;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const buf = Buffer.from(await res.arrayBuffer());
      fs.writeFileSync(gzPath, zlib.gzipSync(buf, { level: 9 }));
    } catch {
      ok = false;
    }
  }
  return ok && fs.existsSync(path.join(TESSDATA_DIR, "spa.traineddata.gz"));
}

export function requireResolve(pkg, subpath) {
  const require = createRequire(import.meta.url);
  return require.resolve(`${pkg}/${subpath}`);
}
