/**
 * Modelo neutro para la web (web/app.js y web/writers.js).
 *
 * Convierte el modelo interno del motor (spans, rellenos, líneas, imágenes)
 * y su cuadrícula visual (buildLayout) al formato neutro que espera la web:
 *
 *   { pages: [{ pageNumber, width, height, scanned,
 *                tables: [{ rows: [[celda, ...], ...] }],
 *                texts: [{ text, bold, size }],
 *                images: [{ dataUrl, width, height }] }],
 *     doubtfulCells: [{ page, table, row, col, value, confidence }],
 *     quality: { text_coverage, number_coverage, missing_sample },
 *     ocr_warning: "" }
 *
 * Cada celda: { value, type: "number"|"text"|"date", bold, italic, fill,
 * numFmt, colspan, rowspan, doubtful, confidence }.
 *
 * La cobertura aquí es de *colocación*: qué parte del texto y de las cifras
 * del PDF quedó dentro de la cuadrícula. La cobertura del archivo generado
 * (la que se muestra como informe de calidad) la calcula convertPdf contra
 * el .xlsx/.docx/.pptx ya escrito.
 */
import { buildLayout, isLowConfidence, verticalMerges } from "./layout.js";
import { parseNumber } from "./numbers.js";

function tokenize(text) {
  return String(text ?? "")
    .split(/\s+/)
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean);
}

function isNumberToken(token) {
  return parseNumber(token) !== null;
}

/**
 * @param {object} model modelo de página de extractPage
 * @param {number} pageNumber número de página (1-based)
 * @returns {object} página neutra
 */
export function modelToNeutralPage(model, pageNumber) {
  const lay = buildLayout(model);
  const { rows, cols, bounds, fills, borders } = lay;
  const vmerges = verticalMerges(model, lay);
  const vmergeTops = new Set(vmerges.map(([top, j]) => `${top},${j}`));
  const vmergeCont = new Set();
  for (const [top, j, bottom] of vmerges) {
    for (let i = top + 1; i <= bottom; i++) vmergeCont.add(`${i},${j}`);
  }

  // Celda de cada colocación, con su fusión horizontal (mergeTo).
  const cellAt = new Map();
  for (const pl of lay.placements) {
    const key = `${pl.row},${pl.col}`;
    const parsed = pl.parsed;
    const seg = pl.seg;
    const fill = fills.get(key);
    const doubtful = isLowConfidence(seg, model);
    const confWord = (model.ocrConfidences ?? []).find(
      (w) => w.text.trim().toLowerCase() === seg.text.trim().toLowerCase(),
    );
    cellAt.set(key, {
      value: parsed ? parsed.value : seg.text,
      rawText: seg.text,
      type: parsed ? "number" : "text",
      bold: seg.bold,
      italic: seg.italic,
      size: seg.size,
      fill: fill ?? null,
      numFmt: parsed ? parsed.numberFormat : null,
      currency: parsed ? parsed.currency : "",
      colspan: pl.mergeTo !== null && pl.mergeTo !== undefined && pl.mergeTo > pl.col ? pl.mergeTo - pl.col + 1 : 1,
      rowspan: 1,
      doubtful,
      confidence: confWord ? confWord.conf : null,
      _row: pl.row,
      _col: pl.col,
    });
  }
  // Fusión vertical: la celda superior abarca las filas continuadas.
  for (const [top, j, bottom] of vmerges) {
    const cell = cellAt.get(`${top},${j}`);
    if (cell) cell.rowspan = bottom - top + 1;
  }

  const tableRows = [];
  for (let i = 0; i < bounds.length - 1; i++) {
    const row = [];
    for (let j = 0; j < cols.length; j++) {
      const key = `${i},${j}`;
      if (vmergeCont.has(key)) {
        row.push(null); // celda cubierta por la fusión vertical de arriba
        continue;
      }
      const cell = cellAt.get(key);
      if (!cell) {
        row.push({
          value: "",
          rawText: "",
          type: "text",
          bold: false,
          italic: false,
          size: null,
          fill: fills.get(key) ?? null,
          numFmt: null,
          currency: "",
          colspan: 1,
          rowspan: 1,
          doubtful: false,
          confidence: null,
        });
        continue;
      }
      const { _row, _col, rawText, ...pub } = cell;
      void _row;
      void _col;
      void rawText;
      row.push(pub);
    }
    tableRows.push(row);
  }

  // Textos sueltos: spans cuya posición no cae dentro de ningún segmento
  // colocado en la cuadrícula (los segmentos son copias de los spans, así
  // que se compara por posición, no por identidad de objeto).
  const placedSegs = lay.placements.map((p) => p.seg);
  const texts = model.spans
    .filter(
      (s) =>
        !placedSegs.some(
          (g) =>
            (s.x0 + s.x1) / 2 >= g.x0 - 1 &&
            (s.x0 + s.x1) / 2 <= g.x1 + 1 &&
            (s.y0 + s.y1) / 2 >= g.y0 - 1 &&
            (s.y0 + s.y1) / 2 <= g.y1 + 1,
        ),
    )
    .map((s) => ({ text: s.text, bold: s.bold, size: s.size }));

  // Imágenes como data URL (el worker las envía como bytes; aquí ya son
  // Uint8Array PNG y se convierten en el hilo que llama).
  const images = (model.images ?? []).map((img) => ({
    x0: img.x0,
    y0: img.y0,
    x1: img.x1,
    y1: img.y1,
    fullPage: img.fullPage,
    png: img.png,
  }));

  // Cobertura de colocación (texto y cifras dentro de la cuadrícula).
  const expectedText = model.spans.flatMap((s) => tokenize(s.text));
  const placedText = lay.placements.flatMap((p) => tokenize(p.seg.text));
  const countTokens = (tokens) => {
    const map = new Map();
    for (const t of tokens) map.set(t, (map.get(t) ?? 0) + 1);
    return map;
  };
  const coverage = (expected, got) => {
    if (!expected.length) return 1;
    const gotMap = countTokens(got);
    let hit = 0;
    for (const t of expected) {
      if (gotMap.get(t) > 0) {
        gotMap.set(t, gotMap.get(t) - 1);
        hit++;
      }
    }
    return hit / expected.length;
  };
  const expectedNum = expectedText.filter(isNumberToken);
  const placedNum = placedText.filter(isNumberToken);
  const quality = {
    text_coverage: Math.round(coverage(expectedText, placedText) * 10000) / 10000,
    number_coverage: Math.round(coverage(expectedNum, placedNum) * 10000) / 10000,
    missing_sample: expectedText.filter((t) => !placedText.includes(t)).slice(0, 5),
  };

  const doubtfulCells = [];
  for (const cell of cellAt.values()) {
    if (cell.doubtful) {
      doubtfulCells.push({
        page: pageNumber,
        table: 0,
        row: cell._row,
        col: cell._col,
        value: cell.value,
        confidence: cell.confidence,
      });
    }
  }
  void borders;

  return {
    pageNumber,
    width: model.width,
    height: model.height,
    scanned: model.scanned,
    tables: [{ rows: tableRows }],
    texts,
    images,
    doubtfulCells,
    quality,
  };
}
