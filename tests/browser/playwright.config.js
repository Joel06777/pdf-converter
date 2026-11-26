// Configuración de Playwright para las pruebas de navegador.
// Proyectos: Chromium, Firefox y WebKit (escritorio) + emulación de celular
// (Pixel 7). La CPU limitada y la memoria reducida se aplican en la prueba
// de móvil (privacy.spec.js) con CDP + flags de lanzamiento de Chromium.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 120 * 1000,
  expect: { timeout: 30 * 1000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8931",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
