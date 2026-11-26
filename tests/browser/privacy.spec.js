/**
 * Prueba de privacidad: durante una conversión en el navegador no sale
 * ninguna petición de red salvo la carga de archivos estáticos del mismo
 * origen (módulos JS, wasm). Falla si aparece cualquier otra petición
 * (otro origen, /api, telemetría, CDN, etc.).
 *
 * La conversión se ejecuta con el worker REAL empaquetado
 * (web/engine/dist/worker.js, generado con `npm run build` en web/engine)
 * en la página tests/browser/fixtures/privacy-app.html, servida por un
 * servidor estático local que levanta esta misma prueba (sin dependencias
 * externas). Se convierten los tres destinos (Excel, Word y PowerPoint)
 * con el motor completo, sin stubs.
 */
import http from "node:http";
import { createReadStream, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect, devices, chromium } from "@playwright/test";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PORT = 8931;

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".css": "text/css",
  ".map": "application/json",
};

// Solo se sirven el motor, la página de prueba y el fixture; nada más del repo.
const ALLOWED_PREFIXES = ["/web/engine/", "/tests/browser/", "/tests/fixtures/"];

function serveStatic(req, res) {
  const url = new URL(req.url, "http://127.0.0.1");
  const pathname = decodeURIComponent(url.pathname);
  if (!ALLOWED_PREFIXES.some((p) => pathname.startsWith(p))) {
    res.writeHead(404);
    res.end("no permitido");
    return;
  }
  const file = path.join(REPO_ROOT, pathname);
  if (!file.startsWith(REPO_ROOT) || !existsSync(file)) {
    res.writeHead(404);
    res.end("no encontrado");
    return;
  }
  res.writeHead(200, {
    "content-type": MIME[path.extname(file)] || "application/octet-stream",
  });
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

/** Regla de privacidad: solo archivos estáticos del mismo origen. */
function isStaticAsset(url) {
  try {
    const u = new URL(url);
    return (
      u.origin === `http://127.0.0.1:${PORT}` &&
      ALLOWED_PREFIXES.some((p) => u.pathname.startsWith(p))
    );
  } catch {
    return false;
  }
}

async function runConversion(page) {
  const requests = [];
  page.on("request", (req) => requests.push(req.url()));
  await page.goto("/tests/browser/fixtures/privacy-app.html");
  await expect(page.locator("#status")).toHaveText("motor listo");
  // La página descarga el fixture y convierte a los tres destinos.
  await page.evaluate(() => window.__convertAll());
  await expect(page.locator("#status")).toHaveText("terminado", { timeout: 120000 });
  const result = JSON.parse((await page.locator("#result").textContent()) || "{}");
  for (const target of ["excel", "word", "pptx"]) {
    expect(result[target]?.size, `el .${target} no se generó`).toBeGreaterThan(1000);
  }
  const nonStatic = requests.filter((url) => !isStaticAsset(url));
  return { requests, nonStatic };
}

test("conversión en el navegador sin peticiones de red externas", async ({ page }) => {
  const { requests, nonStatic } = await runConversion(page);
  expect(
    nonStatic,
    `la conversión hizo peticiones fuera de los estáticos locales: ${nonStatic.join(", ")}`,
  ).toEqual([]);
  // Información: cuántos estáticos se cargaron durante la conversión
  // (módulos/wasm del mismo origen; permitidos por la regla).
  console.log(`peticiones estáticas locales durante la conversión: ${requests.length}`);
});

test("móvil con CPU limitada y memoria reducida: la conversión termina", async ({ browserName }) => {
  // La limitación de CPU por CDP solo existe en Chromium.
  test.skip(browserName !== "chromium", "CPU throttling por CDP solo en Chromium");
  const browser = await chromium.launch({
    args: [
      "--js-flags=--max-old-space-size=512",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  });
  try {
    const context = await browser.newContext({ ...devices["Pixel 7"] });
    const page = await context.newPage();
    const session = await context.newCDPSession(page);
    // CPU 4 veces más lenta (equivalente a un móvil de gama baja).
    await session.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    const { nonStatic } = await runConversion(page);
    expect(nonStatic).toEqual([]);
    await context.close();
  } finally {
    await browser.close();
  }
});
