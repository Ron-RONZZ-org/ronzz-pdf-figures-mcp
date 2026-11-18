FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PDF_FIGURES_ALLOWED_ROOTS=/app/backend/data/uploads:/figures \
    PDF_FIGURES_OUTPUT_DIR=/figures \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-fra \
        tesseract-ocr-epo \
    && rm -rf /var/lib/apt/lists/*

# Normalise the tessdata path across Debian releases for PyMuPDF's OCR bridge.
RUN TESSDATA_DIR="$(find /usr/share/tesseract-ocr -type d -name tessdata | head -n 1)" \
    && ln -sfn "$TESSDATA_DIR" /usr/share/tessdata
ENV TESSDATA_PREFIX=/usr/share/tessdata

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --uid 100 --create-home app \
    && mkdir -p /figures \
    && chown app:app /figures
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"

CMD ["python", "-m", "pdf_figures.server"]
