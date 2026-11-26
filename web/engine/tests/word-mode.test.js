/**
 * Decisión auto de Word (grid vs flow): si la cobertura de texto empata,
 * deciden las cifras aisladas. En flow las cifras quedan enterradas en
 * líneas («Alquiler mensual   $   800.00») y una comprobación por celdas
 * no las encuentra; en grid cada cifra es su propia celda.
 *
 * Casos medidos en paridad (cobertura de celdas del navegador en Word):
 * contrato_servicios 0,5833, dos_columnas_mixto 0,6, informe_mensual_mixto
 * 0,4074, tabla_encabezado_doble 0,36, tabla_sin_lineas_nomina 0,4 y
 * tabla_sin_lineas_ventas 0,4 — todos con auto eligiendo flow.
 */
import { describe, expect, it } from "vitest";
import { convertPdf } from "../src/index.js";
import { docxTexts } from "../src/verify.js";
import { parseNumber } from "../src/numbers.js";
import { readFixture } from "./helpers.js";

const GRID_CASES = [
  ["contrato_servicios.pdf", 800],
  ["dos_columnas_mixto.pdf", 25],
  ["informe_mensual_mixto.pdf", 12450],
  ["tabla_encabezado_doble.pdf", 100],
  ["tabla_sin_lineas_nomina.pdf", 974.98],
  ["tabla_sin_lineas_ventas.pdf", 1100],
];

describe("Word auto: grid cuando hay cifras en tabla", () => {
  for (const [file, amount] of GRID_CASES) {
    it(`${file}: elige grid y la cifra ${amount} queda aislada`, async () => {
      const { buffer, info, quality } = await convertPdf(readFixture(file), "word", { ocr: false });
      expect(info.engine).toMatch(/grid/);
      expect(quality.textCoverage).toBe(1);
      expect(quality.numberCoverage).toBe(1);
      const values = docxTexts(buffer)
        .map((t) => parseNumber(t.trim()))
        .filter(Boolean)
        .map((p) => p.value);
      expect(values).toContain(amount);
    });
  }

  it("dos_columnas.pdf (texto corrido sin cifras en tabla) sigue en flow", async () => {
    const { info, quality } = await convertPdf(readFixture("dos_columnas.pdf"), "word", {
      ocr: false,
    });
    expect(info.engine).toBe("flow");
    expect(quality.textCoverage).toBe(1);
  });
});
