import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

FIX = Path(__file__).parent / "fixtures" / "estado_ingresos_octubre_2026.pdf"
client = TestClient(app)


def _wait(job_id):
    for _ in range(120):
        r = client.get(f"/api/v1/jobs/{job_id}").json()
        if r["status"] in ("done", "error"):
            return r
        time.sleep(0.5)
    raise AssertionError("timeout")


def test_full_flow_excel():
    with open(FIX, "rb") as f:
        r = client.post("/api/v1/convert", files={"file": ("estado.pdf", f, "application/pdf")}, data={"target": "excel"})
    assert r.status_code == 202
    status = _wait(r.json()["job_id"])
    assert status["status"] == "done", status
    dl = client.get(status["download_url"])
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    assert "estado.xlsx" in dl.headers["content-disposition"]


def test_rejects_non_pdf():
    r = client.post("/api/v1/convert", files={"file": ("a.pdf", b"no soy pdf", "application/pdf")}, data={"target": "word"})
    assert r.status_code == 400


def test_rejects_bad_target():
    r = client.post("/api/v1/convert", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}, data={"target": "zip"})
    assert r.status_code == 400


def test_unknown_job():
    assert client.get("/api/v1/jobs/abc123").status_code == 404


def test_progress_endpoint():
    with open(FIX, "rb") as f:
        r = client.post("/api/v1/convert", files={"file": ("estado.pdf", f, "application/pdf")}, data={"target": "excel"})
    job_id = r.json()["job_id"]
    status = _wait(job_id)
    assert status["status"] == "done"
    p = client.get(f"/api/v1/jobs/{job_id}/progress").json()
    assert p["pages_done"] == p["pages_total"] == 1
    assert p["progress"] == 1.0


def test_cancel_unknown_job():
    assert client.post("/api/v1/jobs/abc123/cancel").status_code == 404


def test_cancel_done_job_conflict():
    with open(FIX, "rb") as f:
        r = client.post("/api/v1/convert", files={"file": ("estado.pdf", f, "application/pdf")}, data={"target": "excel"})
    job_id = r.json()["job_id"]
    _wait(job_id)
    assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 409


def test_convert_many():
    with open(FIX, "rb") as f:
        data = f.read()
    files = [("files", ("a.pdf", data, "application/pdf")), ("files", ("b.pdf", data, "application/pdf"))]
    r = client.post("/api/v1/convert-many", files=files, data={"target": "word"})
    assert r.status_code == 202
    assert len(r.json()["jobs"]) == 2
    for job in r.json()["jobs"]:
        assert _wait(job["job_id"])["status"] == "done"


def test_convert_continuous_layout():
    with open(FIX, "rb") as f:
        r = client.post("/api/v1/convert", files={"file": ("estado.pdf", f, "application/pdf")},
                        data={"target": "excel", "layout": "continuous"})
    assert r.status_code == 202
    assert _wait(r.json()["job_id"])["status"] == "done"


def test_health_and_metrics():
    h = client.get("/health").json()
    assert h["ok"] is True and "disco_libre_mb" in h
    m = client.get("/metrics")
    assert m.status_code == 200
    assert "converter_jobs_total" in m.text
    assert "converter_disk_free_bytes" in m.text


def test_signed_download(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "download_secret", "secreto-de-prueba")
    with open(FIX, "rb") as f:
        r = client.post("/api/v1/convert", files={"file": ("estado.pdf", f, "application/pdf")}, data={"target": "excel"})
    job_id = r.json()["job_id"]
    status = _wait(job_id)
    assert status["status"] == "done"
    url = status["download_url"]
    assert "token=" in url
    # Sin token no se puede descargar cuando hay secreto configurado.
    assert client.get(f"/api/v1/jobs/{job_id}/download").status_code == 401
    # Con el enlace firmado sí.
    assert client.get(url).status_code == 200
