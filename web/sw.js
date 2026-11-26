/* Service Worker (PWA): uso sin conexión tras la primera visita.
   Estrategia: la cáscara de la app (HTML, CSS, JS y librerías vendidas)
   se guarda en caché en la instalación y se sirve desde caché.
   El motor (web/engine/) y las librerías grandes (vendor/) NO pasan por
   el service worker: su descarga (varios MB, con compresión) se atascaba
   a veces cuando el worker intentaba guardarla en caché y la conversión
   se quedaba en «Descargando MuPDF.js…». Van directas a la red; la caché
   HTTP del navegador (max-age) las guarda para la próxima visita.
   Los datos de idioma del OCR y los archivos del usuario NUNCA se
   guardan en caché: no son parte de la app. */
var CACHE_NAME = "pdf-converter-v3";
var APP_SHELL = [
  "./",
  "./index.html",
  "./excel.html",
  "./word.html",
  "./pptx.html",
  "./privacy.html",
  "./styles.css",
  "./config.js",
  "./engine.js",
  "./writers.js",
  "./app.js",
  "./manifest.webmanifest",
  "./favicon.svg",
  "./vendor/fflate/fflate-0.8.2.js",
  "./vendor/exceljs/exceljs-4.4.0.min.js",
  "./vendor/docx/docx-9.16.0.iife.js",
  "./vendor/pptxgenjs/pptxgenjs-4.0.1.bundle.js",
  "./vendor/pdfjs/pdf-5.5.207.min.mjs",
  "./vendor/pdfjs/pdf-5.5.207.worker.min.mjs",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
        /* `reload` obliga a bajar los archivos de la red: sin esto la
           instalación podría guardar la copia vieja que el navegador
           tenga en su caché HTTP y el cambio no llegaría nunca. */
        return Promise.all(APP_SHELL.map(function (u) {
          return cache.add(new Request(u, { cache: "reload" }));
        }));
      })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE_NAME; }).map(function (k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  /* Solo se cachea lo del propio sitio. Nada de terceros. */
  if (url.origin !== self.location.origin) return;
  /* El motor y las librerías grandes NO pasan por el service worker:
     su descarga (varios MB, con compresión) se atascaba a veces cuando
     el worker intentaba guardarla en caché. Van directas a la red; la
     caché HTTP del navegador (max-age) las guarda para la próxima vez. */
  if (url.pathname.indexOf("/engine/") === 0 || url.pathname.indexOf("/vendor/") === 0) return;
  /* Los archivos del usuario (blob:) no pasan por aquí: fetch solo ve
     peticiones de red del mismo origen. */
  event.respondWith(
    caches.match(event.request, { ignoreSearch: true }).then(function (cached) {
      if (cached) return cached;
      return fetch(event.request);
    })
  );
});
