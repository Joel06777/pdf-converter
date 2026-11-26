/**
 * Reconstrucción de la cuadrícula visual de la página (filas, columnas,
 * celdas combinadas) a partir del modelo de extract.js.
 *
 * Traducción fiel de app/converters/pdf_to_excel.py (build_layout y
 * auxiliares). La usan Excel y Word; PowerPoint la usa para las tablas nativas.
 */
import { groupRows } from "./extract.js";
import { isLoneCurrency, parseNumber } from "./numbers.js";

const MIN_GAP = 4.0; // huecos menores se consideran la misma columna
const SPACER_MIN = 12.0; // huecos mayores se conservan como columna vacía
const MIN_ROW_H = 5.0;
const MIN_COL_W = 9.0; // ancho mínimo (pt) para que un símbolo como "$" no quede recortado
const SPLIT_MIN_OFFSET = 10.0; // texto suelto que empieza más allá de esto parte la columna
const EDGE_REACH = 30.0; // cuánto se estiran los bordes exteriores hasta marcos/rellenos cercanos
const LOW_CONFIDENCE = 60;

function bisectRight(arr, x) {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] <= x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function buildColumns(rows, model) {
  const tableRows = rows.filter((r) => r.segments.length >= 2);
  const use = tableRows.length >= 2 ? tableRows : rows;
  // Perfil de proyección: cuántas filas ocupan cada punto horizontal.
  const width = Math.floor(model.width) + 2;
  const diff = new Array(width + 3).fill(0);
  for (const r of use) {
    for (const sg of r.segments) {
      const a = Math.max(0, Math.floor(sg.x0));
      const b = Math.min(width, Math.floor(sg.x1) + 1);
      diff[a] += 1;
      diff[b] -= 1;
    }
  }
  const noise = Math.floor(0.06 * use.length);
  const occupied = [];
  let acc = 0;
  for (let x = 0; x <= width; x++) {
    acc += diff[x];
    occupied.push(acc > noise);
  }
  let runs = [];
  let x = 0;
  while (x <= width) {
    if (occupied[x]) {
      const start = x;
      while (x <= width && occupied[x]) x++;
      const a = start;
      const b = x;
      if (runs.length && a - runs[runs.length - 1][1] < MIN_GAP) {
        runs[runs.length - 1][1] = b;
      } else {
        runs.push([a, b]);
      }
    } else {
      x++;
    }
  }
  // Los números alineados a la derecha pueden empezar antes del tramo "ocupado".
  for (const r of rows) {
    for (const sg of r.segments) {
      if (!parseNumber(sg.text)) continue;
      const cx = (sg.x0 + sg.x1) / 2;
      for (const run of runs) {
        if (run[0] - 2 <= cx && cx <= run[1] + 2) {
          run[0] = Math.min(run[0], sg.x0);
          run[1] = Math.max(run[1], sg.x1);
          break;
        }
      }
    }
  }
  const mergedRuns = [];
  for (const run of runs.sort((a, b) => a[0] - b[0])) {
    if (mergedRuns.length && run[0] - mergedRuns[mergedRuns.length - 1][1] < MIN_GAP) {
      mergedRuns[mergedRuns.length - 1][1] = Math.max(mergedRuns[mergedRuns.length - 1][1], run[1]);
    } else {
      mergedRuns.push(run);
    }
  }
  runs = mergedRuns;
  if (!runs.length) {
    // página sin estructura: una sola columna
    runs = [[Math.min(...rows.flatMap((r) => r.segments.map((s) => s.x0))), Math.max(...rows.flatMap((r) => r.segments.map((s) => s.x1)))]];
  }

  const cols = [];
  let left = runs[0][0] - 1.0;
  for (let i = 0; i < runs.length; i++) {
    const [a, b] = runs[i];
    if (i + 1 < runs.length) {
      const na = runs[i + 1][0];
      if (na - b >= SPACER_MIN) {
        cols.push({ left, right: b + 0.5, runL: a, runR: b });
        cols.push({ left: b + 0.5, right: na - 0.5, runL: b + 0.5, runR: na - 0.5 });
        left = na - 0.5;
      } else {
        const mid = (b + na) / 2;
        cols.push({ left, right: mid, runL: a, runR: b });
        left = mid;
      }
    } else {
      cols.push({ left, right: b + 1.0, runL: a, runR: b });
    }
  }

  const split = splitColumns(cols, rows);
  widenNarrow(split);

  // Estirar los bordes exteriores hasta marcos y rellenos cercanos.
  const xsLeft = [...model.lines.filter((l) => l.orient === "v").map((l) => l.pos), ...model.fills.map((f) => f.x0)];
  const xsRight = [...model.lines.filter((l) => l.orient === "v").map((l) => l.pos), ...model.fills.map((f) => f.x1)];
  const nearL = xsLeft.filter((v) => v >= 0 && split[0].left - v >= 0 && split[0].left - v <= EDGE_REACH);
  const nearR = xsRight.filter((v) => v - split[split.length - 1].right >= 0 && v - split[split.length - 1].right <= EDGE_REACH);
  if (nearL.length) split[0].left = Math.min(...nearL);
  if (nearR.length) split[split.length - 1].right = Math.max(...nearR);
  return split;
}

function splitColumns(cols, rows) {
  const contentLeft = cols[0].left;
  const contentRight = cols[cols.length - 1].right;
  const ccx = (contentLeft + contentRight) / 2;
  const splits = new Map();
  for (const r of rows) {
    const single = r.segments.length === 1;
    for (const seg of r.segments) {
      if (parseNumber(seg.text)) continue;
      const cx = (seg.x0 + seg.x1) / 2;
      if (single) {
        const centered = Math.abs(cx - ccx) <= 8 && seg.x0 - contentLeft > 12;
        const right = seg.x1 >= contentRight - 8 && seg.x0 > ccx;
        if (centered || right) continue;
      }
      const j = Math.max(0, Math.min(cols.length - 1, bisectRight(cols.map((c) => c.left), seg.x0) - 1));
      const c = cols[j];
      if (seg.x0 - c.left > SPLIT_MIN_OFFSET && c.right - seg.x0 > 6) {
        const xs = splits.get(j) ?? [];
        if (!xs.some((v) => Math.abs(v - seg.x0) < 3)) xs.push(seg.x0);
        splits.set(j, xs);
      }
    }
  }
  const out = [];
  for (let j = 0; j < cols.length; j++) {
    const c = cols[j];
    const edges = [c.left, ...(splits.get(j) ?? []).sort((a, b) => a - b), c.right];
    for (let k = 0; k < edges.length - 1; k++) {
      out.push({ left: edges[k], right: edges[k + 1], runL: c.runL, runR: c.runR });
    }
  }
  return out;
}

function widenNarrow(cols) {
  for (let j = 0; j < cols.length; j++) {
    const c = cols[j];
    const need = MIN_COL_W - (c.right - c.left);
    if (need <= 0) continue;
    for (const [nb, side] of [[j + 1, "r"], [j - 1, "l"]]) {
      if (nb >= 0 && nb < cols.length && cols[nb].right - cols[nb].left - need >= MIN_COL_W) {
        if (side === "r") {
          c.right += need;
          cols[nb].left += need;
        } else {
          c.left -= need;
          cols[nb].right -= need;
        }
        break;
      }
    }
  }
}

function mergeWrappedRows(rows, model) {
  if (rows.length < 3 || !model.fills.length) return rows;
  const heights = rows.map((r) => r.y1 - r.y0).sort((a, b) => a - b);
  const med = heights[Math.floor(heights.length / 2)];
  const groupOf = new Map();
  const groups = [];
  for (const f of model.fills) {
    const h = f.y1 - f.y0;
    if (!(1.5 * med < h && h <= 3.2 * med)) continue;
    const idx = rows
      .map((r, i) => i)
      .filter((i) => f.y0 <= (rows[i].y0 + rows[i].y1) / 2 && (rows[i].y0 + rows[i].y1) / 2 <= f.y1 && !groupOf.has(i));
    const numericRows = idx.filter((i) => rows[i].segments.some((sg) => parseNumber(sg.text))).length;
    if (idx.length >= 2 && idx.length <= 3 && idx.every((v, k) => v === idx[0] + k) && numericRows <= 1) {
      for (const i of idx) groupOf.set(i, groups.length);
      groups.push(idx);
    }
  }
  if (!groups.length) return rows;
  const out = [];
  const done = new Set();
  for (let i = 0; i < rows.length; i++) {
    if (!groupOf.has(i)) {
      out.push(rows[i]);
      continue;
    }
    const g = groupOf.get(i);
    if (done.has(g)) continue;
    done.add(g);
    const stacks = [];
    for (const k of groups[g]) {
      for (const s of rows[k].segments) {
        const st = stacks.find((st) => Math.abs(st[0].x0 - s.x0) <= 3 && st[st.length - 1].y1 <= s.y0 + 1);
        if (st) st.push(s);
        else stacks.push([s]);
      }
    }
    const segs = stacks.map((st) => {
      const first = st[0];
      return {
        text: st.map((s) => s.text).join("\n"),
        x0: first.x0,
        y0: Math.min(...st.map((s) => s.y0)),
        x1: Math.max(...st.map((s) => s.x1)),
        y1: Math.max(...st.map((s) => s.y1)),
        font: first.font,
        size: first.size,
        bold: first.bold,
        italic: first.italic,
        color: first.color,
        rotation: first.rotation ?? 0,
      };
    });
    segs.sort((a, b) => a.x0 - b.x0);
    out.push({ segments: segs, y0: Math.min(...segs.map((s) => s.y0)), y1: Math.max(...segs.map((s) => s.y1)) });
  }
  return out;
}

function buildRowBounds(rows, model) {
  const hCandidates = [...model.lines.filter((l) => l.orient === "h").map((l) => l.pos)];
  for (const f of model.fills) hCandidates.push(f.y0, f.y1);
  const bounds = [rows[0].y0 - 1.0];
  for (let k = 0; k < rows.length - 1; k++) {
    const a = rows[k];
    const b = rows[k + 1];
    let mid = (a.y1 + b.y0) / 2;
    const lo = Math.min(a.y1, b.y0) - 1.5;
    const hi = Math.max(a.y1, b.y0) + 1.5;
    const snaps = hCandidates.filter((c) => c >= lo && c <= hi);
    if (snaps.length) mid = snaps.reduce((best, c) => (Math.abs(c - mid) < Math.abs(best - mid) ? c : best), snaps[0]);
    bounds.push(Math.max(mid, bounds[bounds.length - 1] + MIN_ROW_H));
  }
  bounds.push(Math.max(rows[rows.length - 1].y1 + 1.0, bounds[bounds.length - 1] + MIN_ROW_H));
  const nearTop = hCandidates.filter((c) => bounds[0] - c >= 0 && bounds[0] - c <= EDGE_REACH);
  const nearBot = hCandidates.filter((c) => c - bounds[bounds.length - 1] >= 0 && c - bounds[bounds.length - 1] <= EDGE_REACH);
  if (nearTop.length) bounds[0] = Math.min(...nearTop);
  if (nearBot.length) bounds[bounds.length - 1] = Math.max(...nearBot);
  return bounds;
}

function colIndex(cols, x) {
  return Math.max(0, Math.min(cols.length - 1, bisectRight(cols.map((c) => c.left), x) - 1));
}

function rowIndex(bounds, y) {
  return Math.max(0, Math.min(bounds.length - 2, bisectRight(bounds, y) - 1));
}

function sideStyle(lineWidth) {
  let style = "thin";
  if (lineWidth < 0.45) style = "hair";
  else if (lineWidth >= 2.6) style = "thick";
  else if (lineWidth >= 1.4) style = "medium";
  return { style, width: lineWidth };
}

function computeBorders(model, cols, bounds) {
  const tol = 3.5;
  const hByBound = new Map();
  const vByBound = new Map();
  const colEdges = [...cols.map((c) => c.left), cols[cols.length - 1].right];
  for (const ln of model.lines) {
    if (ln.orient === "h") {
      let k = 0;
      let best = Infinity;
      bounds.forEach((b, i) => {
        if (Math.abs(b - ln.pos) < best) {
          best = Math.abs(b - ln.pos);
          k = i;
        }
      });
      if (Math.abs(bounds[k] - ln.pos) <= tol) {
        if (!hByBound.has(k)) hByBound.set(k, []);
        hByBound.get(k).push(ln);
      }
    } else {
      let k = 0;
      let best = Infinity;
      colEdges.forEach((e, i) => {
        if (Math.abs(e - ln.pos) < best) {
          best = Math.abs(e - ln.pos);
          k = i;
        }
      });
      if (Math.abs(colEdges[k] - ln.pos) <= tol) {
        if (!vByBound.has(k)) vByBound.set(k, []);
        vByBound.get(k).push(ln);
      }
    }
  }
  const covering = (lines, lo, hi) => {
    let best = null;
    for (const ln of lines ?? []) {
      const overlap = Math.min(ln.b, hi) - Math.max(ln.a, lo);
      if (overlap >= 0.5 * (hi - lo) && (!best || ln.width > best.width)) best = ln;
    }
    return best;
  };
  const borders = new Map();
  for (let i = 0; i < bounds.length - 1; i++) {
    for (let j = 0; j < cols.length; j++) {
      const col = cols[j];
      const sides = {};
      const top = covering(hByBound.get(i), col.left, col.right);
      const bottom = covering(hByBound.get(i + 1), col.left, col.right);
      const left = covering(vByBound.get(j), bounds[i], bounds[i + 1]);
      const right = covering(vByBound.get(j + 1), bounds[i], bounds[i + 1]);
      for (const [name, ln] of [["top", top], ["bottom", bottom], ["left", left], ["right", right]]) {
        if (ln) sides[name] = { ...sideStyle(ln.width), color: ln.color };
      }
      if (Object.keys(sides).length) borders.set(`${i},${j}`, sides);
    }
  }
  return borders;
}

function computeFills(model, cols, bounds) {
  const centersX = cols.map((c) => (c.left + c.right) / 2);
  const centersY = [];
  for (let i = 0; i < bounds.length - 1; i++) centersY.push((bounds[i] + bounds[i + 1]) / 2);
  const result = new Map();
  for (const f of model.fills) {
    // en orden de dibujo: el último queda encima
    for (let i = 0; i < centersY.length; i++) {
      if (!(f.y0 - 0.2 <= centersY[i] && centersY[i] <= f.y1 + 0.2)) continue;
      for (let j = 0; j < centersX.length; j++) {
        if (f.x0 - 0.2 <= centersX[j] && centersX[j] <= f.x1 + 0.2) {
          result.set(`${i},${j}`, f.color);
        }
      }
    }
  }
  return result;
}

/** Fusiones verticales: un relleno que abarca varias filas con texto solo en la primera. */
export function verticalMerges(model, lay) {
  const { rows, cols, bounds, placements } = lay;
  const occupied = new Set(placements.map((p) => `${p.row},${p.col}`));
  const merges = [];
  const centersY = [];
  for (let i = 0; i < bounds.length - 1; i++) centersY.push((bounds[i] + bounds[i + 1]) / 2);
  const centersX = cols.map((c) => (c.left + c.right) / 2);
  for (const f of model.fills) {
    const rowIdx = centersY.map((cy, i) => (f.y0 - 0.2 <= cy && cy <= f.y1 + 0.2 ? i : -1)).filter((i) => i >= 0);
    if (rowIdx.length < 2) continue;
    for (let j = 0; j < centersX.length; j++) {
      if (!(f.x0 - 0.2 <= centersX[j] && centersX[j] <= f.x1 + 0.2)) continue;
      const top = rowIdx[0];
      if (!occupied.has(`${top},${j}`)) continue;
      if (rowIdx.slice(1).some((i) => occupied.has(`${i},${j}`))) continue;
      merges.push([top, j, rowIdx[rowIdx.length - 1]]);
    }
  }
  return merges;
}

function mergeCurrencyWithNumber(placements) {
  const byCell = new Map();
  placements.forEach((pl, k) => {
    const key = `${pl.row},${pl.col}`;
    if (!byCell.has(key)) byCell.set(key, []);
    byCell.get(key).push(k);
  });
  const drop = new Set();
  for (const idxs of byCell.values()) {
    if (idxs.length !== 2) continue;
    const a = placements[idxs[0]];
    const b = placements[idxs[1]];
    let cur = null;
    let num = null;
    if (isLoneCurrency(a.seg.text) && b.parsed) [cur, num] = [a, b];
    else if (isLoneCurrency(b.seg.text) && a.parsed) [cur, num] = [b, a];
    if (!cur || cur.seg.x0 > num.seg.x0) continue;
    const combined = `${cur.seg.text.trim()} ${num.seg.text.trim()}`;
    const parsed = parseNumber(combined);
    if (!parsed) continue;
    num.seg = {
      ...num.seg,
      text: combined,
      x0: Math.min(cur.seg.x0, num.seg.x0),
      y0: Math.min(cur.seg.y0, num.seg.y0),
      x1: Math.max(cur.seg.x1, num.seg.x1),
      y1: Math.max(cur.seg.y1, num.seg.y1),
    };
    num.parsed = parsed;
    drop.add(cur === a ? idxs[0] : idxs[1]);
  }
  return placements.filter((_, k) => !drop.has(k));
}

/**
 * Valida subtotal + IVA = total en las filas etiquetadas así.
 * Devuelve null si faltan filas o si la suma cuadra (±0,01).
 * NUNCA cambia un valor: solo sirve para marcar las celdas como dudosas.
 */
export function checkTotals(placements) {
  const found = {};
  const rows = new Map();
  for (const pl of placements) {
    if (!rows.has(pl.row)) rows.set(pl.row, []);
    rows.get(pl.row).push(pl);
  }
  for (const [r, pls] of rows) {
    const label = pls
      .slice()
      .sort((a, b) => a.col - b.col)
      .map((p) => p.seg.text)
      .join(" ")
      .toUpperCase();
    const money = [];
    const plain = [];
    for (const p of pls.slice().sort((a, b) => a.col - b.col)) {
      const tokens = p.seg.text.split(/\s+/);
      tokens.forEach((tok, k) => {
        const parsed = parseNumber(tok);
        if (!parsed) return;
        const prev = k > 0 ? tokens[k - 1] : "";
        const bucket = tok.includes(".") || tok.includes(",") || isLoneCurrency(prev) ? money : plain;
        bucket.push([parsed.value, [p.row, p.col]]);
      });
    }
    const nums = money.length ? money : plain;
    if (!nums.length) continue;
    const [value, cell] = nums[nums.length - 1];
    if (label.includes("SUBTOTAL")) found.subtotal = found.subtotal ?? [value, cell];
    else if (label.includes("IVA") || /\bI\.?V\.?A\.?\b/.test(label)) found.iva = found.iva ?? [value, cell];
    else if (label.includes("TOTAL")) found.total = found.total ?? [value, cell];
  }
  if (!("subtotal" in found && "iva" in found && "total" in found)) return null;
  const [sub] = found.subtotal;
  const [iva] = found.iva;
  const [total] = found.total;
  if (Math.abs(sub + iva - total) <= 0.01) return null;
  return {
    subtotal: sub,
    iva,
    total,
    cells: [found.subtotal[1], found.iva[1], found.total[1]],
    message:
      `La suma del subtotal ($ ${sub.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}) ` +
      `+ IVA ($ ${iva.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}) ` +
      `no coincide con el total impreso ($ ${total.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}). ` +
      `Revisa esas cifras antes de usar el archivo.`,
  };
}

/** ¿Coincide este segmento con una palabra de OCR de baja confianza? */
export function isLowConfidence(seg, model) {
  const text = seg.text.trim().toLowerCase();
  return (model.ocrConfidences ?? []).some(
    (w) => w.conf < LOW_CONFIDENCE && w.text.trim().toLowerCase() === text,
  );
}

/** Reconstruye la cuadrícula visual de la página. La usan Excel y Word. */
export function buildLayout(model) {
  let rows = mergeWrappedRows(groupRows(model.spans), model);
  let cols;
  let bounds;
  if (!rows.length) {
    cols = [{ left: 0, right: model.width, runL: 0, runR: model.width }];
    bounds = [0.0, model.height];
  } else {
    cols = buildColumns(rows, model);
    bounds = buildRowBounds(rows, model);
  }
  const fills = computeFills(model, cols, bounds);
  const borders = computeBorders(model, cols, bounds);

  const contentLeft = cols[0].left;
  const contentRight = cols[cols.length - 1].right;
  const contentCx = (contentLeft + contentRight) / 2;
  let placements = [];
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const single = row.segments.length === 1;
    for (const seg of row.segments) {
      const parsed = parseNumber(seg.text);
      const cx = (seg.x0 + seg.x1) / 2;
      let horizontal = "left";
      let mergeTo = null;
      let j;
      if (single) {
        const width = seg.x1 - seg.x0;
        if (Math.abs(cx - contentCx) <= 8 && width < 0.95 * (contentRight - contentLeft) && seg.x0 - contentLeft > 12) {
          j = 0;
          mergeTo = cols.length - 1;
          horizontal = "center";
        } else if (seg.x1 >= contentRight - 8 && seg.x0 > contentCx) {
          j = colIndex(cols, seg.x1 - 0.5);
          horizontal = "right";
        } else {
          j = colIndex(cols, seg.x0 + 0.5);
        }
      } else {
        j = colIndex(cols, cx);
        const col = cols[j];
        const lm = seg.x0 - col.runL;
        const rm = col.runR - seg.x1;
        if (parsed) horizontal = lm + 1.5 < rm ? "left" : "right";
        else if (lm <= 3) horizontal = "left";
        else if (rm <= 3) horizontal = "right";
        else if (Math.abs(lm - rm) <= 1.5) horizontal = "center";
        if (horizontal === "left") j = colIndex(cols, seg.x0 + 0.5);
        else if (horizontal === "right") j = colIndex(cols, seg.x1 - 0.5);
      }
      if (mergeTo === null && seg.text.includes("\n") && horizontal === "left") {
        mergeTo = colIndex(cols, seg.x1 - 0.5);
      }
      placements.push({ row: i, col: j, seg, horizontal, mergeTo, parsed });
    }
  }
  placements = mergeCurrencyWithNumber(placements);
  return { rows, cols, bounds, fills, borders, placements };
}

export { colIndex, rowIndex };
