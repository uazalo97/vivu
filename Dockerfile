# ── Production Dockerfile for Vivu Backend (FastAPI + Agentic RAG) ────────────
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

# Copy va cai dat dependencies Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy toan bo source code
COPY . .

# Expose port (Render se truyen bien $PORT)
EXPOSE 8000

# Khoi chay Uvicorn ho tro $PORT tu dong
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
