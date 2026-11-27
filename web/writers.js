/* Escritores de salida: convierten el MODELO neutro del motor
   (ver web/engine.js) a .xlsx, .docx y .pptx con librerías del
   navegador, y empaquetan varios archivos en un ZIP.
   Las librerías se cargan SOLO cuando hacen falta (carga diferida):
   ExcelJS al convertir a Excel, docx a Word, PptxGenJS a PowerPoint
   y fflate solo para el ZIP. Nada se descarga antes. */
(function () {
  "use strict";

  var cfg = window.PDF_CONVERTER_CONFIG || {};

  /* Rutas de las librerías vendidas en web/vendor/ (o jsDelivr si
     config.js dice vendorBase: "jsdelivr"). Las versiones y huellas
     SRI están en web/vendor/README.md. */
  var VENDOR = {
    fflate: {
      self: "./vendor/fflate/fflate-0.8.2.js",
      jsdelivr: "fflate@0.8.2/umd/index.js",
      global: "fflate",
      sri: "sha384-DT0Ls0mO7JmjTnT+oBuMhEJzYJO1zUqzuuMXNdnOmOQRIpN2BgSjvBV/j50NngIT",
    },
    exceljs: {
      self: "./vendor/exceljs/exceljs-4.4.0.min.js",
      jsdelivr: "exceljs@4.4.0/dist/exceljs.min.js",
      global: "ExcelJS",
      sri: "sha384-Pqp51FUN2/qzfxZxBCtF0stpc9ONI6MYZpVqmo8m20SoaQCzf+arZvACkLkirlPz",
    },
    docx: {
      self: "./vendor/docx/docx-9.16.0.iife.js",
      jsdelivr: "docx@9.16.0/dist/index.iife.js",
      global: "docx",
      sri: "sha384-eFdxP1JJM3+9kl1pilXScRK7wDrzbjpzo5b/tO2ik0evzgsLTFhBAEwhTUmoR4SS",
    },
    pptxgenjs: {
      self: "./vendor/pptxgenjs/pptxgenjs-4.0.1.bundle.js",
      jsdelivr: "pptxgenjs@4.0.1/dist/pptxgen.bundle.js",
      global: "PptxGenJS",
      sri: "sha384-qb0Xhi7LLYpvW1HCK6oMrmDLSY9sy7vwm6ZlV6KjtrlL9yg30+YN4neTwnmX+Kp8",
    },
  };

  function vendorUrl(entry) {
    if (cfg.vendorBase === "jsdelivr") {
      return (cfg.jsdelivrBase || "https://cdn.jsdelivr.net/npm") + "/" + entry.jsdelivr;
    }
    return entry.self;
  }

  var loaded = {};
  function loadScript(name) {
    if (loaded[name]) return loaded[name];
    var entry = VENDOR[name];
    loaded[name] = new Promise(function (resolve, reject) {
      if (window[entry.global]) return resolve(window[entry.global]);
      var s = document.createElement("script");
      s.src = vendorUrl(entry);
      s.async = true;
      if (cfg.vendorBase === "jsdelivr") s.integrity = entry.sri;
      s.crossOrigin = "anonymous";
      s.onload = function () {
        if (window[entry.global]) resolve(window[entry.global]);
        else reject(new Error("La librería " + name + " no se cargó correctamente."));
      };
      s.onerror = function () {
        reject(
          new Error(
            "No se pudo descargar la librería " + name + ". Revisa tu conexión " +
              "y vuelve a intentarlo; si sigue fallando, el archivo no se ha perdido."
          )
        );
      };
      document.head.appendChild(s);
    });
    return loaded[name];
  }

  function cellValue(cell) {
    if (cell == null) return null;
    if (cell.type === "number" && typeof cell.value === "number") return cell.value;
    return cell.value == null ? null : String(cell.value);
  }

  /* El modelo neutro trae cell.fill como hex de 6 dígitos (p. ej. "92D050",
     el color de fondo del PDF). ExcelJS espera ARGB de 8 dígitos
     (alfa + RGB): sin el alfa, el relleno puede quedar transparente y el
     Excel sale sin colores aunque el modelo sí los traiga. */
  function argb(hex) {
    var h = String(hex || "").replace(/^#/, "").toUpperCase();
    if (/^[0-9A-F]{6}$/.test(h)) return "FF" + h;
    if (/^[0-9A-F]{8}$/.test(h)) return h;
    return null;
  }

  function fillStyle(cell) {
    if (cell.doubtful) return { type: "pattern", pattern: "solid", fgColor: { argb: "FFFFF2CC" } };
    var a = cell.fill ? argb(cell.fill) : null;
    if (a) return { type: "pattern", pattern: "solid", fgColor: { argb: a } };
    return null;
  }

  /* ---------- Excel ---------- */
  async function writeExcel(model, options) {
    var ExcelJS = await loadScript("exceljs");
    var wb = new ExcelJS.Workbook();
    wb.creator = "Convertidor PDF (navegador)";
    options = options || {};
    var layout = options.excelLayout || "pages"; // pages | continuous | per-table
    var sheetCount = 0;

    function addSheet(name, tables) {
      var ws = wb.addWorksheet(name.slice(0, 31));
      sheetCount++;
      var rowIndex = 0;
      tables.forEach(function (table, ti) {
        if (layout === "per-table" && ti > 0) return; // una hoja por tabla: se crea fuera
        if (rowIndex > 0) rowIndex += 1; // fila en blanco entre tablas
        table.rows.forEach(function (row) {
          rowIndex++;
          var wsRow = ws.getRow(rowIndex);
          row.forEach(function (cell, ci) {
            var c = wsRow.getCell(ci + 1);
            c.value = cellValue(cell);
            if (cell.type === "number" && typeof cell.value === "number" && cell.numFmt) {
              c.numFmt = cell.numFmt;
            }
            c.font = { bold: !!cell.bold, italic: !!cell.italic };
            var fill = fillStyle(cell);
            if (fill) c.fill = fill;
            if (cell.colspan > 1) ws.mergeCells(rowIndex, ci + 1, rowIndex, ci + cell.colspan);
          });
        });
      });
      ws.columns.forEach(function (col) {
        col.width = Math.min(40, Math.max(12, col.width || 12));
      });
      return ws;
    }

    if (layout === "per-table") {
      model.pages.forEach(function (page) {
        page.tables.forEach(function (table, ti) {
          addSheet("P" + page.pageNumber + " T" + (ti + 1), [table]);
        });
      });
      if (sheetCount === 0) addSheet("Texto", [{ rows: model.pages.map(function (p) { return [{ value: "Página " + p.pageNumber, type: "text", bold: true }].concat(p.texts.map(function (t) { return { value: t.text, type: "text" }; })); }) }]);
    } else if (layout === "continuous") {
      var all = [];
      model.pages.forEach(function (page) {
        page.tables.forEach(function (t) { all.push(t); });
      });
      addSheet("Libro", all);
    } else {
      model.pages.forEach(function (page) {
        addSheet("Página " + page.pageNumber, page.tables);
      });
    }
    if (sheetCount === 0) addSheet("Vacío", [{ rows: [[{ value: "Sin tablas detectadas", type: "text" }]] }]);
    var buffer = await wb.xlsx.writeBuffer();
    return new Blob([buffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  }

  /* ---------- Word ---------- */
  async function writeWord(model, options) {
    var docx = await loadScript("docx");
    var children = [];
    model.pages.forEach(function (page) {
      page.tables.forEach(function (table) {
        var rows = table.rows.map(function (row) {
          return new docx.TableRow({
            children: row.map(function (cell) {
              return new docx.TableCell({
                children: [
                  new docx.Paragraph({
                    children: [
                      new docx.TextRun({
                        text: cellValue(cell) == null ? "" : String(cellValue(cell)),
                        bold: !!cell.bold,
                        italics: !!cell.italic,
                      }),
                    ],
                  }),
                ],
                shading: cell.doubtful ? { fill: "FFF2CC" } : cell.fill ? { fill: cell.fill.replace(/^FF/, "") } : undefined,
                columnSpan: cell.colspan > 1 ? cell.colspan : undefined,
              });
            }),
          });
        });
        children.push(new docx.Table({ rows: rows, width: { size: 100, type: docx.WidthType.PERCENTAGE } }));
      });
      page.texts.forEach(function (t) {
        children.push(new docx.Paragraph({ children: [new docx.TextRun({ text: t.text, bold: !!t.bold })] }));
      });
    });
    if (!children.length) children.push(new docx.Paragraph("Sin contenido detectable."));
    var doc = new docx.Document({ sections: [{ children: children }] });
    var blob = await docx.Packer.toBlob(doc);
    return blob;
  }

  /* ---------- PowerPoint ---------- */
  async function writePptx(model, options) {
    var PptxGenJS = await loadScript("pptxgenjs");
    var pptx = new PptxGenJS();
    pptx.defineLayout({ name: "PANORAMICA", width: 13.33, height: 7.5 });
    pptx.layout = "PANORAMICA";
    model.pages.forEach(function (page) {
      var slide = pptx.addSlide();
      slide.addText("Página " + page.pageNumber, { x: 0.4, y: 0.2, fontSize: 12, bold: true, color: "666666" });
      var y = 0.6;
      page.tables.forEach(function (table) {
        var rows = table.rows.map(function (row) {
          return row.map(function (cell) {
            return {
              text: cellValue(cell) == null ? "" : String(cellValue(cell)),
              options: {
                bold: !!cell.bold,
                italic: !!cell.italic,
                fill: cell.doubtful ? { color: "FFF2CC" } : cell.fill ? { color: cell.fill.replace(/^FF/, "") } : undefined,
              },
            };
          });
        });
        slide.addTable(rows, { x: 0.4, y: y, w: 12.5, fontSize: 11, border: { pt: 0.5, color: "CCCCCC" } });
        y += 0.35 + rows.length * 0.32;
      });
      page.texts.forEach(function (t) {
        slide.addText(t.text, { x: 0.4, y: y, w: 12.5, fontSize: 12, bold: !!t.bold });
        y += 0.3;
      });
    });
    if (!model.pages.length) pptx.addSlide().addText("Sin contenido detectable.", { x: 0.4, y: 0.4 });
    var blob = await pptx.write({ outputType: "blob" });
    return blob;
  }

  /* ---------- ZIP (varios archivos) ---------- */
  async function zipFiles(files) {
    var fflate = await loadScript("fflate");
    var data = {};
    files.forEach(function (f) { data[f.name] = f.data; });
    var zipped = fflate.zipSync(data, { level: 6 });
    return new Blob([zipped], { type: "application/zip" });
  }

  window.PdfWriters = {
    writeExcel: writeExcel,
    writeWord: writeWord,
    writePptx: writePptx,
    zipFiles: zipFiles,
    vendorInfo: VENDOR,
  };
})();

