/**
 * Verificación automática de fidelidad: ¿todo el texto y todas las cifras del
 * PDF llegaron al archivo? Traducción de app/converters/verify.py.
 *
 * Compara las "palabras" del PDF contra las del archivo convertido. Las
 * cifras se comparan por valor numérico (no por cadena), así que
 * "30,570.51" y "$ 30,570.51" cuentan igual; los códigos como el RUC se
 * comparan como texto.
 */
import ExcelJS from "exceljs";
import { unzipSync } from "fflate";
import { parseNumber } from "./numbers.js";

function norm(token) {
  const p = parseNumber(token);
  return p ? ["n", Math.round(p.value * 10000) / 10000] : ["t", token.toLowerCase()];
}

function keyOf([kind, val]) {
  return `${kind}:${val}`;
}

function countTokens(tokens) {
  const map = new Map();
  for (const t of tokens) {
    const k = keyOf(t);
    map.set(k, (map.get(k) ?? 0) + 1);
  }
  return map;
}

/** Tokens del texto nativo del PDF (palabras con su posición, vía MuPDF). */
export function pdfTokensFromSpans(spans) {
  const tokens = [];
  for (const s of spans) {
    for (const t of s.text.split(/\s+/)) {
      if (t) tokens.push(norm(t));
    }
  }
  const map = countTokens(tokens);
  return map.size >= 5 ? map : null;
}

/** Tokens de un .xlsx. Las fórmulas =SUM(...) se evalúan con su rango. */
export async function xlsxTokens(buffer) {
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.load(buffer);
  const tokens = [];
  for (const ws of wb.worksheets) {
    const numeric = new Map();
    const formulas = [];
    ws.eachRow((row) => {
      row.eachCell((cell) => {
        if (cell.value === null || cell.value === undefined) return;
        if (typeof cell.value === "number") {
          numeric.set(`${cell.row},${cell.col}`, cell.value);
          tokens.push(["n", Math.round(cell.value * 10000) / 10000]);
          if (typeof cell.numFmt === "string" && cell.numFmt.startsWith('"')) {
            tokens.push(["t", cell.numFmt.split('"')[1].toLowerCase()]);
          }
        } else if (typeof cell.value === "object" && cell.value.formula) {
          formulas.push([cell.row, cell.col, cell.value.formula]);
        } else if (typeof cell.value === "string") {
          for (const t of cell.value.split(/\s+/)) {
            if (t) tokens.push(norm(t));
          }
        }
      });
    });
    for (const [r, col, formula] of formulas) {
      const m = /^SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)$/.exec(String(formula).trim());
      if (!m) continue;
      const colIdx = (letters) => {
        let n = 0;
        for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64);
        return n;
      };
      const c0 = colIdx(m[1]);
      const r0 = parseInt(m[2], 10);
      const c1 = colIdx(m[3]);
      const r1 = parseInt(m[4], 10);
      let total = 0;
      for (const [key, v] of numeric) {
        const [rr, cc] = key.split(",").map(Number);
        if (rr >= r0 && rr <= r1 && cc >= c0 && cc <= c1) total += v;
      }
      numeric.set(`${r},${col}`, total);
      tokens.push(["n", Math.round(total * 10000) / 10000]);
      const fmt = ws.getCell(r, col).numFmt || "";
      if (typeof fmt === "string" && fmt.startsWith('"')) {
        tokens.push(["t", fmt.split('"')[1].toLowerCase()]);
      }
    }
  }
  return countTokens(tokens);
}

/** Textos <w:t>/<a:t> completos de un XML (sin partir en tokens). */
function xmlTexts(xml) {
  // <w:t> (Word) y <a:t> (PowerPoint); se decodifican las entidades básicas.
  const re = /<(?:w|a):t[^>]*>([^<]*)<\/(?:w|a):t>/g;
  const out = [];
  let m;
  while ((m = re.exec(xml)) !== null) {
    out.push(
      m[1]
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, '"')
        .replace(/&apos;/g, "'"),
    );
  }
  return out;
}

function xmlTextTokens(buffer, filePattern) {
  const files = unzipSync(new Uint8Array(buffer));
  const tokens = [];
  const decoder = new TextDecoder("utf-8");
  for (const [name, data] of Object.entries(files)) {
    if (!filePattern.test(name)) continue;
    const xml = decoder.decode(data);
    for (const text of xmlTexts(xml)) {
      for (const t of text.split(/\s+/)) {
        if (t) tokens.push(norm(t));
      }
    }
  }
  return countTokens(tokens);
}

/** Textos <w:t> completos de un .docx (cada texto entero, sin partir). */
export function docxTexts(buffer) {
  const files = unzipSync(new Uint8Array(buffer));
  const xml = new TextDecoder("utf-8").decode(files["word/document.xml"]);
  return xmlTexts(xml);
}

/** Tokens de un .docx (párrafos y tablas del documento principal). */
export function docxTokens(buffer) {
  return xmlTextTokens(buffer, /^word\/document\.xml$/);
}

/** Tokens de un .pptx (diapositivas y notas). */
export function pptxTokens(buffer) {
  return xmlTextTokens(buffer, /^ppt\/(slides\/slide\d+\.xml|notesSlides\/notesSlide\d+\.xml)$/);
}

/**
 * Compara los tokens esperados del PDF con los del archivo convertido.
 * @param {Map|null} expected tokens del PDF (null = sin texto nativo)
 * @param {Map} got tokens del archivo convertido
 */
export function compareCoverage(expected, got) {
  if (!expected) {
    return { verifiable: false, reason: "El PDF no tiene texto nativo (documento escaneado)." };
  }
  const cov = (kind) => {
    let total = 0;
    let hit = 0;
    for (const [k, v] of expected) {
      if (kind && !k.startsWith(`${kind}:`)) continue;
      total += v;
      hit += Math.min(v, got.get(k) ?? 0);
    }
    return total ? hit / total : 1.0;
  };
  const missing = [];
  for (const [k, v] of expected) {
    if ((got.get(k) ?? 0) < v && missing.length < 20) {
      missing.push(k.slice(2));
    }
  }
  return {
    verifiable: true,
    textCoverage: Math.round(cov(null) * 10000) / 10000,
    numberCoverage: Math.round(cov("n") * 10000) / 10000,
    missingSample: missing,
  };
}
