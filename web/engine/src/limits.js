/** Límites anti-abuso del motor (se aplican en el worker, en el dispositivo del usuario). */
import { ConversionError } from "./errors.js";

export const LIMITS = {
  /** Tamaño máximo del PDF de entrada (50 MB, como el backend). */
  maxPdfBytes: 50 * 1024 * 1024,
  /** Máximo de páginas por documento. */
  maxPages: 200,
  /** Ancho/alto máximo de página en puntos (~1 m). */
  maxPageDimensionPt: 3000,
  /** Área máxima de página en puntos² (evita páginas gigantes). */
  maxPageAreaPt2: 4_000_000,
  /** Máximo de objetos del PDF (el contador de MuPDF). */
  maxPdfObjects: 200_000,
  /** Máximo de caracteres extraídos por página. */
  maxCharsPerPage: 200_000,
  /** Máximo de objetos vectoriales por página. */
  maxDrawingsPerPage: 50_000,
  /** Máximo de imágenes por página. */
  maxImagesPerPage: 200,
  /** Píxeles máximos de una imagen decodificada (ancho × alto). */
  maxDecodedImagePixels: 100_000_000,
  /** Tiempo máximo por página en ms (extracción + OCR). */
  maxMsPerPage: 120_000,
  /** Tiempo máximo total de la conversión en ms. */
  maxTotalMs: 600_000,
};

function fail(message) {
  throw new ConversionError(message, "limite_excedido");
}

export function checkPdfSize(bytes) {
  if (bytes > LIMITS.maxPdfBytes) {
    fail(
      `El PDF pesa ${(bytes / 1024 / 1024).toFixed(1)} MB y el límite es 50 MB. ` +
        "Divide el documento o comprímelo e inténtalo de nuevo.",
    );
  }
}

export function checkPageCount(n) {
  if (n > LIMITS.maxPages) {
    fail(`El PDF tiene ${n} páginas y el límite es ${LIMITS.maxPages} por conversión.`);
  }
}

export function checkPageDimensions(width, height) {
  if (
    width > LIMITS.maxPageDimensionPt ||
    height > LIMITS.maxPageDimensionPt ||
    width * height > LIMITS.maxPageAreaPt2
  ) {
    fail(
      `La página mide ${Math.round(width)} × ${Math.round(height)} puntos, más grande de lo admitido.`,
    );
  }
}

export function checkPdfObjects(n) {
  if (n > LIMITS.maxPdfObjects) {
    fail(`El PDF tiene ${n.toLocaleString("es")} objetos, más de lo admitido (${LIMITS.maxPdfObjects.toLocaleString("es")}).`);
  }
}

export function checkPageModel(model) {
  if (model.spans.length > LIMITS.maxCharsPerPage) {
    fail("La página tiene demasiado texto para procesarla de forma segura.");
  }
  if (model.lines.length + model.fills.length > LIMITS.maxDrawingsPerPage) {
    fail("La página tiene demasiados elementos de dibujo para procesarla de forma segura.");
  }
  if (model.images.length > LIMITS.maxImagesPerPage) {
    fail("La página tiene demasiadas imágenes para procesarla de forma segura.");
  }
  for (const img of model.images) {
    if (img.pixelWidth * img.pixelHeight > LIMITS.maxDecodedImagePixels) {
      fail("Una imagen del PDF es demasiado grande para decodificarla de forma segura.");
    }
  }
}
