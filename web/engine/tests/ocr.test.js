/**
 * OCR en el navegador (tesseract.js) sobre los fixtures escaneados.
 *
 * La verdad de referencia es el PDF nativo del que se generó cada escaneo
 * (ver scripts/generate_fixtures.py): escaneado, foto inclinada y foto con
 * perspectiva vienen de factura.pdf; el escaneo en color con sello viene de
 * factura_real_logo_sello.pdf.
 *
 * Referencia del backend Python (docs/METRICAS.md, Tesseract CLI 5.3.4):
 * cifras 100 % en los 5 casos; texto 97,9 % (factura plana), 95,8 % (foto
 * inclinada), 97,9 % (color con sello), 95,8 % (perspectiva). Aquí se mide lo
 * mismo con tesseract.js y se exige cifras 1,0 y texto ≥ 0,90.
 *
 * La cobertura se mide contra el PDF ORIGINAL (no contra el escaneo, que no
 * tiene texto nativo y no sería verificable): se extraen sus tokens con
 * MuPDF y se comparan con los del .xlsx generado.
 */
import * as mupdf from "mupdf";
import { beforeAll, describe, expect, it } from "vitest";
import { convertPdf } from "../src/index.js";
import { extractPage } from "../src/extract.js";
import { compareCoverage, pdfTokensFromSpans, xlsxTokens } from "../src/verify.js";
import { ensureTessdata, readFixture, TESSDATA_DIR } from "./helpers.js";

const CASES = [
  { scanned: "escaneado.pdf", truth: "factura.pdf", label: "escaneo plano 200 dpi" },
  { scanned: "foto_inclinada.pdf", truth: "factura.pdf", label: "foto inclinada 3°" },
  // El escaneo en color se generó de _factura_con_sello_y_marca: la factura
  // normal (0001234, TOTAL 335.00) con sello rojo y marca de agua "COPIA".
  { scanned: "escaneado_color_sello.pdf", truth: "factura.pdf", label: "color con sello y marca de agua" },
  { scanned: "foto_celular_perspectiva.pdf", truth: "factura.pdf", label: "foto de celular con perspectiva + 2°" },
];

async function expectedTokens(pdfBytes) {
  const doc = mupdf.Document.openDocument(pdfBytes, "application/pdf");
  const spans = [];
  for (let i = 0; i < doc.countPages(); i++) {
    const model = await extractPage(doc, i, { mupdf, ocr: false });
    spans.push(...model.spans);
  }
  return pdfTokensFromSpans(spans);
}

let tessdataOk = false;

beforeAll(async () => {
  tessdataOk = await ensureTessdata();
  if (!tessdataOk) {
    console.warn("Sin datos de Tesseract (.tessdata/): las pruebas de OCR se omiten.");
  }
}, 300_000);

describe.each(CASES)("OCR → Excel: $scanned ($label)", ({ scanned, truth }) => {
  it("cifras 1,0 y texto ≥ 0,90 contra el PDF original", async () => {
    if (!tessdataOk) {
      console.warn("omitido: sin tessdata");
      return;
    }
    const t0 = Date.now();
    const { buffer, info } = await convertPdf(readFixture(scanned), "excel", {
      langPath: TESSDATA_DIR,
    });
    const quality = compareCoverage(await expectedTokens(readFixture(truth)), await xlsxTokens(buffer));
    console.log(
      `  OCR ${scanned}: texto=${quality.textCoverage} cifras=${quality.numberCoverage} ` +
        `ocrPages=${info.ocrPages} ${Date.now() - t0}ms missing=${JSON.stringify(quality.missingSample)}`,
    );
    expect(info.ocrPages).toBe(1);
    expect(info.scannedPages).toBe(1);
    expect(quality.verifiable).toBe(true);
    expect(quality.numberCoverage).toBe(1.0);
    expect(quality.textCoverage).toBeGreaterThanOrEqual(0.9);
    expect(buffer.length).toBeGreaterThan(0);
  });
});

describe("OCR: página girada 90°/270° (foto de celular de lado)", () => {
  it("Rotate 90: cifras 1,0 y texto ≥ 0,95", async () => {
    if (!tessdataOk) {
      console.warn("omitido: sin tessdata");
      return;
    }
    const bytes = readFixture("escaneado.pdf");
    const doc = mupdf.Document.openDocument(bytes, "application/pdf");
    doc.loadPage(0).getObject().put("Rotate", 90);
    const rotated = doc.saveToBuffer().asUint8Array();
    const { buffer, info } = await convertPdf(rotated, "excel", { langPath: TESSDATA_DIR });
    const quality = compareCoverage(await expectedTokens(readFixture("factura.pdf")), await xlsxTokens(buffer));
    console.log(`  OCR Rotate 90: texto=${quality.textCoverage} cifras=${quality.numberCoverage} missing=${JSON.stringify(quality.missingSample)}`);
    expect(info.ocrPages).toBe(1);
    expect(quality.numberCoverage).toBe(1.0);
    expect(quality.textCoverage).toBeGreaterThanOrEqual(0.95);
  });

  it("Rotate 270: cifras y texto 1,0", async () => {
    if (!tessdataOk) {
      console.warn("omitido: sin tessdata");
      return;
    }
    const bytes = readFixture("escaneado.pdf");
    const doc = mupdf.Document.openDocument(bytes, "application/pdf");
    doc.loadPage(0).getObject().put("Rotate", 270);
    const rotated = doc.saveToBuffer().asUint8Array();
    const { buffer, info } = await convertPdf(rotated, "excel", { langPath: TESSDATA_DIR });
    const quality = compareCoverage(await expectedTokens(readFixture("factura.pdf")), await xlsxTokens(buffer));
    console.log(`  OCR Rotate 270: texto=${quality.textCoverage} cifras=${quality.numberCoverage} missing=${JSON.stringify(quality.missingSample)}`);
    expect(info.ocrPages).toBe(1);
    expect(quality.numberCoverage).toBe(1.0);
    expect(quality.textCoverage).toBe(1.0);
  });
});

describe("OCR: correcciones y advertencias", () => {
  it("el símbolo Nº se restaura (no queda 'N?') y el TOTAL 335.00 es número real", async () => {
    if (!tessdataOk) {
      console.warn("omitido: sin tessdata");
      return;
    }
    const { buffer, quality } = await convertPdf(readFixture("escaneado.pdf"), "excel", {
      langPath: TESSDATA_DIR,
    });
    // Un escaneo no es verificable contra sí mismo (sin texto nativo).
    expect(quality.verifiable).toBe(false);
    const againstTruth = compareCoverage(await expectedTokens(readFixture("factura.pdf")), await xlsxTokens(buffer));
    expect(againstTruth.missingSample).not.toContain("n?");
    expect(againstTruth.missingSample).not.toContain("nº");
    expect(againstTruth.missingSample).not.toContain("335");
    expect(againstTruth.numberCoverage).toBe(1.0);
  });
});
