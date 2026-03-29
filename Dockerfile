# ── Stage 1: Build ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps for PyMuPDF
RUN apt-get update && \
    apt-get install -y --no-install-recommends libmupdf-dev && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY pipeline/ pipeline/
COPY search/ search/
COPY web/ web/

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080"]
