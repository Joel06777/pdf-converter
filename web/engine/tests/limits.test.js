/**
 * Límites anti-abuso y fallos con elegancia: mensajes claros en español y
 * códigos estables, sin excepciones crudas ni cuelgues.
 */
import { describe, expect, it } from "vitest";
import { convertPdf, ConversionError } from "../src/index.js";
import { readFixture } from "./helpers.js";

describe("límites y errores", () => {
  it("archivo que no es un PDF: error claro en español", async () => {
    const junk = new Uint8Array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
    await expect(convertPdf(junk, "excel")).rejects.toMatchObject({
      code: expect.stringMatching(/pdf_(corrupto|invalido)/),
    });
    try {
      await convertPdf(junk, "excel");
    } catch (err) {
      expect(err).toBeInstanceOf(ConversionError);
      expect(err.message).toMatch(/PDF válido|dañado/);
    }
  });

  it("PDF vacío (0 bytes): error claro", async () => {
    await expect(convertPdf(new Uint8Array(0), "excel")).rejects.toBeInstanceOf(ConversionError);
  });

  it("PDF de más de 50 MB: rechazado antes de procesar", async () => {
    const big = new Uint8Array(51 * 1024 * 1024);
    await expect(convertPdf(big, "excel")).rejects.toMatchObject({ code: "limite_excedido" });
  });

  it("destino no soportado: error claro", async () => {
    await expect(convertPdf(readFixture("factura.pdf"), "csv")).rejects.toThrow(/Destino no soportado/);
  });

  it("cancelación: isCancelled() detiene la conversión multipágina", async () => {
    let calls = 0;
    await expect(
      convertPdf(readFixture("estado_cuenta_multipagina.pdf"), "excel", {
        isCancelled: () => {
          calls++;
          return calls >= 2; // cancela tras la primera página
        },
      }),
    ).rejects.toMatchObject({ code: "cancelado" });
  });

  it("progreso real por página en la conversión multipágina", async () => {
    const seen = [];
    await convertPdf(readFixture("estado_cuenta_multipagina.pdf"), "excel", {
      onProgress: (page, total, stage) => {
        if (stage === "extract") seen.push(page);
      },
    });
    expect(seen).toEqual([1, 2, 3]);
  });
});
