import fs from "node:fs";
import { convertPdf } from "../src/index.js";

const FIX = new URL("../../../tests/fixtures/", import.meta.url).pathname;
const native = [
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
const targets = ["excel", "pptx", "word"];
const results = [];
for (const name of native) {
  const pdf = fs.readFileSync(`${FIX}${name}`);
  for (const target of targets) {
    const t0 = Date.now();
    try {
      const { info, quality } = await convertPdf(pdf, target);
      results.push({ fixture: name, target, text: quality.textCoverage, num: quality.numberCoverage, ms: Date.now() - t0, engine: info.engine ?? "", missing: quality.missingSample ?? [] });
      console.log(`${name} → ${target}: texto=${quality.textCoverage} cifras=${quality.numberCoverage} ${Date.now() - t0}ms engine=${info.engine ?? ""} missing=${JSON.stringify(quality.missingSample ?? [])}`);
    } catch (err) {
      results.push({ fixture: name, target, error: String(err?.message ?? err) });
      console.log(`${name} → ${target}: ERROR ${err?.message ?? err}`);
    }
  }
}
fs.writeFileSync("/tmp/matrix.json", JSON.stringify(results, null, 2));
