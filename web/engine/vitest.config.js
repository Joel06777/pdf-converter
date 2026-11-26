import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Las pruebas de OCR son lentas (varios segundos por página) y el motor
    // WASM no debe competir por CPU entre archivos: un solo proceso.
    pool: "forks",
    poolOptions: { forks: { singleFork: true } },
    testTimeout: 180_000,
    hookTimeout: 180_000,
    reporters: ["default"],
  },
});
