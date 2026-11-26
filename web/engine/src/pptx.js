/**
 * PDF → PowerPoint (.pptx) con pptxgenjs 4.0.1 (MIT).
 *
 * Traducción de app/converters/pdf_to_pptx.py: cada página es una diapositiva
 * del mismo tamaño; todo queda editable (texto en cuadros de texto, rellenos
 * y líneas como formas, imágenes como imágenes). Las páginas tabulares se
 * convierten en tablas nativas de PowerPoint. En páginas escaneadas se coloca
 * la imagen de fondo y el texto reconocido va a las notas de la diapositiva.
 */
import PptxGenJS from "pptxgenjs";
import { groupRows } from "./extract.js";
import { buildLayout, verticalMerges } from "./layout.js";
import { parseNumber } from "./numbers.js";

const PT_TO_IN = 1 / 72;

function normalizeRotation(angle) {
  let a = angle;
  while (a > 90) a -= 180;
  while (a < -90) a += 180;
  return a;
}

function isTablePage(model) {
  const rows = groupRows(model.spans);
  if (rows.length < 5) return false;
  const multi = rows.filter((r) => r.segments.length >= 2);
  const numeric = multi.filter((r) => r.segments.some((s) => parseNumber(s.text)));
  return multi.length >= 0.4 * rows.length && numeric.length >= 3;
}

function runsForText(text, seg) {
  const lines = text.split("\n");
  return lines.map((line, k) => ({
    text: line,
    options: {
      fontFace: seg.font,
      fontSize: seg.size,
      bold: seg.bold,
      italic: seg.italic,
      color: seg.color,
      breakLine: k < lines.length - 1,
    },
  }));
}

function addNativeTable(slide, model) {
  const lay = buildLayout(model);
  const { rows, cols, bounds } = lay;
  if (rows.length < 2 || cols.length < 2) return false;
  const tableRows = [];
  const grid = new Map();
  for (const pl of lay.placements) {
    grid.set(`${pl.row},${pl.col}`, pl);
  }
  // Celdas cubiertas por fusiones: se dejan vacías; pptxgenjs emite el
  // gridSpan/vMerge al ver colspan/rowspan en la celda origen.
  // (pptxgenjs 4.0.1 acepta `colspan`/`rowspan` en minúscula aunque sus tipos
  // no los declaren; lo emite como gridSpan/rowSpan en el XML.)
  const covered = new Set();
  const vmerges = verticalMerges(model, lay);
  for (const [top, j, bottom] of vmerges) {
    for (let i = top + 1; i <= bottom; i++) covered.add(`${i},${j}`);
  }
  for (let i = 0; i < rows.length; i++) {
    const rowCells = [];
    for (let j = 0; j < cols.length; j++) {
      const pl = grid.get(`${i},${j}`);
      const fill = lay.fills.get(`${i},${j}`);
      const border = lay.borders.get(`${i},${j}`);
      const cellOpts = {
        fill: fill ? { color: fill } : undefined,
        valign: "middle",
        margin: [0, 0, 0, 0],
        color: pl ? pl.seg.color : "000000",
        fontFace: pl ? pl.seg.font : "Calibri",
        fontSize: pl ? pl.seg.size : 10,
        bold: pl ? pl.seg.bold : false,
        italic: pl ? pl.seg.italic : false,
        align: pl ? pl.horizontal : "left",
      };
      if (border) {
        const side = (s) => (s ? { color: s.color, pt: Math.max(0.25, s.width) } : undefined);
        cellOpts.border = {
          top: side(border.top),
          left: side(border.left),
          bottom: side(border.bottom),
          right: side(border.right),
        };
      }
      if (pl && pl.mergeTo !== null && pl.mergeTo > pl.col) {
        cellOpts.colspan = pl.mergeTo - pl.col + 1;
        for (let c = pl.col + 1; c <= pl.mergeTo; c++) covered.add(`${i},${c}`);
      }
      const vm = vmerges.find(([top, jj]) => top === i && jj === j);
      if (vm) {
        cellOpts.rowspan = vm[2] - vm[0] + 1;
      }
      const isCovered = covered.has(`${i},${j}`);
      rowCells.push({
        text: pl && !isCovered ? runsForText(pl.seg.text, pl.seg) : "",
        options: cellOpts,
      });
    }
    tableRows.push(rowCells);
  }
  try {
    slide.addTable(tableRows, {
      x: cols[0].left * PT_TO_IN,
      y: bounds[0] * PT_TO_IN,
      w: (cols[cols.length - 1].right - cols[0].left) * PT_TO_IN,
      h: (bounds[bounds.length - 1] - bounds[0]) * PT_TO_IN,
      colW: cols.map((c) => (c.right - c.left) * PT_TO_IN),
      rowH: rows.map((_, i) => Math.max(1, bounds[i + 1] - bounds[i]) * PT_TO_IN),
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Convierte los modelos de página ya extraídos a un .pptx.
 * @param {Array} models modelos de página (de extractPage)
 * @param {object} opts { onProgress?: fn }
 * @returns {Promise<{ buffer: Uint8Array, info: object }>}
 */
export async function modelsToPptx(models, opts = {}) {
  const { onProgress = null } = opts;
  const pptx = new PptxGenJS();
  const first = models[0];
  pptx.defineLayout({ name: "PAGE", width: first.width * PT_TO_IN, height: first.height * PT_TO_IN });
  pptx.layout = "PAGE";
  const info = { pages: models.length, ocrPages: 0 };

  for (let n = 0; n < models.length; n++) {
    const model = models[n];
    const slide = pptx.addSlide();
    const rows = groupRows(model.spans);

    for (const img of model.images) {
      slide.addImage({
        data: `data:image/png;base64,${Buffer.from(img.png).toString("base64")}`,
        x: img.x0 * PT_TO_IN,
        y: img.y0 * PT_TO_IN,
        w: (img.x1 - img.x0) * PT_TO_IN,
        h: (img.y1 - img.y0) * PT_TO_IN,
      });
    }

    if (model.scanned && model.images.length) {
      const text = rows.map((r) => r.segments.map((s) => s.text).join("  ")).join("\n");
      if (text) slide.addNotes(text);
      info.ocrPages += model.ocrUsed ? 1 : 0;
      if (onProgress) onProgress(n + 1, models.length);
      continue;
    }

    if (isTablePage(model) && addNativeTable(slide, model)) {
      if (onProgress) onProgress(n + 1, models.length);
      continue;
    }

    for (const f of model.fills) {
      slide.addShape(pptx.shapes.RECTANGLE, {
        x: f.x0 * PT_TO_IN,
        y: f.y0 * PT_TO_IN,
        w: (f.x1 - f.x0) * PT_TO_IN,
        h: (f.y1 - f.y0) * PT_TO_IN,
        fill: { color: f.color },
        line: { color: f.color, width: 0 },
      });
    }

    for (const ln of model.lines) {
      if (ln.orient === "h") {
        slide.addShape(pptx.shapes.LINE, {
          x: ln.a * PT_TO_IN,
          y: ln.pos * PT_TO_IN,
          w: (ln.b - ln.a) * PT_TO_IN,
          h: 0,
          line: { color: ln.color, width: Math.max(0.25, ln.width) },
        });
      } else {
        slide.addShape(pptx.shapes.LINE, {
          x: ln.pos * PT_TO_IN,
          y: ln.a * PT_TO_IN,
          w: 0,
          h: (ln.b - ln.a) * PT_TO_IN,
          line: { color: ln.color, width: Math.max(0.25, ln.width) },
        });
      }
    }

    for (const row of rows) {
      for (const seg of row.segments) {
        slide.addText(runsForText(seg.text, seg), {
          x: seg.x0 * PT_TO_IN,
          y: seg.y0 * PT_TO_IN,
          w: (seg.x1 - seg.x0 + 6) * PT_TO_IN,
          h: (seg.y1 - seg.y0 + 2) * PT_TO_IN,
          align: "left",
          valign: "top",
          margin: 0,
          wrap: seg.text.includes("\n") || seg.text.length > 40,
          rotate: seg.rotation ? normalizeRotation(seg.rotation) : 0,
        });
      }
    }
    if (onProgress) onProgress(n + 1, models.length);
  }

  const out = await pptx.write({ outputType: "arraybuffer" });
  return { buffer: new Uint8Array(out), info };
}
