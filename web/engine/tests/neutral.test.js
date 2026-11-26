/**
 * Modelo neutro para la web: la cuadrícula del motor convertida al formato
 * que esperan web/app.js y web/writers.js, sin duplicar el texto entre
 * tablas y textos sueltos y con la cobertura de colocación en 1,0.
 */
import * as mupdf from "mupdf";
import { describe, expect, it } from "vitest";
import { extractPage } from "../src/extract.js";
import { modelToNeutralPage } from "../src/neutral.js";
import { readFixture } from "./helpers.js";

describe("modelo neutro", () => {
  it("factura: una tabla con la cifra TOTAL como número y cobertura 1,0", async () => {
    const doc = mupdf.Document.openDocument(readFixture("factura.pdf"), "application/pdf");
    const model = await extractPage(doc, 0, { mupdf, ocr: false });
    const page = modelToNeutralPage(model, 1);
    expect(page.tables.length).toBe(1);
    const cells = page.tables[0].rows.flat();
    const totals = cells.filter((c) => c.type === "number" && c.value === 335);
    expect(totals.length).toBeGreaterThanOrEqual(1);
    expect(page.quality.text_coverage).toBe(1);
    expect(page.quality.number_coverage).toBe(1);
    // Sin duplicados: ningún texto suelto repite un texto ya en la tabla.
    const cellTexts = new Set(cells.map((c) => String(c.rawText ?? c.value).trim()).filter(Boolean));
    for (const t of page.texts) {
      expect(cellTexts.has(t.text.trim())).toBe(false);
    }
    doc.destroy?.();
  });

  it("estado de ingresos: relleno verde y celdas combinadas en el modelo neutro", async () => {
    const doc = mupdf.Document.openDocument(
      readFixture("estado_ingresos_octubre_2026.pdf"),
      "application/pdf",
    );
    const model = await extractPage(doc, 0, { mupdf, ocr: false });
    const page = modelToNeutralPage(model, 1);
    const cells = page.tables[0].rows.flat();
    expect(cells.some((c) => c.fill === "8ED973")).toBe(true);
    expect(cells.some((c) => c.colspan > 1)).toBe(true);
    expect(page.quality.text_coverage).toBe(1);
    expect(page.quality.number_coverage).toBe(1);
    doc.destroy?.();
  });
});
