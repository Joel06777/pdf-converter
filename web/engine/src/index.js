/**
 * API pública del motor de conversión en el navegador.
 *
 * Uso en Node (pruebas y herramientas):
 *   import { convertPdf } from "./src/index.js";
 *   const { buffer, quality } = await convertPdf(pdfBytes, "excel");
 *
 * Uso en el navegador (Web Worker): ver src/worker.js. La página solo
 * entrega estáticos; la conversión ocurre en el dispositivo del usuario.
 */
export { convertPdf, TARGETS } from "./convert.js";
export { extractPage, groupRows } from "./extract.js";
export { buildLayout } from "./layout.js";
export { parseNumber } from "./numbers.js";
export { OcrEngine, ocrWarning } from "./ocr.js";
export { ConversionError, ConversionCancelled } from "./errors.js";
export { LIMITS } from "./limits.js";
export { modelsToExcel } from "./excel.js";
export { modelsToPptx } from "./pptx.js";
export { modelsToWord } from "./word.js";
export { ENGINE_VERSION } from "./version.js";
