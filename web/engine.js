/* Cargador del motor de conversión del navegador (web/engine/).
   ============================================================
   CONTRATO DEL MOTOR — lo que web/engine/index.js debe exponer:
   ------------------------------------------------------------
   Al cargarse, el motor deja en `window.PdfConverterEngine` un objeto
   con estos métodos (todos devuelven promesas):

   - ENGINE_VERSION: texto, p. ej. "1.0.0 (MuPDF.js 1.28.0)".
   - engineName: texto legible, p. ej. "MuPDF.js".
   - supportsOCR: true/false (¿puede leer PDFs escaneados?).
   - load(onProgress) — descarga e inicializa el motor. onProgress es
     una función (fracción 0..1, mensaje) que la web usa para la barra.
   - open(arrayBuffer, nombreArchivo) — abre el PDF y devuelve:
       { pageCount, encrypted, title,
         pages: [{ width, height, hasText }] }
     Si el PDF tiene contraseña, lanza Error("encrypted").
     Si el PDF está roto o no es un PDF, lanza Error("invalid").
   - renderPage(doc, indicePagina, canvas, escala) — dibuja la página
     en el canvas dado (vista previa).
   - extract(doc, { from, to, onProgress }) — extrae el contenido del
     rango de páginas y devuelve el MODELO neutro:
       { pages: [ { pageNumber, scanned, tables, texts, images } ],
         doubtfulCells: [ { page, table, row, col, value, confidence } ],
         quality: { text_coverage, number_coverage, missing_sample },
         ocr_warning: "" | "texto en español…" }
     Cada tabla: { rows: [ [ celda, … ], … ] } y cada celda:
       { value, type: "number"|"text"|"date", bold, italic, fill,
         numFmt, colspan, rowspan, doubtful, confidence }
     Los textos sueltos (fuera de tabla) van en `texts` como
     { text, bold, size } y las imágenes en `images` como
     { dataUrl, width, height }.
   - dispose(doc) — libera el documento (opcional).

   MODO DE DEMOSTRACIÓN: si web/engine/ aún no existe (el motor lo está
   construyendo otro agente), este cargador NO rompe la página: la web
   sigue mostrando la vista previa del PDF con pdf.js y explica con
   claridad que la conversión aún no está lista. Nada se inventa: el
   botón «Convertir» queda desactivado hasta que haya motor o servidor.
   ============================================================ */
(function () {
  "use strict";

  var ENGINE_URL = "./engine/index.js";

  function engineMissingError() {
    var e = new Error(
      "El motor de conversión del navegador aún no está instalado " +
        "(falta web/engine/index.js). La vista previa del PDF sí funciona, " +
        "pero convertir todavía no. Si el dueño ya activó el servidor " +
        "opcional, usa ese camino; si no, espera a la próxima versión."
    );
    e.code = "ENGINE_MISSING";
    return e;
  }

  /* Intenta cargar el motor. Resuelve con el objeto del motor o rechaza
     con un error con `code` = "ENGINE_MISSING" si no existe. */
  async function loadEngine(onProgress) {
    if (window.PdfConverterEngine && window.PdfConverterEngine.load) {
      return window.PdfConverterEngine;
    }
    var res;
    try {
      res = await fetch(ENGINE_URL, { method: "HEAD", cache: "no-store" });
    } catch (err) {
      throw engineMissingError();
    }
    if (!res.ok) throw engineMissingError();
    try {
      await import(ENGINE_URL);
    } catch (err) {
      throw engineMissingError();
    }
    if (!window.PdfConverterEngine || !window.PdfConverterEngine.load) {
      throw engineMissingError();
    }
    var engine = window.PdfConverterEngine;
    if (typeof onProgress === "function") onProgress(0, "Cargando el motor…");
    await engine.load(onProgress);
    if (typeof onProgress === "function") onProgress(1, "Motor listo.");
    return engine;
  }

  /* ¿Está el motor instalado? (sin descargarlo: solo comprueba el archivo). */
  async function engineAvailable() {
    if (window.PdfConverterEngine) return true;
    try {
      var res = await fetch(ENGINE_URL, { method: "HEAD", cache: "no-store" });
      return res.ok;
    } catch (err) {
      return false;
    }
  }

  window.PdfConverterEngineLoader = {
    loadEngine: loadEngine,
    engineAvailable: engineAvailable,
  };
})();
