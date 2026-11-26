/**
 * Cobertura de texto y cifras por fixture y destino, medida contra el texto
 * extraído del PDF (misma métrica que app/converters/verify.py).
 *
 * Puerta de calidad: Excel primero (1,0 en texto nativo), luego PowerPoint y
 * Word. Los valores esperados son los medidos en docs/METRICAS.md para el
 * backend Python: 1,0 / 1,0 en los 10 fixtures nativos y los 3 destinos.
 */
import ExcelJS from "exceljs";
import { unzipSync } from "fflate";
import { describe, expect, it } from "vitest";
import { convertPdf } from "../src/index.js";
import { readFixture } from "./helpers.js";

const NATIVE = [
  "estado_ingresos_octubre_2026.pdf",
  "factura.pdf",
  "estado_cuenta_multipagina.pdf",
  "tabla_sin_lineas.pdf",
  "celdas_combinadas.pdf",
  "dos_columnas.pdf",
  "acentos.pdf",
  "factura_real_logo_sello.pdf",
  "tabla_combinada_compleja.pdf",
  "dos_columnas_tablas.pdf",
];

async function numericValues(buffer) {
  // Valores numéricos del .xlsx, resolviendo las fórmulas =SUM(...) (ExcelJS
  // no guarda valores en caché al escribir, igual que openpyxl en Python).
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.load(buffer);
  const values = [];
  for (const ws of wb.worksheets) {
    const numeric = new Map();
    const formulas = [];
    ws.eachRow((row) => {
      row.eachCell((cell) => {
        if (typeof cell.value === "number") {
          numeric.set(`${cell.row},${cell.col}`, cell.value);
          values.push(cell.value);
        } else if (cell.value && typeof cell.value === "object" && cell.value.formula) {
          formulas.push(cell.value.formula);
        }
      });
    });
    const colIdx = (letters) => {
      let n = 0;
      for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64);
      return n;
    };
    for (const formula of formulas) {
      const m = /^SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)$/.exec(String(formula).trim());
      if (!m) continue;
      const c0 = colIdx(m[1]);
      const r0 = parseInt(m[2], 10);
      const c1 = colIdx(m[3]);
      const r1 = parseInt(m[4], 10);
      let total = 0;
      for (const [key, v] of numeric) {
        const [rr, cc] = key.split(",").map(Number);
        if (rr >= r0 && rr <= r1 && cc >= c0 && cc <= c1) total += v;
      }
      values.push(total);
    }
  }
  return values;
}

async function allTextXlsx(buffer) {
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.load(buffer);
  const texts = [];
  for (const ws of wb.worksheets) {
    ws.eachRow((row) => {
      row.eachCell((cell) => {
        if (cell.value !== null && cell.value !== undefined && typeof cell.value !== "object") {
          texts.push(String(cell.value));
        }
      });
    });
  }
  return texts;
}

describe.each(NATIVE)("Excel: %s", (fixture) => {
  it("cobertura de texto y cifras 1,0", async () => {
    const { buffer, quality } = await convertPdf(readFixture(fixture), "excel");
    expect(quality.verifiable).toBe(true);
    expect(quality.textCoverage).toBe(1.0);
    expect(quality.numberCoverage).toBe(1.0);
    expect(quality.missingSample).toEqual([]);
    expect(buffer.length).toBeGreaterThan(0);
  });
});

describe.each(NATIVE)("PowerPoint: %s", (fixture) => {
  it("cobertura de texto y cifras 1,0", async () => {
    const { buffer, quality } = await convertPdf(readFixture(fixture), "pptx");
    expect(quality.verifiable).toBe(true);
    expect(quality.textCoverage).toBe(1.0);
    expect(quality.numberCoverage).toBe(1.0);
    expect(quality.missingSample).toEqual([]);
  });
});

describe.each(NATIVE)("Word: %s", (fixture) => {
  it("cobertura de texto y cifras 1,0", async () => {
    const { buffer, quality } = await convertPdf(readFixture(fixture), "word");
    expect(quality.verifiable).toBe(true);
    expect(quality.textCoverage).toBe(1.0);
    expect(quality.numberCoverage).toBe(1.0);
    expect(quality.missingSample).toEqual([]);
  });
});

describe("Excel: casos concretos (paridad con tests/test_fixtures.py)", () => {
  it("factura: números reales, fórmula TOTAL y RUC como texto", async () => {
    const { buffer, info } = await convertPdf(readFixture("factura.pdf"), "excel");
    const values = await numericValues(buffer);
    expect(values).toContain(335.0);
    expect(values).toContain(50.0);
    expect(values).toContain(160.0);
    expect(info.formulas.length).toBeGreaterThan(0);
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.load(buffer);
    const formulas = [];
    wb.worksheets[0].eachRow((row) => {
      row.eachCell((cell) => {
        if (cell.value && typeof cell.value === "object" && cell.value.formula) {
          formulas.push(cell.value.formula);
        }
      });
    });
    expect(formulas.some((f) => f.startsWith("SUM("))).toBe(true);
    const texts = await allTextXlsx(buffer);
    expect(texts.some((t) => t.includes("0993132977001"))).toBe(true);
  });

  it("estado de cuenta: 3 hojas en modo pages y 1 en continuo", async () => {
    const { buffer, info } = await convertPdf(readFixture("estado_cuenta_multipagina.pdf"), "excel");
    expect(info.pages).toBe(3);
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.load(buffer);
    expect(wb.worksheets.length).toBe(3);
    const { buffer: buf2 } = await convertPdf(readFixture("estado_cuenta_multipagina.pdf"), "excel", { layout: "continuous" });
    const wb2 = new ExcelJS.Workbook();
    await wb2.xlsx.load(buf2);
    expect(wb2.worksheets.length).toBe(1);
    expect(wb2.worksheets[0].rowCount).toBeGreaterThan(25);
  });

  it("tabla sin líneas: cifras 1950.50 y 1680.00", async () => {
    const { buffer } = await convertPdf(readFixture("tabla_sin_lineas.pdf"), "excel");
    const values = await numericValues(buffer);
    expect(values).toContain(1950.5);
    expect(values).toContain(1680.0);
  });

  it("celdas combinadas: hay fusión vertical en el xlsx", async () => {
    const { buffer } = await convertPdf(readFixture("celdas_combinadas.pdf"), "excel");
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.load(buffer);
    const merged = [];
    for (const ws of wb.worksheets) {
      for (const m of ws.model.merges ?? []) merged.push(m);
    }
    const vertical = merged.filter((m) => {
      const match = /^([A-Z]+)(\d+):([A-Z]+)(\d+)$/.exec(m);
      return match && match[2] !== match[4];
    });
    expect(vertical.length).toBeGreaterThan(0);
  });

  it("estado de ingresos: cifras clave como números reales", async () => {
    const { buffer } = await convertPdf(readFixture("estado_ingresos_octubre_2026.pdf"), "excel");
    const values = await numericValues(buffer);
    expect(values).toContain(30570.51);
    expect(values).toContain(27948.96);
    expect(values).toContain(2621.55);
  });

  it("estado de ingresos: el encabezado conserva el relleno verde 8ED973", async () => {
    const { buffer } = await convertPdf(readFixture("estado_ingresos_octubre_2026.pdf"), "excel");
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.load(buffer);
    const fills = new Set();
    for (const ws of wb.worksheets) {
      ws.eachRow((row) => {
        row.eachCell((cell) => {
          if (cell.fill?.fgColor?.argb) fills.add(cell.fill.fgColor.argb);
        });
      });
    }
    expect([...fills].some((f) => f.toUpperCase().includes("8ED973"))).toBe(true);
  });
});

describe("PowerPoint: casos concretos", () => {
  it("factura: tabla nativa con la cifra 335", async () => {
    const { buffer } = await convertPdf(readFixture("factura.pdf"), "pptx");
    const files = unzipSync(new Uint8Array(buffer));
    const slideXml = new TextDecoder().decode(files["ppt/slides/slide1.xml"]);
    expect(slideXml).toContain("<a:tbl>");
    expect(slideXml).toContain("335");
  });

  it("celdas combinadas: la tabla tiene gridSpan o vMerge", async () => {
    const { buffer } = await convertPdf(readFixture("celdas_combinadas.pdf"), "pptx");
    const files = unzipSync(new Uint8Array(buffer));
    const slideXml = new TextDecoder().decode(files["ppt/slides/slide1.xml"]);
    expect(slideXml.includes("gridSpan") || slideXml.includes("vMerge")).toBe(true);
  });

  it("una diapositiva por página", async () => {
    const { buffer, info } = await convertPdf(readFixture("estado_cuenta_multipagina.pdf"), "pptx");
    expect(info.pages).toBe(3);
    const files = unzipSync(new Uint8Array(buffer));
    const slides = Object.keys(files).filter((n) => /^ppt\/slides\/slide\d+\.xml$/.test(n));
    expect(slides.length).toBe(3);
  });
});

describe("Word: casos concretos", () => {
  it("estado de cuenta: 3 secciones y encabezado repetido", async () => {
    const { buffer, info } = await convertPdf(readFixture("estado_cuenta_multipagina.pdf"), "word");
    expect(info.pages).toBe(3);
    const files = unzipSync(new Uint8Array(buffer));
    const names = Object.keys(files);
    expect(names.some((n) => n === "word/document.xml")).toBe(true);
    const docXml = new TextDecoder().decode(files["word/document.xml"]);
    expect(docXml).toContain("ESTADO DE CUENTA");
    // secciones (una por página)
    const sections = (docXml.match(/<w:sectPr>/g) ?? []).length;
    expect(sections).toBe(3);
  });

  it("celdas combinadas: fusión vertical real (vMerge) en el docx", async () => {
    const { buffer } = await convertPdf(readFixture("celdas_combinadas.pdf"), "word");
    const files = unzipSync(new Uint8Array(buffer));
    const docXml = new TextDecoder().decode(files["word/document.xml"]);
    expect(docXml).toContain("vMerge");
  });

  it("dos columnas: la columna izquierda va antes que la derecha (orden de lectura)", async () => {
    const { buffer } = await convertPdf(readFixture("dos_columnas.pdf"), "word");
    const files = unzipSync(new Uint8Array(buffer));
    const docXml = new TextDecoder().decode(files["word/document.xml"]);
    const texts = [...docXml.matchAll(/<w:t[^>]*>([^<]*)<\/w:t>/g)].map((m) => m[1]);
    const joined = texts.join(" ");
    const leftIdx = joined.indexOf("La asociación informa");
    const rightIdx = joined.indexOf("También se recuerda");
    expect(leftIdx).toBeGreaterThanOrEqual(0);
    expect(rightIdx).toBeGreaterThanOrEqual(0);
    expect(leftIdx).toBeLessThan(rightIdx);
  });
});
