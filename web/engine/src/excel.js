/**
 * PDF → Excel (.xlsx) con exceljs 4.4.0 (MIT).
 *
 * Traducción de app/converters/pdf_to_excel.py (_page_to_sheet, _total_formulas,
 * check_totals). Mismos números reales, formatos contables, rellenos, bordes,
 * celdas combinadas, imágenes y fórmulas de totales (solo si la suma coincide
 * con lo impreso, tolerancia 0,01; si no, la cifra impresa se queda como valor).
 */
import ExcelJS from "exceljs";
import { buildLayout, checkTotals, isLowConfidence, verticalMerges } from "./layout.js";

const EMU_PER_PT = 12700;
const LOW_CONF_FILL = "FFF2CC";

/** Letra de columna de Excel (1 → "A"). */
function colLetter(n) {
  let s = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function borderSide(side) {
  if (!side) return undefined;
  return { style: side.style, color: { argb: `FF${side.color}` } };
}

function totalFormulas(ws, lay, off) {
  const byCell = new Map();
  for (const p of lay.placements) {
    if (p.parsed) byCell.set(`${p.row + off},${p.col}`, p);
  }
  const applied = [];
  for (const [key, pl] of byCell) {
    const [r, c] = key.split(",").map(Number);
    const label = lay.placements
      .filter((p) => p.row + off === r)
      .map((p) => p.seg.text)
      .join(" ");
    if (!label.toUpperCase().includes("TOTAL")) continue;
    const above = [...byCell.keys()]
      .map((k) => k.split(",").map(Number))
      .filter(([rr, cc]) => cc === c && rr < r)
      .map(([rr]) => rr)
      .sort((a, b) => a - b);
    if (above.length < 2) continue;
    let contiguous = true;
    for (let i = 0; i < above.length; i++) {
      if (above[i] !== above[0] + i) contiguous = false;
    }
    if (!contiguous || above[above.length - 1] !== r - 1) continue;
    const total = above.reduce((s, rr) => s + byCell.get(`${rr},${c}`).parsed.value, 0);
    if (Math.abs(total - pl.parsed.value) > 0.01) continue;
    const letter = colLetter(c + 1);
    const cell = ws.getCell(r + 1, c + 1);
    cell.value = { formula: `SUM(${letter}${above[0] + 1}:${letter}${above[above.length - 1] + 1})` };
    applied.push(`${letter}${r + 1}`);
  }
  return applied;
}

/**
 * Escribe una página en la hoja a partir de `startRow` (0 = primera fila).
 * Devuelve { rows, formulas, lowConfidenceCells, totalsWarning }.
 */
export function pageToSheet(ws, model, startRow = 0, formulas = true) {
  const lay = buildLayout(model);
  const { rows, cols, bounds, fills, borders } = lay;
  const off = startRow;

  // --- dimensiones (puntos -> unidades de Excel)
  for (let j = 0; j < cols.length; j++) {
    const c = cols[j];
    const px = (c.right - c.left) / 0.75;
    ws.getColumn(j + 1).width = Math.max(0.5, Math.min(255, (px - 5) / 7));
  }
  for (let i = 0; i < bounds.length - 1; i++) {
    ws.getRow(off + i + 1).height = Math.max(1.0, Math.min(409.0, bounds[i + 1] - bounds[i]));
  }

  // --- celdas con solo estilo (rellenos y bordes)
  const styled = new Set([...fills.keys(), ...borders.keys()]);
  for (const key of styled) {
    const [i, j] = key.split(",").map(Number);
    const cell = ws.getCell(off + i + 1, j + 1);
    if (fills.has(key)) {
      const color = fills.get(key);
      cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: `FF${color}` } };
    }
    if (borders.has(key)) {
      const s = borders.get(key);
      cell.border = {
        top: borderSide(s.top),
        bottom: borderSide(s.bottom),
        left: borderSide(s.left),
        right: borderSide(s.right),
      };
    }
  }

  // --- texto
  const merges = [];
  const lowCells = [];
  for (const pl of lay.placements) {
    const { seg, parsed } = pl;
    const cell = ws.getCell(off + pl.row + 1, pl.col + 1);
    if (parsed) {
      cell.value = parsed.value;
      cell.numFmt = parsed.numberFormat;
    } else {
      cell.value = seg.text;
    }
    cell.font = {
      name: seg.font,
      size: seg.size,
      bold: seg.bold,
      italic: seg.italic,
      color: { argb: `FF${seg.color}` },
    };
    cell.alignment = { horizontal: pl.horizontal, vertical: "middle", wrapText: seg.text.includes("\n") };
    if (isLowConfidence(seg, model)) {
      cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: `FF${LOW_CONF_FILL}` } };
      lowCells.push(`${colLetter(pl.col + 1)}${off + pl.row + 1}`);
    }
    if (pl.mergeTo !== null && pl.mergeTo !== undefined) {
      merges.push([off + pl.row + 1, pl.col + 1, pl.mergeTo + 1]);
    }
  }
  for (const [r, c0, c1] of merges) {
    if (c1 > c0) ws.mergeCells(r, c0, r, c1);
  }

  // --- fusiones verticales (categorías que agrupan varias filas)
  for (const [top, j, bottom] of verticalMerges(model, lay)) {
    try {
      ws.mergeCells(off + top + 1, j + 1, off + bottom + 1, j + 1);
    } catch {
      // ya fusionada por otra regla: se deja como está
    }
  }

  // --- validación subtotal + IVA = total (solo OCR: el texto nativo es exacto).
  // Nunca cambia valores: si no cuadra, las tres celdas quedan en amarillo.
  let totalsWarning = null;
  if (model.ocrUsed) {
    const totals = checkTotals(lay.placements);
    if (totals) {
      totalsWarning = totals.message;
      for (const [r, c] of totals.cells) {
        const cell = ws.getCell(off + r + 1, c + 1);
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: `FF${LOW_CONF_FILL}` } };
        lowCells.push(`${colLetter(c + 1)}${off + r + 1}`);
      }
    }
  }

  // --- fórmulas de totales (solo si la suma coincide con lo impreso)
  const formulaRefs = formulas ? totalFormulas(ws, lay, off) : [];

  // --- imágenes (el fondo de un escaneo con OCR no se copia: el texto ya está en las celdas)
  for (const img of model.images) {
    if (img.fullPage && model.scanned && rows.length) continue;
    try {
      const imageId = ws.workbook.addImage({ buffer: img.png, extension: "png" });
      const j = colIndexOf(cols, img.x0);
      const i = rowIndexOf(bounds, img.y0);
      ws.addImage(imageId, {
        tl: { col: j + Math.max(0, img.x0 - cols[j].left) / Math.max(1, cols[j].right - cols[j].left), row: i + Math.max(0, img.y0 - bounds[i]) / Math.max(1, bounds[i + 1] - bounds[i]) },
        ext: { width: (img.x1 - img.x0) / 0.75, height: (img.y1 - img.y0) / 0.75 },
      });
    } catch {
      // imagen no incrustable: se omite sin romper la conversión
    }
  }

  // --- vista e impresión
  ws.views = [{ showGridLines: false }];
  ws.pageSetup = {
    fitToPage: true,
    fitToWidth: 1,
    fitToHeight: 0,
    orientation: model.width > model.height ? "landscape" : "portrait",
    paperSize: Math.abs(model.width - 595) < 20 ? 9 : 1,
  };
  ws.pageMargins = { left: 0.25, right: 0.25, top: 0.25, bottom: 0.25 };
  return { rows: bounds.length - 1, formulas: formulaRefs, lowConfidenceCells: lowCells, totalsWarning };
}

function colIndexOf(cols, x) {
  let idx = 0;
  for (let j = 0; j < cols.length; j++) {
    if (cols[j].left <= x) idx = j;
  }
  return idx;
}

function rowIndexOf(bounds, y) {
  let idx = 0;
  for (let i = 0; i < bounds.length - 1; i++) {
    if (bounds[i] <= y) idx = i;
  }
  return idx;
}

/**
 * Convierte los modelos de página ya extraídos a un .xlsx.
 * @param {Array} models modelos de página (de extractPage)
 * @param {object} opts { layout: 'pages'|'continuous', formulas: boolean, onProgress?: fn }
 * @returns {Promise<{ buffer: Uint8Array, info: object }>}
 */
export async function modelsToExcel(models, opts = {}) {
  const { layout = "pages", formulas = true, onProgress = null } = opts;
  if (!["pages", "continuous"].includes(layout)) {
    throw new Error("layout debe ser 'pages' o 'continuous'");
  }
  const wb = new ExcelJS.Workbook();
  wb.creator = "Convertidor PDF (motor en el navegador)";
  const info = {
    pages: models.length,
    ocrPages: 0,
    scannedPages: 0,
    layout,
    formulas: [],
    lowConfidenceCells: [],
    ocrWarning: null,
  };
  let ws = null;
  let startRow = 0;
  for (let n = 0; n < models.length; n++) {
    const model = models[n];
    if (layout === "continuous") {
      if (!ws) ws = wb.addWorksheet("Documento");
    } else {
      ws = wb.addWorksheet(`Página ${n + 1}`);
    }
    const result = pageToSheet(ws, model, layout === "continuous" ? startRow : 0, formulas);
    if (layout === "continuous") startRow += result.rows + 1;
    info.ocrPages += model.ocrUsed ? 1 : 0;
    info.scannedPages += model.scanned ? 1 : 0;
    info.formulas.push(...result.formulas);
    info.lowConfidenceCells.push(...result.lowConfidenceCells);
    if (result.totalsWarning) {
      info.totalsWarning = result.totalsWarning;
      info.ocrWarning = info.ocrWarning ? `${info.ocrWarning} ${result.totalsWarning}` : result.totalsWarning;
    }
    if (onProgress) onProgress(n + 1, models.length);
  }
  const buffer = await wb.xlsx.writeBuffer();
  return { buffer: new Uint8Array(buffer), info };
}
