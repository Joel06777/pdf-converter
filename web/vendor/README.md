# Librerías del navegador (vendidas en `web/vendor/`)

Las librerías se sirven desde el propio sitio junto a la página
(`config.js`: `vendorBase: "self"`). Así la web funciona sin conexión
tras la primera visita y no depende de ningún tercero. Si algún día se
sirven desde jsDelivr, se usan estas mismas versiones con la huella
SRI (sha384) de la tabla.

Verificación (26 nov 2026): versión y licencia leídas del
`package.json` y del archivo `LICENSE` de cada paquete descargado de
npm, contrastadas con la ficha de npm y el repositorio oficial. Esto
no es asesoría legal.

| Archivo | Paquete | Versión | Licencia | Tamaño | gzip | Huella SRI (sha384) |
|---|---|---|---|---|---|---|
| `fflate/fflate-0.8.2.js` | fflate | 0.8.2 | MIT | 32.665 B | 12.525 B | `sha384-DT0Ls0mO7JmjTnT+oBuMhEJzYJO1zUqzuuMXNdnOmOQRIpN2BgSjvBV/j50NngIT` |
| `exceljs/exceljs-4.4.0.min.js` | exceljs | 4.4.0 | MIT | 947.702 B | 257.936 B | `sha384-Pqp51FUN2/qzfxZxBCtF0stpc9ONI6MYZpVqmo8m20SoaQCzf+arZvACkLkirlPz` |
| `docx/docx-9.16.0.iife.js` | docx | 9.16.0 | MIT | 1.061.739 B | 231.856 B | `sha384-eFdxP1JJM3+9kl1pilXScRK7wDrzbjpzo5b/tO2ik0evzgsLTFhBAEwhTUmoR4SS` |
| `pptxgenjs/pptxgenjs-4.0.1.bundle.js` | pptxgenjs | 4.0.1 | MIT | 460.889 B | 157.280 B | `sha384-qb0Xhi7LLYpvW1HCK6oMrmDLSY9sy7vwm6ZlV6KjtrlL9yg30+YN4neTwnmX+Kp8` |
| `pdfjs/pdf-5.5.207.min.mjs` | pdfjs-dist | 5.5.207 | Apache-2.0 | 425.269 B | 120.582 B | `sha384-786Q/eJLyI15EFOSaF5q7TTNwWCnLloYJEp0wYXWmSFzAKPu8WBxUchjpTvoSVtv` |
| `pdfjs/pdf-5.5.207.worker.min.mjs` | pdfjs-dist | 5.5.207 | Apache-2.0 | 1.239.047 B | 366.137 B | `sha384-lhv6DIzz0XlkRVjXOxrDvC/QyumqzYhWN6adAAtkINF2VyJ+qgLBWM9P22v9GVBJ` |

Total vendido: **4.167.311 B** (4,0 MB); con gzip (lo que baja el
navegador, con Brotli es algo menos): **1.146.316 B** (1,1 MB).
El motor (`web/engine/`, otro agente) y los datos de idioma del OCR
no están en esta tabla: los mide y documenta quien los construya.

**Qué hace cada una:**

- **fflate** (MIT, <https://github.com/101arrowz/fflate>): crea el ZIP
  cuando se descargan varios resultados juntos. Solo se descarga si se
  pide un ZIP.
- **exceljs** (MIT, <https://github.com/exceljs/exceljs>): escribe el
  `.xlsx`. Solo se descarga al convertir a Excel.
- **docx** (MIT, <https://github.com/dolanmiu/docx>): escribe el `.docx`.
  Solo se descarga al convertir a Word.
- **pptxgenjs** (MIT, <https://github.com/gitbrent/PptxGenJS>): escribe
  el `.pptx`. Solo se descarga al convertir a PowerPoint.
- **pdfjs-dist** (Apache-2.0, <https://github.com/mozilla/pdf.js>):
  vista previa del PDF original (renderiza la página en un canvas).
  Solo se descarga al abrir la vista previa. El worker es el proceso
  que hace el trabajo pesado en segundo plano.

**Globales que expone cada archivo** (lo que usa `writers.js` y `app.js`):

- fflate → `window.fflate` · exceljs → `window.ExcelJS` ·
  docx → `window.docx` · pptxgenjs → `window.PptxGenJS` ·
  pdf.js se importa como módulo ES (`import ... from "./pdf-5.5.207.min.mjs"`).

**Compatibilidad con la licencia del proyecto (AGPL-3.0):** MIT y
Apache-2.0 son permisivas y compatibles con publicar el servicio bajo
AGPL-3.0. Ninguna de estas librerías impone copyleft al proyecto.
El motor del navegador (MuPDF.js, AGPL-3.0-or-later) sí es copyleft:
ver `docs/LICENCIAS.md`.

**Para actualizar una librería:** descarga la versión nueva de npm,
copia el archivo con el nuevo nombre versionado, actualiza la ruta y
la huella SRI en `writers.js`/`app.js` y en esta tabla, y revisa su
licencia en `docs/LICENCIAS.md`. Nunca uses una versión sin fijar
(`latest`): un cambio silencioso rompería la huella SRI.
