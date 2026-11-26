"""Prueba de carga con Locust: 200 usuarios concurrentes (ver README.md).

Simula usuarios reales: suben un PDF (1, 10 o 50 páginas), consultan el
estado hasta que termina y descargan el resultado.

CORRECCIÓN 26 nov 2026: antes, el fixture de "10 páginas" era
estado_cuenta_multipagina.pdf (3 páginas reales) y el de "50" era
estado_ingresos_octubre_2026.pdf (1 página real). Ahora los PDFs de 10 y
50 páginas se generan de verdad al arrancar Locust (ver _ensure_pdfs):
se repite la página de tests/fixtures/factura.pdf 10 y 50 veces con
PyMuPDF y se guardan en scripts/loadtest/generated/ (ignorado por git).
Son páginas con texto nativo (sin OCR), así que miden la conversión de
texto, no el OCR de escaneos.

Métrica E2E: además de los tiempos por endpoint que Locust ya reporta,
cada conversión completa (subida -> estado done -> descarga) registra un
evento propio "E2E / convert_e2e" con el tiempo total en ms, para leer el
p50/p95 de extremo a extremo en la salida y en el CSV.
"""
import random
import time
from pathlib import Path

import pymupdf
from locust import HttpUser, between, events, task

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent.parent / "tests" / "fixtures"
GENERATED = HERE / "generated"


def _repeat_pages(src: Path, n: int, dst: Path) -> Path:
    """Genera un PDF de n páginas repitiendo la página de `src`."""
    base = pymupdf.open(src)
    try:
        out = pymupdf.open()
        for _ in range(n):
            page = out.new_page(width=base[0].rect.width, height=base[0].rect.height)
            page.show_pdf_page(page.rect, base, 0)
        out.save(dst)
        return dst
    finally:
        base.close()


def _ensure_pdfs() -> dict[int, Path]:
    """PDFs reales de 1, 10 y 50 páginas (los de 10 y 50 se generan si faltan)."""
    GENERATED.mkdir(exist_ok=True)
    pdf_10 = GENERATED / "carga_10p.pdf"
    pdf_50 = GENERATED / "carga_50p.pdf"
    if not pdf_10.exists():
        _repeat_pages(FIXTURES / "factura.pdf", 10, pdf_10)
    if not pdf_50.exists():
        _repeat_pages(FIXTURES / "factura.pdf", 50, pdf_50)
    return {1: FIXTURES / "factura.pdf", 10: pdf_10, 50: pdf_50}


PDFS = _ensure_pdfs()
# Verificación en arranque: si el conteo no es el esperado, fallar alto
# en vez de medir con el PDF equivocado.
for _n, _p in PDFS.items():
    assert pymupdf.open(_p).page_count == _n, f"{_p} no tiene {_n} páginas"


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
        pdf = PDFS[pages]
        start = time.time()
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
        status = None
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
                return
        # Tiempo total de extremo a extremo (subida -> descarga lista).
        events.request.fire(
            request_type="E2E",
            name="convert_e2e",
            response_time=(time.time() - start) * 1000,
            response_length=0,
        )
