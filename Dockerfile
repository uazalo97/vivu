# ── Production Dockerfile for Vivu Backend (FastAPI + Agentic RAG) ────────────
# Chi dong goi backend (app/), khong keo theo frontend / lib / docs / data.
FROM python:3.11-slim

# Thiet lap bien moi truong chuan cho Python container
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PORT=8000

WORKDIR /app

# Cai dat thu vien he thong can thiet
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy va cai dat dependencies Python (chi file requirements cua backend)
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Chi copy source backend (app/) de image nhe va khong chua frontend/docs...
COPY app ./app

# Sparse index (BM25) can cho hybrid retrieval - chi copy cac file runtime that su can
# (dung copy ca data_v2 379MB gom input ingest pipeline/scripts):
COPY data_v2/retrieval/sparse_index.json data_v2/retrieval/sparse_index.json
# Fallback sparse index tu pipeline cu:
COPY data/clean/v1/sparse_index.json data/clean/v1/sparse_index.json
COPY data/clean/v2/sparse_index.json data/clean/v2/sparse_index.json

# Expose port (Render se truyen bien $PORT)
EXPOSE 8000

# Khoi chay Uvicorn ho tro $PORT tu dong
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
