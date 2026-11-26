/**
 * Prueba de la web real (web/index.html): subir un PDF, convertirlo con
 * el motor del navegador (web/engine/index.js + dist/worker.js) y
 * descargar el resultado, en escritorio (Chromium) y en móvil (Pixel 7).
 *
 * También comprueba que durante toda la sesión no sale ninguna petición
 * de red fuera del servidor estático local.
 *
 * Requiere el build del motor: `npm run build` en web/engine/ (sin él,
 * la página queda en modo demostración y la conversión no arranca).
 */
import http from "node:http";
import { createReadStream, existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { unzipSync, strFromU8 } from "../../web/engine/node_modules/fflate/esm/index.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const WEB_ROOT = path.join(REPO_ROOT, "web");
const FIXTURE_PDF = path.join(REPO_ROOT, "tests/fixtures/factura.pdf");
const PORT = 8931;

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".webmanifest": "application/manifest+json",
  ".gz": "application/gzip",
};

function serveStatic(req, res) {
  const url = new URL(req.url, "http://127.0.0.1");
  const pathname = decodeURIComponent(url.pathname);
  const file = path.join(WEB_ROOT, pathname === "/" ? "index.html" : pathname);
  if (!file.startsWith(WEB_ROOT) || !existsSync(file)) {
    res.writeHead(404);
    res.end("no encontrado");
    return;
  }
  res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
  createReadStream(file).pipe(res);
}

let server;

test.beforeAll(async () => {
  server = http.createServer(serveStatic);
  await new Promise((resolve) => server.listen(PORT, "127.0.0.1", resolve));
});

test.afterAll(async () => {
  await new Promise((resolve) => server.close(resolve));
});

async function convertAndDownload(page, target) {
  const requests = [];
  page.on("request", (req) => requests.push(req.url()));
  await page.goto("/");
  await page.locator("#fileInput").setInputFiles(FIXTURE_PDF);
  await expect(page.locator("#convertBtn")).toBeEnabled({ timeout: 30000 });
  await page.locator("#target").selectOption(target);
  const downloadPromise = page.waitForEvent("download", { timeout: 120000 });
  await page.locator("#convertBtn").click();
  await expect(page.locator("#quality")).toBeVisible({ timeout: 120000 });
  const quality = await page.locator("#quality").textContent();
  expect(quality).toMatch(/texto: 100 %/);
  expect(quality).toMatch(/cifras: 100 %/);
  await page.locator("#downloadList a").first().click();
  const download = await downloadPromise;
  const filePath = await download.path();
  const bytes = readFileSync(filePath);
  const nonStatic = requests.filter((url) => {
    try {
      return new URL(url).origin !== `http://127.0.0.1:${PORT}`;
    } catch {
      return true;
    }
  });
  expect(nonStatic, `peticiones fuera del origen local: ${nonStatic.join(", ")}`).toEqual([]);
  return bytes;
}

test("escritorio: factura.pdf → Excel con la cifra TOTAL y sin red externa", async ({ page }) => {
  test.skip(test.info().project.name !== "chromium", "solo en el proyecto de escritorio");
  const bytes = await convertAndDownload(page, "excel");
  expect(bytes.length).toBeGreaterThan(1000);
  const zip = unzipSync(new Uint8Array(bytes));
  const sheet = strFromU8(zip["xl/worksheets/sheet1.xml"] ?? new Uint8Array());
  const strings = strFromU8(zip["xl/sharedStrings.xml"] ?? new Uint8Array());
  expect(sheet + strings).toContain("335");
  expect(strings).toContain("TOTAL");
});

test("móvil Pixel 7: factura.pdf → Word con el texto de la factura", async ({ page }) => {
  test.skip(test.info().project.name !== "mobile", "solo en el proyecto móvil");
  const bytes = await convertAndDownload(page, "word");
  expect(bytes.length).toBeGreaterThan(1000);
  const zip = unzipSync(new Uint8Array(bytes));
  const doc = strFromU8(zip["word/document.xml"] ?? new Uint8Array());
  expect(doc).toContain("335");
});
