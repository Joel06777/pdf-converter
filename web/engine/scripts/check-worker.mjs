/**
 * Harness Node para verificar el protocolo de src/worker.js sin navegador:
 * ejecuta el worker en un worker_thread con un `self` simulado.
 */
import { Worker } from "node:worker_threads";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WRAPPER = `
import { parentPort } from "node:worker_threads";
// self sin postMessage durante la importación: si no, setImmediate (dep.
// de exceljs) detecta "navegador" y falla con attachEvent.
globalThis.self = {
  set onmessage(fn) { globalThis.__onmessage = fn; },
  get onmessage() { return globalThis.__onmessage; },
};
parentPort.on("message", (msg) => { globalThis.__onmessage?.({ data: msg }); });
await import(${JSON.stringify(new URL("../src/worker.js", import.meta.url).href)});
globalThis.self.postMessage = (msg, transfer) => { if (Array.isArray(transfer)) parentPort.postMessage(msg, transfer); else parentPort.postMessage(msg); };
parentPort.postMessage({ type: "__loaded" });
`;

const wrapperPath = path.join(path.dirname(fileURLToPath(import.meta.url)), ".worker-harness.mjs");
fs.writeFileSync(wrapperPath, WRAPPER);

const worker = new Worker(wrapperPath);
const pdf = fs.readFileSync("/home/hatch/workspace/pdf-converter-work/pdf-converter/tests/fixtures/factura.pdf");
const mupdfUrl = new URL("../node_modules/mupdf/dist/mupdf.js", import.meta.url).href;

const pending = new Map();
let loaded = false;
worker.on("message", (msg) => {
  if (msg.type === "__loaded") { loaded = true; return; }
  if (msg.type === "progress") { console.log(`progreso ${msg.stage}: ${msg.page}/${msg.total}`); return; }
  if (msg.type === "ready") { console.log("worker: ready"); return; }
  if (msg.type === "done") {
    console.log(`worker: done, ${msg.buffer.length} bytes, calidad=${JSON.stringify(msg.quality)}`);
    pending.get(msg.id)?.(msg);
    return;
  }
  if (msg.type === "error") {
    console.log("worker: error", msg.error, msg.code);
    pending.get(msg.id)?.(msg);
  }
});
worker.on("error", (e) => { console.error("worker thread error:", e); process.exit(1); });

await new Promise((r) => { const t = setInterval(() => { if (loaded) { clearInterval(t); r(); } }, 50); });
worker.postMessage({ type: "init", mupdfUrl });
await new Promise((r) => setTimeout(r, 1500));
const done = await new Promise((resolve) => {
  pending.set("test-1", resolve);
  worker.postMessage({ type: "convert", id: "test-1", pdf: pdf.buffer.slice(pdf.byteOffset, pdf.byteOffset + pdf.byteLength), target: "excel" });
});
if (done.type !== "done" || done.quality.textCoverage !== 1.0) {
  console.error("FALLO: conversión por worker no llegó a 1.0");
  process.exit(1);
}
console.log("OK: protocolo del worker verificado (init → convert → done, cobertura 1.0)");
await worker.terminate();
fs.unlinkSync(wrapperPath);
