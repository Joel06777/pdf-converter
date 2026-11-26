# Roadmap (backlog priorizado)

Trabajo pendiente, ordenado por valor para el usuario. Cada punto
sigue el mismo ciclo: **medir → mejorar → probar → documentar**.
Nada se da por hecho sin medirlo primero en `docs/METRICAS.md`.

> Estado: 26 nov 2026. La integración motor ↔ web está hecha y
> verificada en Chromium, Firefox y Pixel 7 emulado (ver
> `tests/browser/README.md`): la web convierte de verdad en el
> navegador. Queda pendiente el OCR en el navegador real, WebKit,
> los casos hostiles y el flujo de respaldo al servidor opcional.

## 0. Terminar el motor del navegador (hecho el 26 nov 2026)

- `web/engine/index.js` (adaptador, opción A) expone
  `window.PdfConverterEngine` según el contrato de `web/README.md`;
  el motor se construye con `npm run build` (Vite 8) y produce
  `index.js`, `dist/worker.js`, `dist/tesseract-*` y
  `vendor/mupdf/`. Verificado en Chromium/Firefox/Pixel 7:
  factura → Excel con calidad 100 % / 100 % y TOTAL 335 en el
  `.xlsx`; factura → Word en Pixel 7.
- Pendiente de este punto: rellenar la tabla de
  `web/tests/hostile-cases.md` corriendo `web/tests/index.html`, y
  conectar el flujo de respaldo al servidor opcional en `web/` (hoy
  solo existe en `web-example/`). La paridad en Node ya cubre los 42
  PDFs del conjunto de oro (navegador: texto 0,9982 / cifras 1,0 en
  los 3 destinos; celdas Word 1,0 tras la decisión grid/flow por
  cifras aisladas); lo que sigue sin medir es la fidelidad en la web
  real más allá de la factura.

## 1. OCR más preciso

- Probar `tessdata_best` de español en el navegador (en el servidor
  se probó y **empeoró**: texto 97,9 % → 87,5 %; no adoptarlo sin
  medir de nuevo en el navegador).
- Probar el enderezado y la binarización del servidor en el motor
  del navegador y medir si recuperan cifras en fotos inclinadas.
- Criterio de aceptación: cifras al 100 % en los 5 casos de OCR
  medidos hoy en el servidor, sin bajar el texto.

## 2. Más tipos de documento

- **Tablas a CSV**: exportar cada tabla detectada como `.csv`
  (una descarga más, sin librería nueva: es texto plano).
- **PDF escaneado a PDF con texto seleccionable**: el escaneo con
  una capa de texto invisible encima (lo que hace OCRmyPDF en el
  servidor). Útil para archivar.
- **PDF a imágenes** (una imagen por página): para compartir por
  WhatsApp o revisar rápido. Sin librería nueva: el motor ya
  renderiza páginas.
- Después de cada tipo nuevo: medir, probar y documentar; no añadir
  un destino que no se haya medido.

## 3. Mejor Safari y celulares antiguos

- Probar la web en Safari (iOS y macOS) y en un Android antiguo:
  WebAssembly, `OffscreenCanvas`, Service Worker y descarga de
  archivos grandes se comportan distinto.
- Si Safari no admite algo, degradar con elegancia (mensaje claro
  + sugerir el servidor opcional) en vez de fallar en silencio.
- Medir los tiempos en un celular real de gama media y baja (hoy
  solo hay emulaciones planificadas; ver `docs/METRICAS.md`).

## 4. Menos peso de descarga

- El peso real ya está medido (26 nov 2026, Brotli): núcleo sin OCR
  3,85 MB → 26.626 visitas nuevas/mes en 100 GB/mes; con OCR completo
  8,70 MB → 11.782; primera visita 4,75 MB sin OCR y 9,60 MB con OCR
  (ver `docs/METRICAS.md`).
- Opciones si el motor pesa mucho: servir el motor desde jsDelivr o
  GitHub Pages con SRI (ver `web/README.md`), o dividir el motor en
  un núcleo pequeño + OCR bajo demanda.
- Criterio: la primera visita en un celular con 3G no debe tardar
  más de lo que tarda en abrirse la página hoy (sin medir: medir
  antes de prometer un número).

## 5. Calidad y confianza

- Que el informe de calidad del navegador mida lo mismo que el del
  servidor (`text_coverage`, `number_coverage`, `missing_sample`)
  y que la página lo muestre igual.
- Ampliar el corrector de celdas dudosas: mostrar la zona de la
  página original junto a la celda (recorte de imagen) para que
  corregir sea mirar y escribir, no adivinar.
- Guardar (solo en el dispositivo) los últimos ajustes del usuario
  (destino, diseño de Excel) para no elegirlos cada vez.

## 6. Distribución y lanzamiento

- Hacer público el repositorio (obligatorio por la AGPL-3.0 antes
  de lanzar).
- Publicar la web estática en Vercel según
  `docs/DESPLIEGUE_GRATIS.md` y comprobar la PWA en un celular real.
- Decidir el modelo de negocio **antes** de lanzar: si el
  convertidor va a ganar dinero, Vercel Hobby no sirve (uso no
  comercial) y hace falta el plan Pro u otro alojamiento.
- Poner la dirección real de contacto de privacidad en
  `docs/PRIVACIDAD.md` y en `web/privacy.html` (hoy es un marcador).

## Fuera de alcance (no se hará)

- Cuentas de usuario, historial en la nube o sincronización entre
  dispositivos: rompería la promesa de «el archivo no sale del
  dispositivo».
- Analítica de terceros o publicidad en la página.
- Convertir PDFs con contraseña adivinándola.
- Servidor obligatorio: el servidor seguirá siendo opcional.
