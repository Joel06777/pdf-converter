/* Frontend de ejemplo (HTML + JS puro). Flujo nuevo: pide un token de subida
   a la función serverless /api/upload-token y sube el PDF DIRECTO al backend
   con ese token (sin pasar por Vercel, que limita a 4,5 MB); el estado y la
   descarga también van directos al backend. Si el token no se puede obtener,
   usa como respaldo el flujo antiguo por /api/convert.
   La clave de API NUNCA va en el navegador. */
(function () {
  "use strict";
  var file = null;
  var drop = document.getElementById("drop");
  var fileInput = document.getElementById("fileInput");
  var fileInfo = document.getElementById("fileInfo");
  var convertBtn = document.getElementById("convertBtn");
  var progressBox = document.getElementById("progress");
  var barFill = document.getElementById("barFill");
  var progressText = document.getElementById("progressText");
  var qualityBox = document.getElementById("quality");
  var errorBox = document.getElementById("error");
  var downloadLink = document.getElementById("download");

  function setFile(f) {
    if (!f) return;
    if (f.type !== "application/pdf" && !/\.pdf$/i.test(f.name)) {
      showError("El archivo debe ser un PDF.");
      return;
    }
    if (f.size > 50 * 1024 * 1024) {
      showError("El archivo supera 50 MB.");
      return;
    }
    file = f;
    fileInfo.hidden = false;
    fileInfo.textContent = f.name + " — " + (f.size / 1024 / 1024).toFixed(2) + " MB";
    convertBtn.disabled = false;
    hideError();
  }

  function showError(msg) {
    errorBox.hidden = false;
    errorBox.textContent = msg;
  }
  function hideError() { errorBox.hidden = true; errorBox.textContent = ""; }

  document.getElementById("pickBtn").addEventListener("click", function () { fileInput.click(); });
  fileInput.addEventListener("change", function () { setFile(fileInput.files[0]); });
  drop.addEventListener("dragover", function (e) { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", function () { drop.classList.remove("over"); });
  drop.addEventListener("drop", function (e) {
    e.preventDefault();
    drop.classList.remove("over");
    setFile(e.dataTransfer.files[0]);
  });

  function pct(q) {
    return q == null ? "—" : Math.round(q * 100) + " %";
  }

  function showQuality(info) {
    var q = info && info.quality;
    qualityBox.hidden = false;
    qualityBox.classList.remove("warn");
    if (!q || !q.verifiable) {
      qualityBox.textContent = "Documento escaneado: el texto se reconoció con OCR propio. Revisa el resultado antes de usarlo.";
      qualityBox.classList.add("warn");
      return;
    }
    var text = "Calidad de la conversión — texto: " + pct(q.text_coverage) +
      " · cifras: " + pct(q.number_coverage) + ".";
    if (q.missing_sample && q.missing_sample.length) {
      text += " No se encontró en el resultado: " + q.missing_sample.join(", ") + ".";
      qualityBox.classList.add("warn");
    }
    if (info.ocr_warning) {
      text += " " + info.ocr_warning;
      qualityBox.classList.add("warn");
    }
    qualityBox.textContent = text;
  }

  // Flujo nuevo (directo): el navegador pide un token de subida a la función
  // serverless /api/upload-token (que usa la clave solo en el servidor) y luego
  // sube el PDF DIRECTO al backend con ese token, sin pasar por Vercel: así
  // no aplica el límite de 4,5 MB del plan Hobby. El estado y la descarga
  // también van directos al backend. La clave de API NUNCA va en el navegador.
  var backendUrl = null; // base del backend en modo directo; null = flujo antiguo

  function startDirectUpload(tokenInfo) {
    backendUrl = tokenInfo.backend_url || null;
    var form = new FormData();
    form.append("file", file);
    form.append("target", document.getElementById("target").value);
    form.append("layout", document.getElementById("layout").value);

    fetch(tokenInfo.upload_url, {
      method: "POST",
      headers: { "X-Upload-Token": tokenInfo.upload_token },
      body: form,
    })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error(j.detail || "No se pudo subir el PDF."); });
        return r.json();
      })
      .then(function (created) { poll(created.job_id); })
      .catch(function (err) {
        progressBox.hidden = true;
        convertBtn.disabled = false;
        showError(err.message);
      });
  }

  function startLegacyUpload() {
    // Respaldo: flujo antiguo por la función serverless /api/convert, que
    // reenvía el PDF al backend. Solo sirve para PDFs de hasta 4,5 MB en el
    // plan Hobby de Vercel.
    backendUrl = null;
    var form = new FormData();
    form.append("file", file);
    form.append("target", document.getElementById("target").value);
    form.append("layout", document.getElementById("layout").value);

    fetch("/api/convert", { method: "POST", body: form })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (j) { throw new Error(j.detail || "No se pudo iniciar la conversión."); });
        return r.json();
      })
      .then(function (created) { poll(created.job_id); })
      .catch(function (err) {
        progressBox.hidden = true;
        convertBtn.disabled = false;
        showError(err.message);
      });
  }

  convertBtn.addEventListener("click", function () {
    if (!file) return;
    hideError();
    qualityBox.hidden = true;
    downloadLink.hidden = true;
    progressBox.hidden = false;
    barFill.style.width = "5%";
    progressText.textContent = "Subiendo…";
    convertBtn.disabled = true;

    // 1) Pedir el token de subida (la clave solo la conoce el servidor).
    // Si este paso falla (p. ej. el backend aún no tiene subida directa),
    // se usa el flujo antiguo como respaldo.
    fetch("/api/upload-token", { method: "POST" })
      .then(function (r) {
        if (!r.ok) throw new Error("sin token");
        return r.json();
      })
      .then(function (tokenInfo) {
        if (!tokenInfo.upload_token || !tokenInfo.upload_url) throw new Error("sin token");
        startDirectUpload(tokenInfo);
      })
      .catch(function () { startLegacyUpload(); });
  });

  function poll(jobId) {
    var timer = setInterval(function () {
      // En modo directo el estado se consulta directo al backend; en el
      // flujo antiguo, a través de la función serverless /api/jobs.
      var url = backendUrl
        ? backendUrl + "/api/v1/jobs/" + jobId
        : "/api/jobs?id=" + jobId;
      fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (job) {
          var p = job.progress || 0;
          barFill.style.width = Math.max(5, Math.round(p * 100)) + "%";
          progressText.textContent = job.status === "processing"
            ? "Convirtiendo… página " + (job.pages_done || 0) + " de " + (job.pages_total || "?")
            : job.status === "queued" ? "En cola…" : job.status;
          if (job.status === "done") {
            clearInterval(timer);
            progressText.textContent = "Listo.";
            barFill.style.width = "100%";
            // La URL de descarga del backend es relativa: en modo directo se
            // completa con la base del backend; en el flujo antiguo ya viene
            // reescrita a /api/download por la función serverless.
            downloadLink.href = backendUrl && job.download_url &&
              job.download_url.charAt(0) === "/"
              ? backendUrl + job.download_url
              : job.download_url;
            downloadLink.hidden = false;
            convertBtn.disabled = false;
            showQuality(job.info);
          } else if (job.status === "error" || job.status === "cancelled") {
            clearInterval(timer);
            progressBox.hidden = true;
            convertBtn.disabled = false;
            showError(job.error || "La conversión fue cancelada.");
          }
        })
        .catch(function () { /* reintento en el siguiente ciclo */ });
    }, 1000);
  }
})();
