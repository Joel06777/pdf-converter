/**
 * Orquestador de la conversión: abre el PDF con MuPDF.js, extrae el modelo
 * de cada página (con OCR solo donde hace falta), genera el destino y verifica
 * la cobertura contra el texto del PDF.
 *
 * Un solo modelo intermedio alimenta los tres destinos. La verificación
 * aritmética (subtotal + IVA = total) solo avisa: jamás cambia un valor.
 *
 * MuPDF NO se importa estático aquí: su salida de Emscripten se rompe al
 * empaquetarla con Vite/Rolldown (ver src/worker.js). En Node se carga
 * perezoso con import dinámico; en el navegador el worker ya lo trae
 * cargado (init con mupdfUrl) y se pasa en opts.mupdf.
 */
import { ConversionCancelled, ConversionError, pdfOpenError } from "./errors.js";
import { extractPage } from "./extract.js";
import { modelsToExcel } from "./excel.js";
import { checkPageCount, checkPdfObjects, checkPdfSize, LIMITS } from "./limits.js";
import { OcrEngine, ocrWarning } from "./ocr.js";
import { modelsToPptx } from "./pptx.js";
import { compareCoverage, docxTokens, pdfTokensFromSpans, pptxTokens, xlsxTokens } from "./verify.js";
import { modelsToWord } from "./word.js";
import { buildLayout, checkTotals } from "./layout.js";

export const TARGETS = ["excel", "word", "pptx"];

/**
 * Convierte un PDF (bytes) al destino pedido.
 * @param {Uint8Array|ArrayBuffer} pdfBytes
 * @param {'excel'|'word'|'pptx'} target
 * @param {object} opts {
 *   layout?: 'pages'|'continuous', formulas?: boolean, mode?: 'auto'|'grid'|'flow'|'ocr',
 *   ocr?: boolean, ocrLang?: string, langPath?: string, corePath?: string, workerPath?: string,
 *   mupdf?: object, onProgress?: (page, total) => void, isCancelled?: () => boolean
 * }
 * @returns {Promise<{ buffer: Uint8Array, filename: string, info: object, quality: object }>}
 */
export async function convertPdf(pdfBytes, target, opts = {}) {
  if (!TARGETS.includes(target)) {
    throw new ConversionError(`Destino no soportado: ${target}.`, "conversion_fallida");
  }
  const bytes = pdfBytes instanceof Uint8Array ? pdfBytes : new Uint8Array(pdfBytes);
  checkPdfSize(bytes.length);
  const {
    layout = "pages",
    formulas = true,
    mode = "auto",
    ocr = true,
    ocrLang = "spa+eng",
    langPath = null,
    corePath = null,
    workerPath = null,
    mupdf: mupdfOpt = null,
    onProgress = null,
    isCancelled = null,
  } = opts;

  // Carga perezosa: en Node resuelve por node_modules; en el navegador el
  // worker siempre pasa el módulo ya cargado, así que nunca se ejecuta aquí.
  const mupdf = mupdfOpt ?? (await import(/* @vite-ignore */ "mupdf"));

  const cancelled = () => {
    if (isCancelled && isCancelled()) throw new ConversionCancelled();
  };

  const tStart = Date.now();
  let doc;
  try {
    doc = mupdf.Document.openDocument(bytes, "application/pdf");
  } catch (err) {
    throw pdfOpenError(err);
  }

  let ocrEngine = null;
  const ocrRunner = async (png) => {
    if (!ocrEngine) {
      ocrEngine = new OcrEngine({ lang: ocrLang, langPath, corePath, workerPath });
      await ocrEngine.init();
    }
    return ocrEngine.recognizePage(png);
  };

  try {
    const pageCount = doc.countPages();
    checkPageCount(pageCount);
    if (typeof doc.countObjects === "function") {
      checkPdfObjects(doc.countObjects());
    }
    const models = [];
    const warnings = [];
    let ocrPages = 0;
    let scannedPages = 0;
    for (let n = 0; n < pageCount; n++) {
      cancelled();
      if (Date.now() - tStart > LIMITS.maxTotalMs) {
        throw new ConversionError("La conversión tardó demasiado y se detuvo.", "limite_excedido");
      }
      const pageStart = Date.now();
      const model = await extractPage(doc, n, {
        mupdf,
        ocr,
        ocrLang,
        ocrRunner,
        onOcrProgress: null,
      });
      if (Date.now() - pageStart > LIMITS.maxMsPerPage) {
        throw new ConversionError(`La página ${n + 1} tardó demasiado en procesarse.`, "limite_excedido");
      }
      models.push(model);
      ocrPages += model.ocrUsed ? 1 : 0;
      scannedPages += model.scanned ? 1 : 0;
      if (onProgress) onProgress(n + 1, pageCount, "extract");
    }

    // Tokens esperados del PDF (solo páginas con texto nativo: las escaneadas
    // no son verificables contra sí mismas, como en Python).
    const nativeModels = models.filter((m) => m.nativeChars >= 20);
    const expectedTokens =
      nativeModels.length > 0 ? pdfTokensFromSpans(nativeModels.flatMap((m) => m.spans)) : null;

    // Verificación aritmética (solo avisa, jamás cambia valores).
    const totalsWarnings = [];
    for (const model of models) {
      const lay = buildLayout(model);
      const t = checkTotals(lay.placements);
      if (t) totalsWarnings.push(t.message);
    }
    if (totalsWarnings.length) warnings.push(...totalsWarnings);

    cancelled();
    let out;
    if (target === "excel") {
      out = await modelsToExcel(models, { layout, formulas, onProgress: (p, t) => onProgress?.(p, t, "generate") });
    } else if (target === "pptx") {
      out = await modelsToPptx(models, { onProgress: (p, t) => onProgress?.(p, t, "generate") });
    } else {
      out = await modelsToWord(models, {
        mode,
        expectedTokens,
        onProgress: (p, t) => onProgress?.(p, t, "generate"),
      });
    }

    // Advertencias de OCR (palabras dudosas).
    const allConf = models.flatMap((m) => m.ocrConfidences ?? []);
    const warn = ocrWarning(allConf);
    if (warn) warnings.push(warn);
    if (out.info?.totalsWarning && !warnings.includes(out.info.totalsWarning)) {
      warnings.push(out.info.totalsWarning);
    }

    // Verificación de cobertura contra el archivo generado.
    let quality;
    try {
      const got =
        target === "excel"
          ? await xlsxTokens(out.buffer)
          : target === "word"
            ? docxTokens(out.buffer)
            : pptxTokens(out.buffer);
      quality = compareCoverage(expectedTokens, got);
    } catch (err) {
      quality = { verifiable: false, reason: `No se pudo verificar el archivo generado: ${err.message}` };
    }

    return {
      buffer: out.buffer,
      filename: `documento.${target === "excel" ? "xlsx" : target === "word" ? "docx" : "pptx"}`,
      info: {
        ...out.info,
        pages: pageCount,
        ocrPages,
        scannedPages,
        target,
        layout: target === "excel" ? layout : undefined,
        mode: target === "word" ? mode : undefined,
        warnings,
        ms: Date.now() - tStart,
      },
      quality,
    };
  } finally {
    if (ocrEngine) await ocrEngine.terminate().catch(() => {});
    try {
      doc.destroy?.();
    } catch {
      // MuPDF.js no siempre expone destroy en Document
    }
  }
}
