/* Aplicación principal del convertidor web.
   HTML + JavaScript puro, sin frameworks. Todo ocurre en el navegador:
   el PDF no sale del dispositivo salvo que el dueño active el servidor
   opcional (ver web/config.js y docs/SERVIDOR_OPCIONAL.md). */
(function () {
  "use strict";

  var cfg = window.PDF_CONVERTER_CONFIG || {};
  var $ = function (id) { return document.getElementById(id); };

  /* ---------- Capacidad del dispositivo (Fase 4) ---------- */
  var device = {
    memoryGB: (navigator.deviceMemory || null), // puede no existir (Safari)
    cores: navigator.hardwareConcurrency || null,
    mobile: /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent),
    lowEnd: false,
    maxPages: 200,
    maxMB: 50,
  };
  (function detectDevice() {
    var lowMem = device.memoryGB != null && device.memoryGB <= 2;
    var fewCores = device.cores != null && device.cores <= 2;
    device.lowEnd = device.mobile && (lowMem || fewCores);
    if (device.memoryGB != null && device.memoryGB <= 2) { device.maxPages = 20; device.maxMB = 10; }
    else if (device.memoryGB != null && device.memoryGB <= 4) { device.maxPages = 60; device.maxMB = 25; }
    else if (device.mobile) { device.maxPages = 100; device.maxMB = 25; }
  })();

  /* ---------- Estado ---------- */
  var state = {
    files: [],           // [{ file, name, size, buffer, doc, pageCount, encrypted }]
    engine: null,
    engineState: "idle", // idle | loading | ready | missing | error
    serverState: "unknown", // unknown | ok | down
    converting: false,
    currentModel: null,  // modelo del archivo activo (para vista previa y corrector)
    currentFileIndex: 0,
    results: [],         // [{ name, blob, quality, ocr_warning }]
    timings: {},
    errors: [],
    embedded: false, // true cuando viene incrustado en Pdfaria (?target=)
    plan: "free",    // plan de Pdfaria cuando viene incrustado: free | premium
  };

  /* ---------- Utilidades ---------- */
  function fmtMB(bytes) { return (bytes / 1024 / 1024).toFixed(2) + " MB"; }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function announce(msg) { var a = $("srStatus"); if (a) a.textContent = msg; }
  function show(box, msg) { if (!box) return; box.hidden = false; box.textContent = msg; }
  function hide(box) { if (!box) return; box.hidden = true; }
  function setProgress(frac, msg) {
    var bar = $("barFill"), txt = $("progressText"), box = $("progress");
    if (box) box.hidden = false;
    // <progress> nativo: el ancho se pinta sin estilos en línea, que la
    // CSP (style-src 'self') bloquea.
    if (bar) { bar.value = Math.round(frac * 100); }
    if (txt) txt.textContent = msg;
    announce(msg);
  }
  function logError(code, msg) {
    state.errors.push({ code: code, message: msg, at: new Date().toISOString() });
  }

  /* ---------- Mensajes de capacidad ---------- */
  function deviceNote() {
    var parts = [];
    if (device.memoryGB) parts.push("memoria aproximada: " + device.memoryGB + " GB");
    if (device.cores) parts.push(device.cores + " núcleos");
    parts.push("límite recomendado: " + device.maxPages + " páginas y " + device.maxMB + " MB por archivo");
    return parts.join(" · ");
  }

  /* ---------- Límite del plan de Pdfaria (solo incrustado) ----------
     Gratis: 4 conversiones al día y 25 MB por archivo.
     Premium: conversiones ilimitadas y 500 MB por archivo.
     Se cuenta en este origen (localStorage), un contador por día. */
  function quotaKey() {
    var d = new Date();
    var day = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    return "pdfconv-quota-" + day;
  }
  function quotaUsed() {
    if (!state.embedded || state.plan === "premium") return 0;
    try { return parseInt(localStorage.getItem(quotaKey()) || "0", 10) || 0; }
    catch (e) { return 0; }
  }
  function quotaConsume() {
    if (!state.embedded || state.plan === "premium") return;
    try { localStorage.setItem(quotaKey(), String(quotaUsed() + 1)); }
    catch (e) { /* sin almacenamiento: no se cuenta */ }
  }

  /* ---------- Carga diferida del motor ---------- */
  async function ensureEngine() {
    if (state.engine) return state.engine;
    if (state.engineState === "missing") throw new Error("ENGINE_MISSING");
    /* Si una carga anterior ya falló, el motor quedó a medias y un nuevo
       intento daría un error confuso («motor no inicializado»); lo único
       que lo arregla es recargar la página. */
    if (state.engineState === "error") throw new Error("El motor no se pudo cargar. Recarga la página y vuelve a intentarlo.");
    state.engineState = "loading";
    setProgress(0.05, "Cargando el motor de conversión…");
    try {
      state.engine = await Promise.race([
        window.PdfConverterEngineLoader.loadEngine(function (f, m) {
          setProgress(0.05 + f * 0.85, m || "Cargando el motor…");
        }),
        /* Seguridad: la carga del motor nunca puede quedarse colgada para
           siempre; si tarda más de 2 minutos, se avisa y se reintenta. */
        new Promise(function (_, reject) {
          setTimeout(function () {
            var e = new Error("El motor tardó demasiado en cargar. Comprueba tu conexión, recarga la página y vuelve a intentarlo.");
            e.code = "ENGINE_TIMEOUT";
            reject(e);
          }, 120000);
        }),
      ]);
      state.engineState = "ready";
      setProgress(1, "Motor listo.");
      return state.engine;
    } catch (err) {
      state.engineState = err.code === "ENGINE_MISSING" ? "missing" : "error";
      logError(err.code || "ENGINE_ERROR", err.message);
      throw err;
    }
  }

  /* ---------- Vista previa con pdf.js (carga diferida) ---------- */
  var pdfjsLib = null;
  async function ensurePdfjs() {
    if (pdfjsLib) return pdfjsLib;
    var base = cfg.vendorBase === "jsdelivr"
      ? (cfg.jsdelivrBase || "https://cdn.jsdelivr.net/npm") + "/pdfjs-dist@5.5.207/build/"
      : "./vendor/pdfjs/";
    pdfjsLib = await import(base + "pdf-5.5.207.min.mjs");
    pdfjsLib.GlobalWorkerOptions.workerSrc = base + "pdf-5.5.207.worker.min.mjs";
    return pdfjsLib;
  }

  async function openPdfWithPdfjs(item) {
    var lib = await ensurePdfjs();
    var pdf = await lib.getDocument({ data: item.buffer.slice(0) }).promise;
    item.pdfjsDoc = pdf;
    item.pageCount = pdf.numPages;
    return pdf;
  }

  async function renderPreviewPage(item, pageIndex) {
    var canvas = $("previewPdf");
    if (!canvas || !item.pdfjsDoc) return;
    var page = await item.pdfjsDoc.getPage(pageIndex + 1);
    var viewport = page.getViewport({ scale: 1.4 });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvasContext: canvas.getContext("2d"), viewport: viewport }).promise;
    var label = $("previewPageLabel");
    if (label) label.textContent = "Página " + (pageIndex + 1) + " de " + item.pageCount + " — " + item.name;
  }

  /* ---------- Archivos ---------- */
  function validateFile(file) {
    if (file.type !== "application/pdf" && !/\.pdf$/i.test(file.name)) {
      return "«" + file.name + "» no es un PDF. Elige un archivo .pdf.";
    }
    if (file.size > device.maxMB * 1024 * 1024) {
      return "«" + file.name + "» pesa " + fmtMB(file.size) + ". Este dispositivo admite hasta " +
        device.maxMB + " MB por archivo. Prueba con un PDF más pequeño o con un rango de páginas.";
    }
    return null;
  }

  async function addFiles(fileList) {
    hide($("error"));
    var added = 0;
    for (var i = 0; i < fileList.length; i++) {
      var file = fileList[i];
      var problem = validateFile(file);
      if (problem) { show($("error"), problem); logError("FILE_REJECTED", problem); continue; }
      var buffer = await file.arrayBuffer();
      var item = { file: file, name: file.name, size: file.size, buffer: buffer, pageCount: null };
      state.files.push(item);
      added++;
    }
    if (added) {
      renderFileList();
      $("options").hidden = false;
      $("convertBtn").disabled = false;
      var first = state.files[state.currentFileIndex];
      await inspectFile(first);
    }
    updateMergeOption();
  }

  async function inspectFile(item) {
    var t0 = performance.now();
    try {
      await openPdfWithPdfjs(item);
    } catch (err) {
      var msg = /password|encrypted/i.test(err.message)
        ? "«" + item.name + "» tiene contraseña. Quítale la contraseña y vuelve a intentarlo; no se puede convertir un PDF protegido."
        : "«" + item.name + "» no se pudo abrir: parece estar dañado o no es un PDF válido.";
      show($("error"), msg);
      logError("PDF_OPEN", msg);
      return;
    }
    state.timings.previewMs = Math.round(performance.now() - t0);
    if (item.pageCount > device.maxPages) {
      show($("error"),
        "Este PDF tiene " + item.pageCount + " páginas y es grande para tu dispositivo " +
        "(" + deviceNote() + "). Prueba con un rango de páginas (por ejemplo, 1–" + device.maxPages + ").");
      logError("TOO_BIG", "pages=" + item.pageCount);
    }
    setPageRangeDefaults(item.pageCount);
    await renderPreviewPage(item, 0);
    $("preview").hidden = false;
    updateEngineStatus();
  }

  function setPageRangeDefaults(pageCount) {
    var from = $("pageFrom"), to = $("pageTo");
    if (!from || !to) return;
    from.max = pageCount; to.max = pageCount;
    from.value = 1;
    to.value = Math.min(pageCount, device.maxPages);
    $("rangeHint").textContent = "El PDF tiene " + pageCount + " páginas.";
  }

  function renderFileList() {
    var list = $("fileList");
    if (!list) return;
    list.innerHTML = "";
    state.files.forEach(function (item, idx) {
      var li = el("li");
      var btn = el("button", "file-item", item.name + " — " + fmtMB(item.size) +
        (item.pageCount ? " — " + item.pageCount + " pág." : ""));
      btn.type = "button";
      btn.setAttribute("aria-pressed", idx === state.currentFileIndex ? "true" : "false");
      btn.addEventListener("click", async function () {
        state.currentFileIndex = idx;
        renderFileList();
        await inspectFile(item);
      });
      var rm = el("button", "file-remove", "Quitar");
      rm.type = "button";
      rm.setAttribute("aria-label", "Quitar " + item.name);
      rm.addEventListener("click", function () {
        state.files.splice(idx, 1);
        if (state.currentFileIndex >= state.files.length) state.currentFileIndex = 0;
        renderFileList();
        updateMergeOption();
        if (!state.files.length) { $("options").hidden = true; $("convertBtn").disabled = true; $("preview").hidden = true; }
      });
      li.appendChild(btn); li.appendChild(rm);
      list.appendChild(li);
    });
  }

  function updateMergeOption() {
    var merge = $("mergeBook");
    if (!merge) return;
    var target = $("target").value;
    merge.disabled = !(state.files.length > 1 && target === "excel");
    if (merge.disabled) merge.checked = false;
    $("mergeHint").textContent = state.files.length > 1 && target === "excel"
      ? "Con varios archivos y destino Excel puedes unirlos en un solo libro (una hoja por archivo)."
      : "La unión en un solo libro solo aplica a varios archivos con destino Excel.";
  }

  /* ---------- Estado del motor / servidor ---------- */
  async function updateEngineStatus() {
    var box = $("engineStatus");
    if (!box) return;
    if (state.engineState === "ready") {
      box.textContent = "Motor listo: " + (state.engine.engineName || "") + ". La conversión ocurre en tu dispositivo.";
      box.className = "status ok";
      return;
    }
    var available = await window.PdfConverterEngineLoader.engineAvailable();
    if (available) {
      box.textContent = "Motor disponible. Se cargará cuando elijas un archivo (primera vez tarda unos segundos).";
      box.className = "status";
    } else {
      box.textContent = "Motor del navegador aún no instalado (modo de demostración): la vista previa funciona, " +
        "pero convertir todavía no. El archivo no sale de tu dispositivo en ningún caso.";
      box.className = "status warn";
    }
  }

  async function checkServer() {
    if (!cfg.serverUrl) { state.serverState = "unknown"; return; }
    try {
      var res = await fetch(cfg.serverUrl.replace(/\/$/, "") + "/health", { method: "GET", cache: "no-store" });
      state.serverState = res.ok ? "ok" : "down";
    } catch (err) {
      state.serverState = "down";
    }
    var box = $("serverStatus");
    if (box) {
      box.hidden = false;
      box.textContent = state.serverState === "ok"
        ? "Servidor opcional disponible. Solo se usará si el motor del navegador no puede con tu PDF, y te avisará antes."
        : "Servidor opcional no disponible ahora. No pasa nada: el convertidor del navegador sigue funcionando solo.";
      box.className = "status " + (state.serverState === "ok" ? "ok" : "warn");
    }
  }

  /* ---------- Conversión ---------- */
  function getRange(item) {
    var from = Math.max(1, parseInt($("pageFrom").value, 10) || 1);
    var to = Math.min(item.pageCount, parseInt($("pageTo").value, 10) || item.pageCount);
    if (from > to) { var tmp = from; from = to; to = tmp; }
    return { from: from, to: to };
  }

  async function convertAll() {
    if (state.converting) return;
    hide($("error")); hide($("quotaUpsell")); hide($("quality")); hide($("downloadBox"));
    if (state.embedded && state.plan !== "premium" && quotaUsed() >= 4) {
      show($("error"), "Llegaste a las 4 conversiones gratis de hoy en Pdfaria.");
      var up = $("quotaUpsell");
      if (up) up.hidden = false;
      logError("QUOTA", "Límite de 4 conversiones diarias del plan gratis.");
      return;
    }
    state.results = [];
    state.converting = true;
    $("convertBtn").disabled = true;
    var t0 = performance.now();
    try {
      var engine = await ensureEngine();
      var target = $("target").value;
      var unreadable = state.files.filter(function (f) { return !f.pageCount; });
      if (unreadable.length) {
        throw new Error("«" + unreadable[0].name + "» no se pudo abrir. Prueba con otro PDF.");
      }
      var rangeByFile = state.files.map(getRange);
      var models = [];
      for (var i = 0; i < state.files.length; i++) {
        var item = state.files[i];
        var range = rangeByFile[i];
        setProgress((i / state.files.length) * 0.5,
          "Leyendo «" + item.name + "» (páginas " + range.from + "–" + range.to + ")…");
        var doc = await engine.open(item.buffer.slice(0), item.name);
        var model = await engine.extract(doc, {
          from: range.from, to: range.to,
          onProgress: (function (idx, total) {
            return function (done, totalPages, msg) {
              setProgress(
                (idx / total) * 0.5 + (done / Math.max(1, totalPages)) * (0.5 / total),
                msg || ("Procesando página " + done + " de " + totalPages + "…")
              );
            };
          })(i, state.files.length),
        });
        model.sourceName = item.name;
        models.push(model);
        if (engine.dispose) engine.dispose(doc);
      }
      state.currentModel = models[state.currentFileIndex] || models[0];
      renderModelPreview(state.currentModel);
      renderCorrector(state.currentModel);

      /* Escritura de salida */
      var layout = $("excelLayout").value;
      var outExt = { excel: "xlsx", word: "docx", pptx: "pptx" }[target];
      var outputs = [];
      if (target === "excel" && $("mergeBook").checked && models.length > 1) {
        var merged = { pages: [], doubtfulCells: [], quality: null, ocr_warning: "" };
        models.forEach(function (m) {
          m.pages.forEach(function (p) { merged.pages.push(p); });
          merged.doubtfulCells = merged.doubtfulCells.concat(m.doubtfulCells || []);
        });
        merged.quality = models[0].quality;
        var blob = await window.PdfWriters.writeExcel(merged, { excelLayout: "pages" });
        outputs.push({ name: "libro-unido." + outExt, blob: blob, quality: merged.quality, ocr_warning: merged.ocr_warning });
      } else {
        for (var j = 0; j < models.length; j++) {
          setProgress(0.5 + (j / models.length) * 0.5, "Escribiendo el archivo " + (j + 1) + " de " + models.length + "…");
          var b;
          if (target === "excel") b = await window.PdfWriters.writeExcel(models[j], { excelLayout: layout });
          else if (target === "word") b = await window.PdfWriters.writeWord(models[j], {});
          else b = await window.PdfWriters.writePptx(models[j], {});
          var base = models[j].sourceName.replace(/\.pdf$/i, "");
          outputs.push({ name: base + "." + outExt, blob: b, quality: models[j].quality, ocr_warning: models[j].ocr_warning });
        }
      }
      state.results = outputs;
      state.timings.totalMs = Math.round(performance.now() - t0);
      showResults(outputs);
      quotaConsume();
      setProgress(1, "Listo.");
    } catch (err) {
      state.converting = false;
      $("convertBtn").disabled = false;
      hide($("progress"));
      if (err.code === "ENGINE_MISSING" || /ENGINE_MISSING/.test(err.message)) {
        var msg = "El motor de conversión del navegador aún no está instalado en esta versión. " +
          "Puedes ver la vista previa de tu PDF, pero la conversión llegará con la próxima actualización. " +
          (cfg.serverUrl
            ? "Si el dueño activó el servidor opcional, prueba de nuevo: se usará como respaldo."
            : "Si el dueño activa el servidor opcional, esa será la vía de respaldo.");
        show($("error"), msg);
        logError("ENGINE_MISSING", msg);
        return;
      }
      if (err.message === "encrypted" || /contraseña|password/i.test(err.message)) {
        show($("error"), "Este PDF tiene contraseña. Quítale la contraseña y vuelve a intentarlo; no se puede convertir un PDF protegido.");
        logError("ENCRYPTED", err.message);
        return;
      }
      show($("error"), "No se pudo convertir: " + err.message + " Prueba con otro PDF o con un rango de páginas más corto.");
      logError("CONVERT", err.message);
    } finally {
      state.converting = false;
      $("convertBtn").disabled = false;
    }
  }

  function showResults(outputs) {
    var box = $("downloadBox");
    if (!box) return;
    box.hidden = false;
    var list = $("downloadList");
    if (!list) return;
    list.innerHTML = "";
    var q = outputs[0] && outputs[0].quality;
    var qualityBox = $("quality");
    if (q) {
      var text = "Calidad de la conversión — texto: " + Math.round((q.text_coverage || 0) * 100) + " % · cifras: " +
        Math.round((q.number_coverage || 0) * 100) + " %.";
      if (q.missing_sample && q.missing_sample.length) text += " No llegó al resultado: " + q.missing_sample.join(", ") + ".";
      if (outputs[0].ocr_warning) text += " " + outputs[0].ocr_warning;
      show(qualityBox, text);
      qualityBox.classList.toggle("warn", (q.text_coverage || 1) < 1 || (q.number_coverage || 1) < 1 || !!outputs[0].ocr_warning);
    }
    outputs.forEach(function (o) {
      var a = el("a", "download", "Descargar " + o.name + " (" + fmtMB(o.blob.size) + ")");
      a.href = URL.createObjectURL(o.blob);
      a.download = o.name;
      list.appendChild(a);
    });
    if (outputs.length > 1) {
      var zipBtn = el("button", "download", "Descargar todo en un ZIP");
      zipBtn.type = "button";
      zipBtn.addEventListener("click", async function () {
        try {
          var files = [];
          for (var i = 0; i < outputs.length; i++) {
            files.push({ name: outputs[i].name, data: new Uint8Array(await outputs[i].blob.arrayBuffer()) });
          }
          var zip = await window.PdfWriters.zipFiles(files);
          var a = el("a");
          a.href = URL.createObjectURL(zip);
          a.download = "conversiones.zip";
          a.click();
        } catch (err) {
          show($("error"), "No se pudo crear el ZIP: " + err.message);
        }
      });
      list.appendChild(zipBtn);
    }
    var again = el("p", "hint", "Los archivos se guardaron en tu dispositivo. Cierra esta pestaña cuando quieras: nada quedó subido a ningún servidor.");
    list.appendChild(again);
    announce("Conversión lista. Ya puedes descargar el resultado.");
  }

  /* ---------- Vista previa del resultado (lado a lado) ---------- */
  function renderModelPreview(model) {
    var box = $("previewResult");
    if (!box || !model) return;
    box.innerHTML = "";
    var page = model.pages[0];
    if (!page) { box.textContent = "Sin contenido extraído."; return; }
    if (!page.tables.length && page.texts.length) {
      page.texts.slice(0, 40).forEach(function (t) {
        box.appendChild(el("p", null, t.text));
      });
      return;
    }
    page.tables.slice(0, 2).forEach(function (table, ti) {
      box.appendChild(el("h3", null, "Tabla " + (ti + 1) + " (página " + page.pageNumber + ")"));
      var tbl = el("table", "result-table");
      table.rows.slice(0, 30).forEach(function (row) {
        var tr = el("tr");
        row.forEach(function (cell) {
          var td = el("td", (cell.doubtful ? "doubtful " : "") + (cell.bold ? "bold" : ""), cellValue(cell));
          tr.appendChild(td);
        });
        tbl.appendChild(tr);
      });
      box.appendChild(tbl);
    });
    box.appendChild(el("p", "hint", "Vista previa de la primera página convertida. El archivo descargado contiene todas las páginas del rango elegido."));
  }

  function cellValue(cell) {
    if (cell == null) return "";
    return cell.value == null ? "" : String(cell.value);
  }

  /* ---------- Corrector de celdas dudosas del OCR ---------- */
  function renderCorrector(model) {
    var box = $("corrector");
    var list = $("doubtfulList");
    if (!box || !list || !model) return;
    var cells = model.doubtfulCells || [];
    list.innerHTML = "";
    if (!cells.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    $("doubtfulCount").textContent = cells.length + " celda(s) dudosa(s) del OCR. Revísalas antes de descargar: corrige el valor si está mal.";
    cells.forEach(function (dc, idx) {
      var li = el("li");
      li.appendChild(el("span", null, "Pág. " + dc.page + " · fila " + (dc.row + 1) + ", col. " + (dc.col + 1) + " (confianza " + Math.round((dc.confidence || 0) * 100) + " %): "));
      var input = document.createElement("input");
      input.type = "text";
      input.value = dc.value == null ? "" : String(dc.value);
      input.setAttribute("aria-label", "Valor corregido para la celda dudosa " + (idx + 1));
      input.addEventListener("change", function () {
        dc.value = input.value;
        dc.corrected = true;
        /* Aplica la corrección al modelo para que salga en la descarga. */
        var page = model.pages.find(function (p) { return p.pageNumber === dc.page; });
        if (page && page.tables[dc.table] && page.tables[dc.table].rows[dc.row]) {
          var cell = page.tables[dc.table].rows[dc.row][dc.col];
          if (cell) { cell.value = input.value; cell.doubtful = false; }
        }
      });
      li.appendChild(input);
      list.appendChild(li);
    });
  }

  /* ---------- Informe técnico (sin contenido del documento) ---------- */
  function technicalReport() {
    var lines = [
      "Informe técnico — Convertidor PDF (navegador)",
      "Versión web: " + (cfg.webVersion || "?"),
      "Motor: " + (state.engine ? (state.engine.ENGINE_VERSION || state.engine.engineName || "cargado") : "no cargado (" + state.engineState + ")"),
      "Navegador: " + navigator.userAgent,
      "Dispositivo: " + (device.mobile ? "móvil" : "escritorio") +
        (device.memoryGB ? ", memoria aprox. " + device.memoryGB + " GB" : "") +
        (device.cores ? ", " + device.cores + " núcleos" : ""),
      "Archivos: " + state.files.map(function (f) { return f.name + " (" + fmtMB(f.size) + ", " + (f.pageCount || "?") + " pág.)"; }).join("; "),
      "Destino: " + ($("target") ? $("target").value : "?"),
      "Tiempos: vista previa " + (state.timings.previewMs || "?") + " ms; conversión total " + (state.timings.totalMs || "?") + " ms",
      "Errores: " + (state.errors.length ? state.errors.map(function (e) { return e.code + ": " + e.message; }).join(" | ") : "ninguno"),
      "Servidor opcional: " + (cfg.serverUrl ? cfg.serverUrl + " (" + state.serverState + ")" : "no configurado"),
      "Nota: este informe NO contiene texto ni cifras de tus documentos.",
    ];
    return lines.join("\n");
  }

  function issueUrl() {
    var body = encodeURIComponent(
      "Describe qué pasó (qué PDF usabas, qué esperabas y qué salió mal):\n\n\n---\nInforme técnico (sin contenido del documento):\n" + technicalReport()
    );
    return cfg.issueFormUrl + "?title=" + encodeURIComponent("Incidencia en la conversión web") +
      "&body=" + body + "&labels=" + encodeURIComponent("incidencia-web");
  }

  /* ---------- Arranque ---------- */
  function init() {
    var params = new URLSearchParams(location.search);
    var target = params.get("target");
    if (target && ["excel", "word", "pptx"].indexOf(target) >= 0) {
      $("target").value = target;
      /* Destino fijo cuando viene de Pdfaria: solo esa opción. */
      var sel = $("target");
      for (var i = sel.options.length - 1; i >= 0; i--) {
        if (sel.options[i].value !== target) sel.remove(i);
      }
      $("excelOptions").hidden = target !== "excel";
      state.embedded = true;
    }
    /* Plan de Pdfaria cuando viene incrustado (?plan=free|premium). */
    var plan = params.get("plan");
    state.plan = plan === "premium" ? "premium" : "free";
    if (state.embedded) {
      /* El tamaño máximo sigue el plan de Pdfaria, no el del dispositivo. */
      device.maxMB = state.plan === "premium" ? 500 : 25;
    }

    $("deviceNote").textContent = "Tu dispositivo: " + deviceNote() + ".";
    updateEngineStatus();
    checkServer();

    var drop = $("drop"), pickBtn = $("pickBtn"), fileInput = $("fileInput");
    pickBtn.addEventListener("click", function () { fileInput.click(); });
    fileInput.addEventListener("change", function () { addFiles(fileInput.files); fileInput.value = ""; });
    ["dragover", "dragenter"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); });
    });
    drop.addEventListener("drop", function (e) { addFiles(e.dataTransfer.files); });
    drop.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
    });

    $("target").addEventListener("change", function () {
      var isExcel = $("target").value === "excel";
      $("excelOptions").hidden = !isExcel;
      updateMergeOption();
    });
    $("convertBtn").addEventListener("click", convertAll);

    var prevBtn = $("prevPage"), nextBtn = $("nextPage");
    var previewIndex = 0;
    if (prevBtn) prevBtn.addEventListener("click", function () {
      var item = state.files[state.currentFileIndex];
      if (!item || !item.pageCount) return;
      previewIndex = Math.max(0, previewIndex - 1);
      renderPreviewPage(item, previewIndex);
    });
    if (nextBtn) nextBtn.addEventListener("click", function () {
      var item = state.files[state.currentFileIndex];
      if (!item || !item.pageCount) return;
      previewIndex = Math.min(item.pageCount - 1, previewIndex + 1);
      renderPreviewPage(item, previewIndex);
    });

    var issueLink = $("issueLink");
    if (issueLink) issueLink.addEventListener("click", function () { issueLink.href = issueUrl(); });

    if ("serviceWorker" in navigator) {
      window.addEventListener("load", function () {
        navigator.serviceWorker.register("./sw.js").catch(function () { /* sin conexión: la app igual funciona */ });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
