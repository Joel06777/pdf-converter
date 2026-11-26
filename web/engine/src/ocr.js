/**
 * OCR en el navegador con tesseract.js 7 (Apache-2.0), idiomas spa+eng.
 *
 * El worker de Tesseract se crea SOLO cuando un PDF no tiene texto nativo.
 * Los datos de idioma (spa.traineddata.gz, eng.traineddata.gz, tessdata_fast)
 * se sirven desde el mismo origen que la página (ruta `langPath`); nunca se
 * descarga nada de terceros durante la conversión.
 *
 * Correcciones aplicadas a las palabras reconocidas (medidas en el backend
 * Python, ver docs/METRICAS.md): el símbolo Nº se lee casi siempre como
 * "N?", "N*" o "N®"; se restaura a "Nº".
 */
import { createWorker } from "tesseract.js";

export const LOW_CONFIDENCE = 60;

/** Correcciones de OCR por palabra (no tocan cifras). */
export function fixOcrWord(text) {
  if (["N?", "N*", "N®", "No", "N°"].includes(text)) return "Nº";
  return text;
}

/**
 * Motor de OCR reutilizable entre páginas.
 * @param {object} opts { langPath?: string, corePath?: string, workerPath?: string, lang?: string }
 */
export class OcrEngine {
  constructor(opts = {}) {
    this.lang = opts.lang ?? "spa+eng";
    this.langPath = opts.langPath ?? null;
    this.corePath = opts.corePath ?? null;
    this.workerPath = opts.workerPath ?? null;
    this.worker = null;
    this.ready = false;
  }

  async init() {
    if (this.ready) return;
    const options = { cacheMethod: "none" };
    if (this.langPath) options.langPath = this.langPath;
    if (this.corePath) options.corePath = this.corePath;
    if (this.workerPath) options.workerPath = this.workerPath;
    this.worker = await createWorker(this.lang, 1, options);
    this.ready = true;
  }

  /**
   * Reconoce una página (PNG gris binarizado) y devuelve palabras con
   * posición en PÍXELES de la imagen de entrada y confianza:
   * [{text, x0, y0, x1, y1, conf}].
   *
   * La conversión a puntos de página la hace el llamador (extract.js), que
   * es quien conoce las rotaciones aplicadas al preprocesar (enderezado y
   * giros de 90°) y debe invertirlas antes de escalar.
   */
  async recognizePage(pngBytes, onProgress = null) {
    await this.init();
    const { data } = await this.worker.recognize(pngBytes, {}, { blocks: true });
    const words = [];
    const collect = (blocks) => {
      for (const block of blocks ?? []) {
        for (const para of block.paragraphs ?? []) {
          for (const line of para.lines ?? []) {
            for (const w of line.words ?? []) {
              if (!w.text?.trim()) continue;
              words.push(w);
            }
          }
        }
      }
    };
    collect(data.blocks);
    const out = words.map((w) => ({
      text: fixOcrWord(w.text),
      x0: w.bbox.x0,
      y0: w.bbox.y0,
      x1: w.bbox.x1,
      y1: w.bbox.y1,
      conf: typeof w.confidence === "number" ? w.confidence : 0,
    }));
    if (onProgress) onProgress(out.length);
    return out;
  }

  async terminate() {
    if (this.worker) {
      await this.worker.terminate();
      this.worker = null;
      this.ready = false;
    }
  }
}

/** Palabras con confianza baja, en español y sin duplicados (para la advertencia). */
export function lowConfidenceWords(confidences, threshold = LOW_CONFIDENCE) {
  const seen = [];
  for (const w of confidences ?? []) {
    if (w.conf < threshold && !seen.includes(w.text)) seen.push(w.text);
  }
  return seen;
}

/** Advertencia en español si el OCR tiene palabras dudosas, o null. */
export function ocrWarning(confidences) {
  const low = lowConfidenceWords(confidences);
  if (!low.length) return null;
  const muestra = low.slice(0, 8).join(", ");
  const extra = low.length > 8 ? ` y ${low.length - 8} más` : "";
  return (
    `El reconocimiento de texto (OCR) tiene baja confianza en algunas palabras ` +
    `(${muestra}${extra}). Revisa esas celdas antes de usar el archivo.`
  );
}
