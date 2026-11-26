/**
 * Entrada del navegador (web/engine/index.js tras el build).
 *
 * Implementa el contrato que espera web/engine.js (ver su cabecera) usando
 * el Web Worker de src/worker.js: la conversión nunca corre en el hilo
 * principal y el archivo PDF no sale del dispositivo.
 *
 * Este archivo es ligero a propósito: NO importa el motor (MuPDF, ExcelJS,
 * docx, pptxgenjs, Tesseract) en el hilo principal; todo eso vive dentro
 * del worker empaquetado en ./dist/worker.js. La vista previa usa pdf.js,
 * que ya vende la web en ../vendor/pdfjs/.
 *
 * Build (desde web/engine/): `npm run build` → genera web/engine/index.js
 * (este archivo) y web/engine/dist/worker.js con Vite (MIT, gratis).
 * Sin build no hay web/engine/index.js y la web queda en modo demostración.
 */
import { ENGINE_VERSION } from "./version.js";

const WORKER_URL = new URL("./dist/worker.js", import.meta.url);
// MuPDF se sirve aparte (ver src/worker.js): su salida de Emscripten no
// sobrevive al empaquetado con Vite.
const MUPDF_URL = new URL("./vendor/mupdf/mupdf.js", import.meta.url).href;
const TESSDATA_URL = new URL("./.tessdata/", import.meta.url).href;
const CORE_URL = new URL("./dist/tesseract-core-lstm.js", import.meta.url).href;
const CORE_WASM_URL = new URL("./dist/tesseract-core-lstm.wasm", import.meta.url).href;
const WORKER_SCRIPT_URL = new URL("./dist/tesseract-worker.min.js", import.meta.url).href;
const PDFJS_URL = new URL("../vendor/pdfjs/pdf-5.5.207.min.mjs", import.meta.url).href;
void CORE_WASM_URL; // El núcleo carga su .wasm junto a su .js; se copia en el build.

let worker = null;
let nextId = 1;
const pending = new Map();
let pdfjsLib = null;
let pdfjsWorkerSrc = null;

function pngToDataUrl(png) {
  return new Promise((resolve, reject) => {
    const blob = new Blob([png], { type: "image/png" });
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("No se pudo leer la imagen de la página."));
    reader.readAsDataURL(blob);
  });
}

async function loadPdfjs() {
  if (pdfjsLib) return pdfjsLib;
  pdfjsLib = await import(/* @vite-ignore */ PDFJS_URL);
  if (!pdfjsWorkerSrc) {
    pdfjsWorkerSrc = new URL("../vendor/pdfjs/pdf-5.5.207.worker.min.mjs", import.meta.url).href;
    pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerSrc;
  }
  return pdfjsLib;
}

function callWorker(type, payload, onProgress) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject, onProgress });
    worker.postMessage({ type, id, ...payload });
  });
}

function onWorkerMessage(event) {
  const msg = event.data ?? {};
  const entry = msg.id != null ? pending.get(msg.id) : null;
  if (msg.type === "progress") {
    entry?.onProgress?.(msg.page, msg.total, msg.stage);
    return;
  }
  if (msg.type === "ready") {
    const ready = pending.get(0);
    if (ready) {
      pending.delete(0);
      ready.resolve();
    }
    return;
  }
  if (!entry) return;
  pending.delete(msg.id);
  if (msg.type === "error") {
    const err = new Error(msg.error || "Error del motor.");
    err.code = msg.code;
    entry.reject(err);
    return;
  }
  entry.resolve(msg);
}

async function load(onProgress) {
  if (worker) return;
  onProgress?.(0.1, "Cargando el motor de conversión…");
  worker = new Worker(WORKER_URL, { type: "module" });
  worker.onmessage = onWorkerMessage;
  worker.onerror = (event) => {
    const err = new Error(
      "No se pudo cargar el motor de conversión. Comprueba tu conexión y recarga la página.",
    );
    err.code = "ENGINE_LOAD_FAILED";
    const ready = pending.get(0);
    if (ready) {
      pending.delete(0);
      ready.reject(err);
    }
  };
  onProgress?.(0.4, "Descargando MuPDF.js…");
  await new Promise((resolve, reject) => {
    pending.set(0, { resolve, reject, onProgress: null });
    worker.postMessage({
      type: "init",
      mupdfUrl: MUPDF_URL,
      tessdataUrl: TESSDATA_URL,
      coreUrl: CORE_URL,
      workerUrl: WORKER_SCRIPT_URL,
    });
  });
  onProgress?.(1, "Motor listo.");
}

async function open(arrayBuffer, nombreArchivo) {
  if (!worker) throw new Error("El motor no está cargado. Llama primero a load().");
  const buffer = arrayBuffer instanceof Uint8Array ? arrayBuffer.buffer : arrayBuffer;
  const msg = await callWorker("info", { pdf: buffer.slice(0) });
  return {
    buffer,
    name: nombreArchivo,
    pageCount: msg.pageCount,
    encrypted: msg.encrypted,
    title: msg.title,
    pages: msg.pages,
  };
}

async function extract(doc, { from = 1, to = null, onProgress } = {}) {
  if (!worker) throw new Error("El motor no está cargado. Llama primero a load().");
  const last = to ?? doc.pageCount;
  const msg = await callWorker(
    "extract",
    { pdf: doc.buffer.slice(0), from, to: last, options: { ocr: true } },
    (page, total) => onProgress?.(page - from + 1, total, `Procesando página ${page} de ${last}…`),
  );
  const model = msg.model;
  // Las imágenes llegan como bytes PNG: convertirlas a data URL aquí, en
  // el hilo principal, que es donde existen Blob y FileReader.
  for (const page of model.pages) {
    for (const img of page.images ?? []) {
      if (img.png) {
        img.dataUrl = await pngToDataUrl(img.png);
        img.width = img.x1 - img.x0;
        img.height = img.y1 - img.y0;
        delete img.png;
      }
    }
  }
  return model;
}

async function renderPage(doc, indicePagina, canvas, escala = 1.5) {
  const lib = await loadPdfjs();
  const loading = lib.getDocument({ data: doc.buffer.slice(0) });
  const pdf = await loading.promise;
  const page = await pdf.getPage(indicePagina + 1);
  const viewport = page.getViewport({ scale: escala });
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  const ctx = canvas.getContext("2d");
  await page.render({ canvasContext: ctx, viewport }).promise;
}

function dispose(doc) {
  void doc;
  // El worker no guarda documentos entre mensajes; nada que liberar.
}

async function convert(arrayBuffer, target, options = {}) {
  if (!worker) throw new Error("El motor no está cargado. Llama primero a load().");
  const msg = await callWorker(
    "convert",
    { pdf: arrayBuffer, target, options },
    options.onProgress,
  );
  return { buffer: msg.buffer, filename: msg.filename, info: msg.info, quality: msg.quality };
}

window.PdfConverterEngine = {
  ENGINE_VERSION: `${ENGINE_VERSION} (MuPDF.js 1.28.6, Tesseract.js 7.0.0)`,
  engineName: "MuPDF.js 1.28.6 + Tesseract.js 7.0.0",
  supportsOCR: true,
  load,
  open,
  renderPage,
  extract,
  dispose,
  convert,
};
