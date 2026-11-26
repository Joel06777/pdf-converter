"""Prueba de carga con Locust: 200 usuarios concurrentes (ver README.md).

Simula usuarios reales: suben un PDF (1, 10 o 50 páginas), consultan el
estado hasta que termina y descargan el resultado.
"""
import random
from pathlib import Path

from locust import HttpUser, between, task

FIXTURES = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
PDFS = {
    1: FIXTURES / "factura.pdf",
    10: FIXTURES / "estado_cuenta_multipagina.pdf",  # 3 págs.; se reutiliza
    50: FIXTURES / "estado_ingresos_octubre_2026.pdf",
}


def _pdf_for(pages: int) -> Path:
    return PDFS[1] if pages == 1 else PDFS[10] if pages == 10 else PDFS[50]


class ConverterUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def convert_small(self):
        self._convert(1)

    @task(2)
    def convert_medium(self):
        self._convert(10)

    @task(1)
    def convert_large(self):
        self._convert(50)

    def _convert(self, pages: int):
        pdf = _pdf_for(pages)
        with self.client.post(
            "/api/v1/convert",
            files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")},
            data={"target": random.choice(["excel", "word", "pptx"])},
            catch_response=True,
        ) as resp:
            if resp.status_code != 202:
                resp.failure(f"convert devolvió {resp.status_code}")
                return
            job_id = resp.json()["job_id"]
        # Consulta el estado hasta que termine (máx. 10 min).
        for _ in range(600):
            with self.client.get(f"/api/v1/jobs/{job_id}", catch_response=True) as resp:
                if resp.status_code != 200:
                    resp.failure(f"estado devolvió {resp.status_code}")
                    return
                status = resp.json()["status"]
            if status in ("done", "error", "cancelled"):
                break
            self.wait()
        if status != "done":
            return
        with self.client.get(f"/api/v1/jobs/{job_id}/download", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"descarga devolvió {resp.status_code}")
