/**
 * Entrada del Web Worker: la conversión corre en el dispositivo del usuario,
 * página por página, con cancelación y progreso real.
 *
 * Protocolo de mensajes (postMessage):
 *   → { type: "init", mupdfUrl, tessdataUrl?, coreUrl?, workerUrl? }
 *       Carga MuPDF.js desde la URL de estáticos indicada. Responde
 *       { type: "ready" } o { type: "error", error }.
 *   → { type: "info", id, pdf: ArrayBuffer }
 *       Devuelve { type: "info", id, pageCount, encrypted, title,
 *       pages: [{ width, height, hasText }] } sin convertir nada.
 *   → { type: "extract", id, pdf: ArrayBuffer, from, to, options? }
 *       Extrae el modelo neutro del rango de páginas (ver src/neutral.js)
 *       para la vista previa y el corrector de la web. Responde
 *       { type: "extracted", id, model } o { type: "error", id, ... }.
 *   → { type: "convert", id, pdf: ArrayBuffer, target: "excel"|"word"|"pptx",
 *       options?: { layout, formulas, mode, ocr, ocrLang } }
 *       Responde con progreso { type: "progress", id, page, total, stage }
 *       y al final { type: "done", id, buffer, filename, info, quality }
 *       o { type: "error", id, error, code }.
 *   → { type: "cancel", id }  Cancela la conversión en curso.
 *
 * MuPDF NO se empaqueta dentro del worker: su salida de Emscripten
 * (top-level await + `import("module")` en la rama de Node) se rompe
 * al empaquetarla con Vite/Rolldown (probado el 26 nov 2026: el worker
 * empaquetado no responde ni pide el .wasm, y en Node falla con
 * "e is not a function"). Se sirve como archivo aparte en
 * web/engine/vendor/mupdf/ y se carga con import dinámico en "init".
 * El resto (ExcelJS, docx, pptxgenjs, Tesseract, fflate) sí va
 * empaquetado en dist/worker.js.
 *
 * No hay peticiones de red durante la conversión: MuPDF.js y los datos de
 * Tesseract se cargan una sola vez en "init" (estáticos del mismo origen).
 * El OCR solo se crea si un PDF escaneado lo necesita.
 */
import { convertPdf } from "./index.js";
import { ConversionError, pdfOpenError } from "./errors.js";
import { extractPage } from "./extract.js";
import { modelToNeutralPage } from "./neutral.js";
import { OcrEngine, ocrWarning } from "./ocr.js";

let mupdfModule = null;
let tessdataUrl = null;
let coreUrl = null;
let workerUrl = null;
let cancelledId = null;
let ocrEngine = null;

/** OCR perezoso, compartido por convert y extract (solo si hace falta). */
async function ocrRunnerFactory(ocrLang) {
  if (!ocrEngine) {
    ocrEngine = new OcrEngine({ lang: ocrLang, langPath: tessdataUrl, corePath: coreUrl, workerPath: workerUrl });
    await ocrEngine.init();
  }
  return async (png) => ocrEngine.recognizePage(png);
}

function openDoc(pdf, mupdf) {
  const bytes = pdf instanceof Uint8Array ? pdf : new Uint8Array(pdf);
  try {
    return mupdf.Document.openDocument(bytes, "application/pdf");
  } catch (err) {
    throw pdfOpenError(err);
  }
}

self.onmessage = async (event) => {
  const msg = event.data ?? {};
  try {
    if (msg.type === "init") {
      if (!msg.mupdfUrl) throw new ConversionError("Falta la URL de MuPDF.js (mupdfUrl).", "conversion_fallida");
      mupdfModule = await import(/* @vite-ignore */ msg.mupdfUrl);
      tessdataUrl = msg.tessdataUrl ?? null;
      coreUrl = msg.coreUrl ?? null;
      workerUrl = msg.workerUrl ?? null;
      self.postMessage({ type: "ready" });
      return;
    }

    if (msg.type === "cancel") {
      cancelledId = msg.id;
      return;
    }

    if (!mupdfModule) {
      throw new ConversionError("El motor no está inicializado. Envía primero { type: 'init' }.", "conversion_fallida");
    }

    if (msg.type === "info") {
      const doc = openDoc(msg.pdf, mupdfModule);
      try {
        const pageCount = doc.countPages();
        const pages = [];
        for (let n = 0; n < pageCount; n++) {
          const page = doc.loadPage(n);
          const [bx0, by0, bx1, by1] = page.getBounds();
          const stext = page.toStructuredText("preserve-whitespace");
          let chars = 0;
          stext.walk({ onChar() { chars++; } });
          pages.push({ width: bx1 - bx0, height: by1 - by0, hasText: chars >= 20 });
        }
        let title = "";
        try {
          title = doc.getMetaData?.("info:Title") ?? "";
        } catch {
          title = "";
        }
        self.postMessage({ type: "info", id: msg.id, pageCount, encrypted: false, title, pages });
      } finally {
        doc.destroy?.();
      }
      return;
    }

    if (msg.type === "extract") {
      const { id, pdf, from = 1, to = null, options = {} } = msg;
      const doc = openDoc(pdf, mupdfModule);
      try {
        const pageCount = doc.countPages();
        const last = Math.min(to ?? pageCount, pageCount);
        const pages = [];
        const doubtfulCells = [];
        let ocrPages = 0;
        const warnings = [];
        for (let n = from - 1; n < last; n++) {
          if (cancelledId === id) throw new ConversionError("Conversión cancelada.", "cancelada");
          // El OCR se inicializa solo si la página lo necesita (extractPage
          // solo llama a ocrRunner en páginas escaneadas).
          const ocrRunner =
            options.ocr === false
              ? null
              : async (png) => {
                  const run = await ocrRunnerFactory(options.ocrLang ?? "spa+eng");
                  return run(png);
                };
          const model = await extractPage(doc, n, {
            mupdf: mupdfModule,
            ocr: options.ocr !== false,
            ocrLang: options.ocrLang ?? "spa+eng",
            ocrRunner,
          });
          ocrPages += model.ocrUsed ? 1 : 0;
          const neutral = modelToNeutralPage(model, n + 1);
          // Las imágenes viajan como bytes PNG; la página las convierte a
          // data URL en el hilo principal (btoa no existe en el worker
          // de la misma forma en todos los navegadores).
          neutral.images = neutral.images.map((img) => ({ ...img, png: img.png }));
          pages.push(neutral);
          doubtfulCells.push(...neutral.doubtfulCells);
          self.postMessage({ type: "progress", id, page: n + 1, total: last - from + 1, stage: "extract" });
        }
        const textCoverage =
          pages.length === 0 ? 1 : pages.reduce((s, p) => s + p.quality.text_coverage, 0) / pages.length;
        const numberCoverage =
          pages.length === 0 ? 1 : pages.reduce((s, p) => s + p.quality.number_coverage, 0) / pages.length;
        const missing = pages.flatMap((p) => p.quality.missing_sample).slice(0, 5);
        const warn = ocrWarning(
          pages.flatMap((p) => p.doubtfulCells.map((c) => ({ text: String(c.value), conf: c.confidence ?? 0 }))),
        );
        if (warn) warnings.push(warn);
        self.postMessage({
          type: "extracted",
          id,
          model: {
            pages,
            doubtfulCells,
            quality: { text_coverage: textCoverage, number_coverage: numberCoverage, missing_sample: missing },
            ocr_warning: warnings.join(" ") || "",
            ocrPages,
          },
        });
      } finally {
        doc.destroy?.();
      }
      return;
    }

    if (msg.type === "convert") {
      const { id, pdf, target, options = {} } = msg;
      cancelledId = null;
      const isCancelled = () => cancelledId === id;
      const result = await convertPdf(pdf, target, {
        ...options,
        mupdf: mupdfModule,
        langPath: tessdataUrl,
        corePath: coreUrl,
        workerPath: workerUrl,
        isCancelled,
        onProgress: (page, total, stage) => {
          self.postMessage({ type: "progress", id, page, total, stage });
        },
      });
      self.postMessage(
        { type: "done", id, buffer: result.buffer, filename: result.filename, info: result.info, quality: result.quality },
        [result.buffer.buffer],
      );
      return;
    }

    self.postMessage({ type: "error", error: `Mensaje desconocido: ${msg.type}` });
  } catch (err) {
    const code = err?.code ?? "conversion_fallida";
    const message = err?.message ?? String(err);
    self.postMessage({ type: "error", id: msg?.id ?? null, error: message, code });
  }
};
