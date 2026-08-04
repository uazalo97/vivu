# vivu — Chatbot tư vấn xe VinFast (RAG)

Chatbot AI tra cứu thông tin xe VinFast: giá, thông số kỹ thuật, chính sách bảo hành, bảo dưỡng, brochure.
Kiến trúc RAG với **hybrid search** (dense + BM25 + rerank), embedding/rerank/LLM chạy hoàn toàn qua **OpenRouter API**.

---

## Kiến trúc

```
data/raw/ (49 file crawl)
   │
   ▼
scripts/clean_data/  →  clean + chunk (heading → câu, max_len=400)
   ▼
scripts/ingest/      →  vector_ingest (embed OpenRouter) + sparse_ingest (BM25) + postgres_ingest
   ▼
Qdrant (4 dense + 1 sparse collection)   PostgreSQL (giá)
   ▼
backend/main.py (FastAPI + SSE) ←── proxy /api ──→  frontend (Vite + React)
```

Luồng câu trả lời: **entity detect → dense + sparse search → RRF → rerank → giá Postgres (tool) → LLM sinh câu trả lời (stream)**

---

## Cấu trúc thư mục

```
backend/                    ← Backend FastAPI + retriever
├── main.py                 FastAPI: POST /api/chat/stream (SSE), /api/suggestions, /api/health
├── lib/openrouter.py       OpenRouter helper: embed, rerank, chat stream (đọc .env)
└── retriever/
    ├── hybrid_retriever.py Module retrieve() + CLI
    └── README.md

scripts/
├── crawl.py                Crawler (tạo file trong data/raw/)
├── clean_data/             clean_to_jsonl.py + split_cold_hot.py
└── ingest/                 vector_ingest.py, sparse_ingest.py, postgres_ingest.py

frontend/                   Giao diện React + Tailwind (Vite), proxy /api → localhost:8000
data/                       raw/, clean/, tài liệu pipeline
docs/                       Tài liệu UC-01
```

---

## Yêu cầu

| Thành phần | Phiên bản |
|---|---|
| Python | ≥ 3.10 |
| Docker + Docker Compose | Qdrant + PostgreSQL |
| Node.js | ≥ 18 (cho frontend) |
| OpenRouter API key | lấy tại https://openrouter.ai/keys |

---

## Setup

### 1. Cài Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Khởi động DB local (Docker)

```bash
docker compose up -d
```

- Qdrant: `http://localhost:6333`
- PostgreSQL: `postgresql://vivu:vivu@localhost:5432/vivu`

### 3. Cấu hình OpenRouter (.env)

Tạo file `.env` ở repo root:

```bash
OPENROUTER_API_KEY=sk-or-v1-...                      # https://openrouter.ai/keys
OPENROUTER_EMBED_MODEL=openai/text-embedding-3-small # 1536-dim
OPENROUTER_RERANK_MODEL=cohere/rerank-v3.5
OPENROUTER_CHAT_MODEL=deepseek/deepseek-v4-flash-0731
```

> `.env` đã gitignore. Model có thể đổi tùy ý (được đọc qua `python-dotenv`).

### 4. Cài frontend

```bash
cd frontend
npm install
cd ..
```

---

## Chạy data pipeline

Từ repo root. Chạy theo thứ tự:

```bash
# 1. Clean raw → intermediate JSONL (chunk theo heading + câu, max_len=400)
python scripts/clean_data/clean_to_jsonl.py --version v1

# 2. Tách cold (vector) + hot (Postgres) + manifest
python scripts/clean_data/split_cold_hot.py --version v1 --commit $(git rev-parse --short HEAD)

# 3. Ingest (bắt buộc chạy đủ 3):
python scripts/ingest/vector_ingest.py --version v1 --recreate   # dense, embed OpenRouter
python scripts/ingest/sparse_ingest.py --version v1 --recreate   # sparse BM25
python scripts/ingest/postgres_ingest.py --version v1            # giá
```

> Lần đầu embed sẽ gọi OpenRouter API cho ~2333 chunks (batch 64, 8 luồng — ~20-30s).
> Ingest có tính idempotent: collection đã đủ points sẽ skip.

---

## Chạy backend

```bash
python -m uvicorn backend.main:app --port 8000 --reload
```

Kiểm tra: `curl http://localhost:8000/api/health`

```
{"status":"ok","qdrant":"up","postgres":"up","llm":"ok"}
```

---

## Chạy frontend

```bash
cd frontend
npm run dev
```

Mở **http://localhost:5173** — chat thử: *"VF 9 Plus giá bao nhiêu và có ADAS gì"*.

Frontend hiển thị:
- Các **bước pipeline** (Phân tích câu hỏi → Tìm tài liệu → Sắp xếp → Tra giá → Tổng hợp)
- Câu trả lời **stream realtime** (SSE)
- **Nguồn tham khảo** (chunks + giá Postgres + brochure)
- **Metrics** (latency, tokens, TTFT)

---

## Retriever CLI

```bash
# Hybrid đầy đủ (dense + sparse + RRF + rerank)
python backend/retriever/hybrid_retriever.py "VF 9 Plus giá bao nhiêu và có ADAS gì"

# Sinh câu trả lời bằng LLM
python backend/retriever/hybrid_retriever.py "bảo hành pin xe điện mấy năm" --answer

# Tùy chọn
python backend/retriever/hybrid_retriever.py "trễ hạn phí thuê pin" --no-rerank  # bỏ rerank
python backend/retriever/hybrid_retriever.py "bảo hành pin" --no-sparse          # chỉ dense
python backend/retriever/hybrid_retriever.py "trễ hạn phí" --no-dense           # chỉ sparse
```

Kết quả in ra: top-k chunks + giá Postgres + brochure + **TIMING & TOKENS** (latency từng bước, TTFT, token usage).

---

## Test nhanh

```bash
# 1. Health backend
curl http://localhost:8000/api/health

# 2. SSE stream
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"VF 9 Plus giá bao nhiêu"}'

# 3. Verify DB
curl http://localhost:6333/collections
docker exec vivu_postgres psql -U vivu -d vivu -c "SELECT * FROM price_list;"
```

---

## Tài liệu tham khảo

- `data/DATA_PIPELINE_GUIDE.md` — chạy data pipeline chi tiết.
- `docs/UC01_PRODUCT_INFORMATION.md` — kiến trúc use-case.
- `docs/UC01_CLEAN_FORMAT_CHUNKING_RETRIEVER_LLM.md` — clean/chunk/retriever/LLM.
- `docs/UC01_PIPELINE_REFERENCE.md` — luồng triển khai + trạng thái task.
- `backend/retriever/README.md` — retriever hybrid.
- `scripts/ingest/README.md` — ingest.
