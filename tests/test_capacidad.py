"""Capacidad y protección: tope de cola (503) y tope de OCR por trabajo.

El tope de cola se comprueba con MAX_QUEUE_JOBS=0 (cualquier trabajo nuevo
supera el tope). El tope de OCR se comprueba con un PDF sintético de 21
páginas escaneadas (más que MAX_OCR_PAGES=20): el trabajo termina en error
con un mensaje claro, sin llegar a ejecutar OCR.
"""
import io
import time
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from app import jobs
from app.config import settings
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "factura.pdf"
client = TestClient(app)


def _wait(job_id):
    for _ in range(120):
        r = client.get(f"/api/v1/jobs/{job_id}").json()
        if r["status"] in ("done", "error"):
            return r
        time.sleep(0.5)
    raise AssertionError("timeout esperando el trabajo")


def _pdf_escaneado(n_paginas: int) -> bytes:
    """PDF sintético de n páginas escaneadas: cada página es una imagen a
    página completa sin capa de texto (la condición de OCR del convertidor)."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 140), "white").save(buf, format="PNG")
    png = buf.getvalue()
    doc = pymupdf.open()
    for _ in range(n_paginas):
        page = doc.new_page(width=612, height=792)
        page.insert_image(page.rect, stream=png)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def test_cola_llena_devuelve_503_en_convert(monkeypatch):
    monkeypatch.setattr(settings, "max_queue_jobs", 0)
    monkeypatch.setattr(settings, "rate_limit_per_hour", 10000)
    with open(FIX, "rb") as f:
        r = client.post("/api/v1/convert",
                        files={"file": ("factura.pdf", f, "application/pdf")},
                        data={"target": "excel"})
    assert r.status_code == 503
    assert r.json()["detail"] == "Estamos con mucha demanda, intenta en unos minutos"


def test_cola_llena_devuelve_503_en_convert_many(monkeypatch):
    monkeypatch.setattr(settings, "max_queue_jobs", 0)
    monkeypatch.setattr(settings, "rate_limit_per_hour", 10000)
    data = FIX.read_bytes()
    files = [("files", ("a.pdf", data, "application/pdf")),
             ("files", ("b.pdf", data, "application/pdf"))]
    r = client.post("/api/v1/convert-many", files=files, data={"target": "word"})
    assert r.status_code == 503
    assert "mucha demanda" in r.json()["detail"]


def test_cola_llena_devuelve_503_en_upload_sin_consumir_token(monkeypatch):
    monkeypatch.setattr(settings, "upload_secret", "secreto-subida-prueba")
    monkeypatch.setattr(settings, "api_key", "clave-prueba")
    monkeypatch.setattr(settings, "rate_limit_per_hour", 10000)
    import app.main as main

    main._hits.clear()
    token = client.post("/api/v1/upload-token",
                        headers={"X-API-Key": "clave-prueba"}, json={}).json()["upload_token"]
    monkeypatch.setattr(settings, "max_queue_jobs", 0)
    with open(FIX, "rb") as f:
        r = client.post("/api/v1/upload",
                        files={"file": ("factura.pdf", f, "application/pdf")},
                        data={"target": "excel"},
                        headers={"X-Upload-Token": token})
    assert r.status_code == 503
    assert "mucha demanda" in r.json()["detail"]
    # El rechazo por cola no consume el token: con la cola libre, el mismo
    # token sigue valiendo (reintento tras esperar unos minutos).
    monkeypatch.setattr(settings, "max_queue_jobs", 50)
    with open(FIX, "rb") as f:
        r = client.post("/api/v1/upload",
                        files={"file": ("factura.pdf", f, "application/pdf")},
                        data={"target": "excel"},
                        headers={"X-Upload-Token": token})
    assert r.status_code == 202, r.text
    assert _wait(r.json()["job_id"])["status"] == "done"


def test_count_active_jobs_cuenta_queued_y_processing():
    antes = jobs.count_active_jobs()
    a = jobs.new_job("excel", "a.pdf")
    b = jobs.new_job("word", "b.pdf")
    assert jobs.count_active_jobs() == antes + 2
    jobs.write_state(a, status="processing")
    assert jobs.count_active_jobs() == antes + 2
    jobs.write_state(a, status="done")
    jobs.write_state(b, status="error")
    assert jobs.count_active_jobs() == antes


def test_mas_paginas_escaneadas_que_max_ocr_pages_da_error(monkeypatch):
    monkeypatch.setattr(settings, "max_ocr_pages", 20)
    monkeypatch.setattr(settings, "rate_limit_per_hour", 10000)
    pdf = _pdf_escaneado(21)
    r = client.post("/api/v1/convert",
                    files={"file": ("escaneado21.pdf", pdf, "application/pdf")},
                    data={"target": "excel"})
    assert r.status_code == 202, r.text
    status = _wait(r.json()["job_id"])
    assert status["status"] == "error", status
    assert "21 páginas escaneadas" in status["error"]
    assert "20" in status["error"]
