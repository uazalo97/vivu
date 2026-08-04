# Ingest Scripts — Local Qdrant + PostgreSQL (OpenRouter embed)

Thư mục này chứa script ingest dữ liệu clean vào database local.
**Embedding dùng OpenRouter API** (KHÔNG còn model local).

## Chuẩn bị

### 1. Cài thư viện

```bash
pip install -r requirements.txt
```

Các thư viện chính:

- `qdrant-client`: kết nối Qdrant
- `psycopg2-binary`: kết nối PostgreSQL
- `requests` + `python-dotenv`: gọi OpenRouter API (embed + rerank)

### 2. Setup OpenRouter API key

Tạo file `.env` ở repo root:

```bash
OPENROUTER_API_KEY=sk-or-v1-...          # lấy tại https://openrouter.ai/keys
OPENROUTER_EMBED_MODEL=openai/text-embedding-3-small
OPENROUTER_RERANK_MODEL=cohere/rerank-v3.5
```

> Mặc định: embed `openai/text-embedding-3-small` (1536-dim), rerank `cohere/rerank-v3.5`.
> Model ghi đè được qua biến môi trường.

### 3. Khởi động DB local (Docker)

```bash
docker compose up -d
```

- Qdrant: `http://localhost:6333`
- PostgreSQL: `postgresql://vivu:vivu@localhost:5432/vivu`

### 4. Chạy data pipeline trước

```bash
python scripts/clean_data/clean_to_jsonl.py --version v1
python scripts/clean_data/split_cold_hot.py --version v1 --commit $(git rev-parse --short HEAD)
```

## Ingest

### Vector (Qdrant) — dense, embed qua OpenRouter

```bash
python scripts/ingest/vector_ingest.py --version v1 --recreate
```

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `--version` | `v1` | Version dữ liệu clean |
| `--url` | `http://localhost:6333` | Qdrant URL |
| `--recreate` | `false` | Xóa và tạo lại collection |

Đặc điểm:

- Embed **`openai/text-embedding-3-small`** (1536-dim, auto-detect từ API probe).
- Batch 64 + **8 luồng song song** → 2333 chunks ≈ 20-30 giây.
- Upsert theo lô 100 points (tránh rớt connection với vector 1536-dim).
- Idempotent: collection đã đủ points → skip.

### Sparse (Qdrant) — BM25, không cần API

```bash
python scripts/ingest/sparse_ingest.py --version v1 --recreate
```

- Tạo collection `sparse` chứa BM25/TF-IDF vectors (tự build vocab từ text, không embed).
- Lưu `data/clean/v1/sparse_index.json` cho retriever encode query.

### PostgreSQL

```bash
python scripts/ingest/postgres_ingest.py --version v1
```

## Kiểm tra sau ingest

```bash
# Qdrant collections
curl http://localhost:6333/collections

# Postgres
docker exec -it vivu_postgres psql -U vivu -d vivu -c "SELECT * FROM price_list WHERE model_id = 'VF9';"
```

## Retriever

```bash
python backend/retriever/hybrid_retriever.py "VF 9 Plus giá bao nhiêu và có ADAS gì"
```

Retriever hybrid: **dense (bge/embed API) + sparse (BM25) → RRF → rerank (cohere/rerank-v3.5)**
→ filter model → join text → giá Postgres (tool `get_price`) → ghép prompt.

## Ghi chú

- `maintenance_schedule.csv` hiện chỉ có header (chưa có dữ liệu chi tiết).
- Không còn `sentence-transformers` — embedding 100% qua OpenRouter API.
- API key đọc từ `.env` qua `python-dotenv` (không commit).
