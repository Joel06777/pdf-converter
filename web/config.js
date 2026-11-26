/* Configuración de la web del convertidor.
   Cambia SOLO los valores de este archivo: nada más del código depende
   de dónde se sirvan las librerías ni de si hay servidor opcional.
   Todo en español y sin secretos: aquí no va ninguna clave. */
(function () {
  "use strict";

  var CONFIG = {
    /* Origen de las librerías del navegador (las que escriben .xlsx, .docx,
       .pptx, el ZIP y la vista previa del PDF).
       - "self": se sirven desde web/vendor/ junto a esta página (lo
         recomendado: funciona sin conexión tras la primera visita y no
         depende de nadie).
       - "jsdelivr": se cargan desde la CDN pública jsDelivr
         (https://cdn.jsdelivr.net). Para cambiar, pon "jsdelivr" aquí y
         nada más: los archivos, versiones e integridad (SRI) son los
         mismos, solo cambia la base de la URL. Ver web/README.md.
       El motor de conversión (web/engine/) SIEMPRE se sirve desde el
       mismo sitio: es código propio y no va por CDN de terceros. */
    vendorBase: "self",

    /* Base de jsDelivr para las mismas versiones fijadas en web/vendor/.
       No la toques salvo que sepas lo que haces: las versiones están
       fijadas con su huella SRI en web/vendor/README.md. */
    jsdelivrBase: "https://cdn.jsdelivr.net/npm",

    /* Servidor opcional (docs/SERVIDOR_OPCIONAL.md). Por defecto APAGADO:
       la conversión ocurre en el navegador y el archivo no sale del
       dispositivo. Si algún día activas el servidor propio, pon aquí su
       URL pública (por ejemplo "https://convertidor.tu-dominio.com") y
       la web lo usará SOLO como respaldo cuando el motor del navegador
       no pueda con un documento, avisando antes al usuario. */
    serverUrl: "",

    /* Formulario de incidencias de GitHub (se abre prellenado). */
    issueFormUrl:
      "https://github.com/Joel06777/pdf-converter/issues/new",

    /* Repositorio público del código fuente (enlace visible en el pie). */
    sourceRepoUrl: "https://github.com/Joel06777/pdf-converter",

    /* Versión de esta web (la misma que en CHANGELOG.md). */
    webVersion: "1.1.0-sin-publicar",
  };

  window.PDF_CONVERTER_CONFIG = CONFIG;
})();
