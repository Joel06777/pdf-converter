/**
 * PDF → Word (.docx) con docx 9.16.0 (MIT).
 *
 * Tres rutas, elegidas automáticamente (o forzadas con `mode`), como en
 * app/converters/pdf_to_word.py:
 *
 * * `grid`  – documentos tipo tabla/estado financiero: cuadrícula visual en
 *   una tabla de Word de ancho fijo, con rellenos, bordes, celdas combinadas
 *   e imágenes ancladas en su posición exacta.
 * * `flow`  – documentos de texto corrido: reconstrucción propia de párrafos,
 *   columnas y listas (NO hay equivalente de pdf2docx en JavaScript; ver
 *   README.md, sección "Word de texto corrido").
 * * `ocr`   – PDF escaneado: párrafos con el texto reconocido.
 *
 * En modo `auto` se construyen `flow` y `grid` y se queda la de mayor
 * cobertura de texto; si el texto empata, deciden las cifras aisladas
 * (en `flow` las cifras quedan enterradas en líneas y no sirven como
 * valores de celda), como hace Python con pdf2docx y la cuadrícula.
 */
import {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  Header,
  HeightRule,
  HorizontalPositionRelativeFrom,
  ImageRun,
  Packer,
  Paragraph,
  SectionType,
  ShadingType,
  Table,
  TableCell,
  TableLayoutType,
  TableRow,
  TextRun,
  TextWrappingType,
  VerticalAlign,
  VerticalMergeType,
  VerticalPositionRelativeFrom,
  WidthType,
} from "docx";
import { groupRows } from "./extract.js";
import { buildLayout, verticalMerges } from "./layout.js";
import { parseNumber } from "./numbers.js";
import { compareCoverage, docxTexts, docxTokens } from "./verify.js";

const PT_TO_TWIPS = 20;
const PT_TO_EMU = 12700;
const BORDER_STYLE = { hair: 2, thin: 4, medium: 12, thick: 18 };

const ALIGN = {
  left: AlignmentType.LEFT,
  right: AlignmentType.RIGHT,
  center: AlignmentType.CENTER,
};

/**
 * Empaqueta un documento .docx a bytes.
 * Se usa `toArrayBuffer` (no `toBuffer`): `Packer.toBuffer` usa el módulo
 * `buffer` de Node y en el navegador lanza "nodebuffer is not supported
 * by this platform". `toArrayBuffer` funciona en Node y en el navegador.
 * @param {Document} doc
 * @returns {Promise<Uint8Array>}
 */
async function packDoc(doc) {
  const ab = await Packer.toArrayBuffer(doc);
  return new Uint8Array(ab);
}

/**
 * Cifras aisladas: qué parte de las cifras colocadas en la cuadrícula
 * queda como valor entero (celda o párrafo propio) en el .docx.
 *
 * En modo flow las cifras van enterradas en líneas de texto
 * («Alquiler mensual   $   800.00») y una comprobación por celdas no las
 * encuentra, aunque el texto esté completo; en modo grid cada cifra es
 * su propia celda. Por eso la decisión auto no puede mirar solo la
 * cobertura de texto: si el texto empata, decide la cifra aislada.
 * @param {Array} models modelos de página
 * @param {Uint8Array} buffer .docx ya empaquetado
 * @returns {number|null} fracción 0..1, o null si no hay cifras colocadas
 */
function isolatedNumberScore(models, buffer) {
  const wanted = new Map();
  for (const model of models) {
    for (const pl of buildLayout(model).placements) {
      if (!pl.parsed) continue;
      const v = Math.round(pl.parsed.value * 10000) / 10000;
      wanted.set(v, (wanted.get(v) ?? 0) + 1);
    }
  }
  if (!wanted.size) return null;
  const have = new Map();
  for (const text of docxTexts(buffer)) {
    const p = parseNumber(text.trim());
    if (!p) continue;
    const v = Math.round(p.value * 10000) / 10000;
    have.set(v, (have.get(v) ?? 0) + 1);
  }
  let found = 0;
  let total = 0;
  for (const [v, n] of wanted) {
    total += n;
    found += Math.min(n, have.get(v) ?? 0);
  }
  return total ? found / total : null;
}

/** Párrafos con las imágenes de página completa de un escaneo (en línea). */
function scanImageParagraphs(model, maxWidthPt) {
  const out = [];
  for (const img of model.images) {
    if (!img.fullPage || !model.scanned) continue;
    let w = img.x1 - img.x0;
    let h = img.y1 - img.y0;
    if (w > maxWidthPt) {
      h = (h * maxWidthPt) / w;
      w = maxWidthPt;
    }
    out.push(
      new Paragraph({
        spacing: { before: 0, after: 0 },
        children: [
          new ImageRun({
            type: "png",
            data: img.png,
            transformation: { width: Math.round(w), height: Math.round(h) },
          }),
        ],
      }),
    );
  }
  return out;
}

function listStyle(text) {
  const t = text.trim();
  if (/^[•\-–*]\s+\S/.test(t)) return "ListBullet";
  if (/^\d+[.)]\s+\S/.test(t)) return "ListNumber";
  return null;
}

function repeatedLines(models) {
  if (models.length < 2) return [[], []];
  const zone = (top) => {
    const seen = new Map();
    for (const m of models) {
      const limit = top ? 90 : m.height - 90;
      const texts = new Set(
        m.spans.filter((s) => (top ? s.y0 < limit : s.y1 > limit)).map((s) => s.text.trim()),
      );
      for (const t of texts) seen.set(t, (seen.get(t) ?? 0) + 1);
    }
    return [...seen.entries()]
      .filter(([, n]) => n === models.length)
      .map(([t]) => t)
      .filter((t) => t.length >= 3);
  };
  return [zone(true), zone(false)];
}

function tableLike(models) {
  for (const m of models) {
    const rows = groupRows(m.spans);
    const multi = rows.filter((r) => r.segments.length >= 2);
    const numericRows = multi.filter((r) => r.segments.some((s) => parseNumber(s.text)));
    if (rows.length < 5 || multi.length < 0.4 * rows.length || numericRows.length < 5) return false;
  }
  return models.length > 0;
}

function runsForSegment(seg) {
  const runs = [];
  const lines = seg.text.split("\n");
  lines.forEach((line, k) => {
    if (k > 0) runs.push(new TextRun({ break: 1 }));
    runs.push(
      new TextRun({
        text: line,
        font: seg.font,
        size: Math.max(2, Math.round(seg.size * 2)),
        bold: seg.bold,
        italics: seg.italic,
        color: seg.color,
      }),
    );
  });
  return runs;
}

function cellBorders(sides) {
  const out = {};
  for (const name of ["top", "left", "bottom", "right"]) {
    const side = sides?.[name];
    if (side) {
      out[name] = { style: BorderStyle.SINGLE, size: BORDER_STYLE[side.style] ?? 4, color: side.color };
    } else {
      out[name] = { style: BorderStyle.NIL, size: 0, color: "auto" };
    }
  }
  return out;
}

function colIndexOf(cols, x) {
  let idx = 0;
  for (let j = 0; j < cols.length; j++) {
    if (cols[j].left <= x) idx = j;
  }
  return idx;
}

/** Una sección por página, con la tabla de la cuadrícula visual. */
function gridSections(models) {
  const [headers, footers] = repeatedLines(models);
  const sections = [];
  for (let n = 0; n < models.length; n++) {
    const model = models[n];
    const lay = buildLayout(model);
    const { cols, bounds } = lay;

    const taken = new Set(lay.placements.map((p) => `${p.row},${p.col}`));
    const vmerges = verticalMerges(model, lay);
    const vmergeTops = new Set(vmerges.map(([top, j]) => `${top},${j}`));
    const vmergeCont = new Set();
    for (const [top, j, bottom] of vmerges) {
      for (let i = top + 1; i <= bottom; i++) vmergeCont.add(`${i},${j}`);
    }

    // Reserva de celdas por texto (igual que en Python: el texto "desborda"
    // a las celdas libres vecinas, sin pisar a otro texto).
    const cellMap = new Map();
    for (const pl of lay.placements) {
      let j0 = pl.col;
      let j1 = pl.col;
      if (pl.mergeTo !== null && pl.mergeTo !== undefined) j1 = pl.mergeTo;
      else if (!pl.parsed) {
        if (pl.horizontal === "left") j1 = colIndexOf(cols, pl.seg.x1 - 0.5);
        else if (pl.horizontal === "right") j0 = colIndexOf(cols, pl.seg.x0 + 0.5);
      }
      let shrunk = false;
      while (j1 > pl.col && [...Array(j1 - pl.col).keys()].some((k) => taken.has(`${pl.row},${pl.col + 1 + k}`))) {
        j1--;
        shrunk = true;
      }
      while (j0 < pl.col && [...Array(pl.col - j0).keys()].some((k) => taken.has(`${pl.row},${j0 + k}`))) {
        j0++;
        shrunk = true;
      }
      if (!shrunk && pl.mergeTo === null && !pl.parsed) {
        if (pl.horizontal === "left") {
          while (j1 + 1 < cols.length && !taken.has(`${pl.row},${j1 + 1}`)) j1++;
        } else if (pl.horizontal === "right") {
          while (j0 - 1 >= 0 && !taken.has(`${pl.row},${j0 - 1}`)) j0--;
        }
      }
      if (vmergeTops.has(`${pl.row},${pl.col}`)) {
        j0 = j1 = pl.col;
      }
      for (let c = j0; c <= j1; c++) taken.add(`${pl.row},${c}`);
      cellMap.set(`${pl.row},${pl.col}`, { pl, j0, j1 });
    }

    const tableRows = [];
    for (let i = 0; i < bounds.length - 1; i++) {
      const cells = [];
      for (let j = 0; j < cols.length; j++) {
        const key = `${i},${j}`;
        const entry = cellMap.get(key);
        const isVCont = vmergeCont.has(key);
        const cellOpts = {
          width: { size: Math.round((cols[j].right - cols[j].left) * PT_TO_TWIPS), type: WidthType.DXA },
          verticalAlign: VerticalAlign.CENTER,
          margins: { top: 0, left: 0, bottom: 0, right: 0 },
          borders: cellBorders(lay.borders.get(key)),
          children: [new Paragraph({ spacing: { before: 0, after: 0 }, children: [] })],
        };
        if (lay.fills.has(key)) {
          cellOpts.shading = { type: ShadingType.CLEAR, color: "auto", fill: lay.fills.get(key) };
        }
        if (entry) {
          const { pl, j0, j1 } = entry;
          if (j1 > j0) cellOpts.columnSpan = j1 - j0 + 1;
          if (vmergeTops.has(key)) cellOpts.verticalMerge = VerticalMergeType.RESTART;
          cellOpts.children = [
            new Paragraph({
              alignment: ALIGN[pl.horizontal] ?? AlignmentType.LEFT,
              spacing: { before: 0, after: 0 },
              children: runsForSegment(pl.seg),
            }),
          ];
        } else if (isVCont) {
          cellOpts.verticalMerge = VerticalMergeType.CONTINUE;
        }
        cells.push(new TableCell(cellOpts));
      }
      tableRows.push(
        new TableRow({
          height: { value: Math.round(Math.max(1, bounds[i + 1] - bounds[i]) * PT_TO_TWIPS), rule: HeightRule.EXACTLY },
          children: cells,
        }),
      );
    }
    const table = new Table({
      rows: tableRows,
      width: { size: Math.round((cols[cols.length - 1].right - cols[0].left) * PT_TO_TWIPS), type: WidthType.DXA },
      layout: TableLayoutType.FIXED,
      columnWidths: cols.map((c) => Math.round((c.right - c.left) * PT_TO_TWIPS)),
    });

    // Párrafo mínimo tras la tabla para las imágenes ancladas (Word exige un
    // párrafo tras la tabla; 1 pt cabe en el margen inferior reservado).
    const imageRuns = [];
    const maxW = cols[cols.length - 1].right - cols[0].left;
    for (const img of model.images) {
      // La imagen de página completa de un escaneo ya va en línea en
      // scanImageParagraphs: si también se pusiera flotante aquí, la
      // página aparecería dos veces en el documento. Antes la condición
      // pedía además lay.rows.length, así que sin OCR (sin filas) se
      // duplicaba.
      if (img.fullPage && model.scanned) continue;
      let w = img.x1 - img.x0;
      let h = img.y1 - img.y0;
      if (w > maxW) {
        h = (h * maxW) / w;
        w = maxW;
      }
      imageRuns.push(
        new ImageRun({
          type: "png",
          data: img.png,
          transformation: { width: Math.round(w), height: Math.round(h) },
          floating: {
            horizontalPosition: {
              offset: Math.round(img.x0 * PT_TO_EMU),
              relative: HorizontalPositionRelativeFrom.PAGE,
            },
            verticalPosition: {
              offset: Math.round(img.y0 * PT_TO_EMU),
              relative: VerticalPositionRelativeFrom.PAGE,
            },
            allowOverlap: true,
            wrap: { type: TextWrappingType.NONE },
          },
        }),
      );
    }
    const tail = new Paragraph({
      spacing: { before: 0, after: 0 },
      children: [new TextRun({ text: "", size: 2 }), ...imageRuns],
    });

    const section = {
      properties: {
        type: n === 0 ? SectionType.CONTINUOUS : SectionType.NEXT_PAGE,
        page: {
          size: { width: Math.round(model.width * PT_TO_TWIPS), height: Math.round(model.height * PT_TO_TWIPS) },
          margin: {
            top: Math.max(0, Math.round(bounds[0] * PT_TO_TWIPS)),
            bottom: Math.max(0, Math.round((model.height - bounds[bounds.length - 1] - 4) * PT_TO_TWIPS)),
            left: Math.max(0, Math.round(cols[0].left * PT_TO_TWIPS)),
            right: Math.max(0, Math.round((model.width - cols[cols.length - 1].right) * PT_TO_TWIPS)),
          },
        },
      },
      // Las imágenes de página completa de un escaneo se incrustan en línea
      // (antes se omitían en Word aunque Python sí las incrustaba).
      children: [table, ...scanImageParagraphs(model, maxW), tail],
    };
    if (n === 0) {
      if (headers.length) {
        section.headers = {
          default: new Header({
            children: [new Paragraph({ children: [new TextRun({ text: headers.join("  |  ") })] })],
          }),
        };
      }
      if (footers.length) {
        section.footers = {
          default: new Footer({
            children: [new Paragraph({ children: [new TextRun({ text: footers.join("  |  ") })] })],
          }),
        };
      }
    }
    sections.push(section);
  }
  return sections;
}

/** Orden de lectura: detecta dos columnas por el hueco vertical y lee columna a columna. */
function orderReading(rows, model) {
  const xs = rows.flatMap((r) => r.segments.map((s) => s.x0)).sort((a, b) => a - b);
  let splitX = null;
  if (xs.length > 4) {
    let bestGap = 0;
    for (let i = 0; i < xs.length - 1; i++) {
      const gap = xs[i + 1] - xs[i];
      if (gap > bestGap && xs[i] > model.width * 0.25 && xs[i + 1] < model.width * 0.75) {
        bestGap = gap;
        splitX = (xs[i] + xs[i + 1]) / 2;
      }
    }
    if (bestGap < 60) splitX = null;
  }
  if (!splitX) return rows;
  const left = [];
  const right = [];
  for (const row of rows) {
    const cx = row.segments.reduce((s, seg) => s + (seg.x0 + seg.x1) / 2, 0) / row.segments.length;
    (cx < splitX ? left : right).push(row);
  }
  if (left.length < 3 || right.length < 3) return rows;
  return [...left, ...right];
}

/** Párrafos de texto corrido a partir de las filas (rutas flow y ocr). */
function paragraphsFromRows(rows, model) {
  const ordered = orderReading(rows, model);
  const children = [];
  for (const row of ordered) {
    const text = row.segments.map((s) => s.text).join("   ");
    const first = row.segments[0];
    const style = listStyle(text);
    children.push(
      new Paragraph({
        ...(style ? { style } : {}),
        spacing: { before: 0, after: 0 },
        children: [
          new TextRun({
            text,
            font: first.font,
            size: Math.max(2, Math.round(first.size * 2)),
            bold: first.bold,
            italics: first.italic,
            color: first.color,
          }),
        ],
      }),
    );
  }
  if (!children.length) children.push(new Paragraph({ children: [] }));
  return children;
}

function flowSections(models) {
  return models.map((model, n) => ({
    properties: {
      type: n === 0 ? SectionType.CONTINUOUS : SectionType.NEXT_PAGE,
      page: {
        size: { width: Math.round(model.width * PT_TO_TWIPS), height: Math.round(model.height * PT_TO_TWIPS) },
        margin: { top: 720, bottom: 720, left: 720, right: 720 },
      },
    },
    // En un escaneo, el texto reconocido va en párrafos y la imagen de la
    // página se incrusta debajo (antes no se incrustaba en Word).
    children: [...paragraphsFromRows(groupRows(model.spans), model), ...scanImageParagraphs(model, Math.max(72, model.width - 72))],
  }));
}

/**
 * Convierte los modelos de página ya extraídos a un .docx.
 * @param {Array} models modelos de página (de extractPage)
 * @param {object} opts { mode: 'auto'|'grid'|'flow'|'ocr', expectedTokens?: Map, onProgress?: fn }
 * @returns {Promise<{ buffer: Uint8Array, info: object }>}
 */
export async function modelsToWord(models, opts = {}) {
  const { mode = "auto", expectedTokens = null, onProgress = null } = opts;
  // Escaneado = sin texto nativo (menos de 20 caracteres por página). El flag
  // `scanned` del modelo también se marca en PDFs con imagen de fondo y texto
  // nativo (como el estado de ingresos), así que no sirve para decidir la ruta.
  const isScanned = models.length > 0 && models.every((m) => (m.nativeChars ?? 1) < 20);
  let engine;
  let buffer;

  if (mode === "ocr" || (mode === "auto" && isScanned)) {
    engine = "ocr";
    const doc = new Document({ sections: flowSections(models) });
    buffer = await packDoc(doc);
  } else if (mode === "grid" || (mode === "auto" && tableLike(models))) {
    engine = "grid";
    const doc = new Document({ sections: gridSections(models) });
    buffer = await packDoc(doc);
  } else if (mode === "flow") {
    engine = "flow";
    const doc = new Document({ sections: flowSections(models) });
    buffer = await packDoc(doc);
  } else {
    // auto, texto corrido: se construyen flow y grid y se queda la mejor cobertura.
    const flowDoc = new Document({ sections: flowSections(models) });
    const gridDoc = new Document({ sections: gridSections(models) });
    const flowBuf = await packDoc(flowDoc);
    const gridBuf = await packDoc(gridDoc);
    if (expectedTokens) {
      const flowQ = compareCoverage(expectedTokens, docxTokens(flowBuf));
      const gridQ = compareCoverage(expectedTokens, docxTokens(gridBuf));
      const flowCells = isolatedNumberScore(models, flowBuf);
      const gridCells = isolatedNumberScore(models, gridBuf);
      // El texto manda; si empata, deciden las cifras aisladas (celdas):
      // en flow las cifras quedan enterradas en líneas y no se pueden
      // usar como valores, aunque el texto esté completo.
      const textTie = Math.abs((gridQ.textCoverage ?? 0) - (flowQ.textCoverage ?? 0)) < 0.0001;
      const gridBetterCells =
        gridCells !== null && flowCells !== null && gridCells > flowCells;
      if ((gridQ.textCoverage ?? 0) > (flowQ.textCoverage ?? 0) || (textTie && gridBetterCells)) {
        engine = "grid (respaldo por cobertura)";
        buffer = gridBuf;
      } else {
        engine = "flow";
        buffer = flowBuf;
      }
    } else {
      engine = "flow";
      buffer = flowBuf;
    }
  }
  if (onProgress) onProgress(models.length, models.length);
  return { buffer: new Uint8Array(buffer), info: { pages: models.length, engine } };
}
