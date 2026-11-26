import fs from "node:fs";
import { convertPdf } from "../src/index.js";

const FIX = new URL("../../../tests/fixtures/", import.meta.url).pathname;
const name = process.argv[2] ?? "factura.pdf";
const target = process.argv[3] ?? "excel";
const t0 = Date.now();
const pdf = fs.readFileSync(`${FIX}${name}`);
const { buffer, info, quality } = await convertPdf(pdf, target, {
  onProgress: (p, t, stage) => console.log(`  progreso ${stage}: ${p}/${t}`),
});
console.log("target:", target, "fixture:", name, "ms:", Date.now() - t0);
console.log("info:", JSON.stringify(info, null, 1));
console.log("quality:", JSON.stringify(quality));
console.log("bytes:", buffer.length);
fs.writeFileSync(`/tmp/smoke.${target === "excel" ? "xlsx" : target === "word" ? "docx" : "pptx"}`, buffer);
