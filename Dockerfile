FROM python:3.12-slim
# Multi-arquitectura: python:3.12-slim existe para linux/amd64 y
# linux/arm64, y las dependencias con código nativo fijadas en
# requirements.txt publican ruedas manylinux_aarch64 en PyPI (verificado
# el 26 nov 2026 contra la API de PyPI para las versiones exactas fijadas):
#   pymupdf==2.2 -> pymupdf-2.2-cp311-abi3-manylinux_2_28_aarch64.whl
#   numpy==2.5.3 -> numpy-2.5.3-cp312-cp312-manylinux_2_27_aarch64...whl
#   pillow==12.3.0 -> pillow-12.3.0-cp312-cp312-manylinux_2_27_aarch64...whl
#   opencv-python-headless (dependencia de pdf2docx) -> rueda abi3 aarch64
# Por tanto el mismo Dockerfile construye en ARM64 sin compilar nada desde
# el código fuente. Los paquetes apt (tesseract-ocr, ocrmypdf, fuentes)
# también existen para arm64 en Debian bookworm. La CI lo comprueba con
# un trabajo docker-build-arm64 (buildx + QEMU); no se pudo construir aquí
# porque esta VM no tiene Docker.

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng ocrmypdf \
        fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN useradd -m appuser && mkdir -p /data/jobs && chown -R appuser /data
USER appuser
ENV PYTHONUNBUFFERED=1 STORAGE_DIR=/data/jobs
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
