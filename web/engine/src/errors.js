/** Errores de conversión con mensaje claro en español para el usuario final. */
export class ConversionError extends Error {
  /**
   * @param {string} message mensaje en español
   * @param {string} code código estable: 'pdf_invalido' | 'pdf_cifrado' | 'pdf_corrupto' |
   *   'limite_excedido' | 'cancelado' | 'sin_texto' | 'ocr_no_disponible' | 'conversion_fallida'
   */
  constructor(message, code = "conversion_fallida") {
    super(message);
    this.name = "ConversionError";
    this.code = code;
  }
}

export class ConversionCancelled extends ConversionError {
  constructor(message = "Conversión cancelada por el usuario.") {
    super(message, "cancelado");
    this.name = "ConversionCancelled";
  }
}

/** Lanza el error en español que corresponde a un fallo de apertura del PDF. */
export function pdfOpenError(err) {
  const msg = String(err?.message ?? err ?? "");
  if (/password|encrypted|decrypt/i.test(msg)) {
    return new ConversionError(
      "El PDF está protegido con contraseña y no se puede abrir. Quita la contraseña e inténtalo de nuevo.",
      "pdf_cifrado",
    );
  }
  if (/damaged|corrupt|invalid|trailer|xref|not a pdf|no document|format|no objects|unknown file|failed to load/i.test(msg)) {
    return new ConversionError(
      "El archivo no parece un PDF válido o está dañado. Revisa el archivo e inténtalo de nuevo.",
      "pdf_corrupto",
    );
  }
  return new ConversionError(
    `No se pudo abrir el PDF (${msg || "error desconocido"}).`,
    "pdf_invalido",
  );
}
