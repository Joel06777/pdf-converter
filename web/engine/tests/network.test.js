/**
 * La conversión de un PDF con texto nativo no hace ninguna petición de red
 * (salvo cargar los estáticos al inicio, que aquí ya están cargados).
 * Se comprueba bloqueando fetch/XMLHttpRequest durante la conversión.
 */
import { describe, expect, it, vi } from "vitest";
import { convertPdf } from "../src/index.js";
import { readFixture } from "./helpers.js";

describe("sin red durante la conversión", () => {
  it("PDF nativo a Excel sin fetch ni XHR", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      throw new Error("fetch llamado durante la conversión (no permitido)");
    });
    const xhrOpen = globalThis.XMLHttpRequest
      ? vi.spyOn(globalThis.XMLHttpRequest.prototype, "open").mockImplementation(() => {
          throw new Error("XHR llamado durante la conversión (no permitido)");
        })
      : null;
    try {
      const { quality } = await convertPdf(readFixture("factura.pdf"), "excel");
      expect(quality.textCoverage).toBe(1.0);
      expect(fetchSpy).not.toHaveBeenCalled();
      if (xhrOpen) expect(xhrOpen).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
      xhrOpen?.mockRestore();
    }
  });

  it("PDF nativo a Word y PowerPoint sin fetch", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      throw new Error("fetch llamado durante la conversión (no permitido)");
    });
    try {
      const w = await convertPdf(readFixture("tabla_sin_lineas.pdf"), "word");
      const p = await convertPdf(readFixture("tabla_sin_lineas.pdf"), "pptx");
      expect(w.quality.textCoverage).toBe(1.0);
      expect(p.quality.textCoverage).toBe(1.0);
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
  });
});
