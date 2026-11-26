# Pruebas de navegador

Pruebas con [Playwright](https://playwright.dev/) (MIT) del motor de
conversión en el navegador (`web/engine/`) y de la web real (`web/`).

## Qué se prueba

- `privacy.spec.js` — **privacidad**: durante una conversión real en el
  navegador con el worker empaquetado (`web/engine/dist/worker.js`, los
  tres destinos: Excel, Word y PowerPoint) no sale ninguna petición de
  red salvo archivos estáticos del mismo origen (módulos JS y el wasm
  de MuPDF). La prueba falla si aparece cualquier otra petición (otro
  origen, `/api`, telemetría, CDN…). Medido el 26 nov 2026 en Chromium:
  6 peticiones estáticas locales durante la conversión.
- `privacy.spec.js` — **móvil con recursos limitados**: la misma
  conversión en emulación Pixel 7 con CPU limitada 4x (CDP
  `Emulation.setCPUThrottlingRate`) y heap V8 de 512 MB
  (`--js-flags=--max-old-space-size=512`).
- `convert.spec.js` — **la web real** (`web/index.html`): subir
  `factura.pdf`, convertir a Excel en Chromium (la cifra TOTAL 335
  llega al `.xlsx` y la calidad es texto 100 % / cifras 100 %) y a
  Word en Pixel 7 (el texto de la factura llega al `.docx`). También
  comprueba que no sale ninguna petición fuera del origen local.

La página de prueba de privacidad es `fixtures/privacy-app.html`,
servida por un servidor estático local que levanta la propia prueba
(sin dependencias externas). La prueba de la web real sirve `web/`
desde un servidor estático local en el mismo puerto.

**Requisito:** antes de Playwright hay que construir el motor
(`npm run build` en `web/engine/`), que genera `web/engine/index.js`,
`web/engine/dist/worker.js` y `web/engine/vendor/mupdf/`. Sin el
build, la web queda en modo demostración y `convert.spec.js` falla.
La CI (`.github/workflows/ci.yml`, trabajo `browser`) ya lo hace.

Complemento: `web/engine/tests/network.test.js` (vitest, en Node)
bloquea fetch/XHR durante la conversión y comprueba que no se llama;
esta prueba de Playwright lo verifica en un navegador real,
observando las peticiones de red durante la conversión.

## Limitaciones conocidas

- Sin OCR en las pruebas (`ocr: false`): los escaneados salen sin
  texto, igual que el motor Python sin Tesseract en este entorno. El
  OCR en el navegador (tesseract.js con datos spa+eng) no se ha
  probado en un navegador real todavía.
- WebKit no se ejecuta en la VM de trabajo (faltan dependencias del
  SO); en CI se instala con `--with-deps` y sí se prueba.

## Ejecutar

```sh
cd web/engine && npm ci && npm run build && cd ../..
cd tests/browser
npm ci
npx playwright install --with-deps chromium firefox webkit
npx playwright test                 # todos los proyectos
npx playwright test --project=chromium
```

## Resultados medidos (26 nov 2026, VM de trabajo)

| Prueba | Resultado |
|---|---|
| convert.spec.js Chromium (factura → Excel) | pasa en 5,6 s; calidad 100 % / 100 %; TOTAL 335 en el .xlsx |
| convert.spec.js móvil Pixel 7 (factura → Word) | pasa en 5,0 s; «335» en el .docx |
| privacy.spec.js Chromium (3 destinos) | pasa en 2,4 s; 6 peticiones estáticas, 0 externas |
| privacy.spec.js móvil CPU 4x (3 destinos) | pasa en 4,7 s; 0 peticiones externas |
| privacy.spec.js Firefox (3 destinos) | pasa en 3,5 s; 0 peticiones externas |
| WebKit | sin medir en esta VM (sin dependencias del SO); en CI con `--with-deps` |
