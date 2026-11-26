"""Subida directa al backend con token firmado (sin pasar por Vercel).

Cubre: token válido permite subir; caducado, reutilizado y manipulado se
rechazan con 401; max_mb menor que el archivo se rechaza con 413; subida de
un PDF de 40 MB de principio a fin; /upload sin token da 401 y
/upload-token sin API key da 401.
"""
import os
import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.config import settings
from app.main import app

FIX = Path(__file__).parent / "fixtures" / "estado_ingresos_octubre_2026.pdf"
client = TestClient(app)
API_HEADERS = {"X-API-Key": "clave-prueba"}


@pytest.fixture(autouse=True)
def _credenciales(monkeypatch):
    """Secreto de subida y API key de prueba; límite de uso amplio y limpio."""
    monkeypatch.setattr(settings, "upload_secret", "secreto-subida-prueba")
    monkeypatch.setattr(settings, "api_key", "clave-prueba")
    monkeypatch.setattr(settings, "rate_limit_per_hour", 10000)
    import app.main as main

    main._hits.clear()
    yield
    main._hits.clear()


def _wait(job_id):
    for _ in range(120):
        r = client.get(f"/api/v1/jobs/{job_id}").json()
        if r["status"] in ("done", "error"):
            return r
        time.sleep(0.5)
    raise AssertionError("timeout esperando el trabajo")


def _token(headers=API_HEADERS, **kwargs):
    r = client.post("/api/v1/upload-token", headers=headers, json=kwargs)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expires_in"] == 300
    assert body["max_mb"] == settings.max_upload_mb
    assert body["upload_url"] == "/api/v1/upload"
    return body["upload_token"]


def _upload(token, pdf_bytes, target="excel", filename="doc.pdf"):
    return client.post(
        "/api/v1/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
        data={"target": target},
        headers={"X-Upload-Token": token} if token else {},
    )


def _pdf_grande(path: Path, relleno_mb: int) -> Path:
    """PDF sintético válido de ~relleno_mb MB: 2 páginas de texto + relleno
    binario incrustado (no comprimible), generado con PyMuPDF."""
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Página de prueba {i + 1}\nImporte total 1,234.56", fontsize=12)
    doc.embfile_add("relleno.bin", os.urandom(relleno_mb * 1024 * 1024))
    doc.save(path)
    return path


def test_upload_token_permite_subir_y_descargar(tmp_path):
    token = _token()
    with open(FIX, "rb") as f:
        r = _upload(token, f.read(), target="excel")
    assert r.status_code == 202, r.text
    status = _wait(r.json()["job_id"])
    assert status["status"] == "done", status
    dl = client.get(status["download_url"])
    assert dl.status_code == 200 and dl.content[:2] == b"PK"


def test_upload_token_sin_api_key_da_401():
    r = client.post("/api/v1/upload-token", json={})
    assert r.status_code == 401


def test_upload_sin_token_da_401():
    with open(FIX, "rb") as f:
        r = _upload(None, f.read())
    assert r.status_code == 401


def test_upload_token_caducado_da_401():
    token = jobs.create_upload_token(ttl_seconds=-10)
    with open(FIX, "rb") as f:
        r = _upload(token, f.read())
    assert r.status_code == 401
    assert "caduc" in r.json()["detail"]


def test_upload_token_reutilizado_da_401():
    token = _token()
    with open(FIX, "rb") as f:
        data = f.read()
    assert _upload(token, data).status_code == 202
    # El nonce ya se consumió al aceptar la primera subida.
    r = _upload(token, data)
    assert r.status_code == 401
    assert "ya fue usado" in r.json()["detail"]


def test_upload_token_manipulado_da_401():
    token = _token()
    raw, _, sig = token.partition(".")
    # Cambiar un carácter del payload.
    manipulado = ("A" if raw[0] != "A" else "B") + raw[1:] + "." + sig
    with open(FIX, "rb") as f:
        assert _upload(manipulado, f.read()).status_code == 401
    # Cambiar un carácter de la firma.
    manipulado = raw + "." + ("0" if sig[0] != "0" else "1") + sig[1:]
    with open(FIX, "rb") as f:
        assert _upload(manipulado, f.read()).status_code == 401


def test_upload_token_max_mb_menor_que_archivo_da_413(tmp_path):
    pdf = _pdf_grande(tmp_path / "mediano.pdf", relleno_mb=2)
    assert pdf.stat().st_size > 1 * 1024 * 1024
    token = jobs.create_upload_token(max_mb=1)
    r = _upload(token, pdf.read_bytes())
    assert r.status_code == 413
    # El rechazo no consume el nonce: el mismo token sigue valiendo para
    # un archivo que sí cabe (reintento tras corregir el archivo).
    with open(FIX, "rb") as f:
        assert _upload(token, f.read()).status_code == 202


def test_upload_directa_pdf_40mb_de_principio_a_fin(tmp_path):
    pdf = _pdf_grande(tmp_path / "grande.pdf", relleno_mb=40)
    assert pdf.stat().st_size >= 40 * 1024 * 1024
    token = _token()
    r = _upload(token, pdf.read_bytes(), target="excel")
    assert r.status_code == 202, r.text
    status = _wait(r.json()["job_id"])
    assert status["status"] == "done", status
    assert status["info"]["quality"]["text_coverage"] == 1.0
    dl = client.get(status["download_url"])
    assert dl.status_code == 200 and dl.content[:2] == b"PK"


def test_upload_token_sin_secreto_da_503(monkeypatch):
    monkeypatch.setattr(settings, "upload_secret", "")
    r = client.post("/api/v1/upload-token", headers=API_HEADERS, json={})
    assert r.status_code == 503
