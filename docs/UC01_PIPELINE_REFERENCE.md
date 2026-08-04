# Tài liệu tham khảo — Luồng triển khai UC-01 Product Information

> Mục tiêu: có 1 luồng data ổn định từ raw → clean → ingest → sẵn sàng cho retrieval.

---

## Slide 1 — Pipeline đề xuất xử lý như thế nào?

### Luồng tổng quan

```text
RAW DATA
    └── data/raw/*.txt (crawl output: html/pdf)
        └── link_brochure.md (brochure URLs)
           │
           ▼
    ┌─────────────────────────────┐
    │  scripts/clean_data/        │
    │  clean_to_jsonl.py          │
    │  • Parse header + classify  │
    │  • Clean HTML/PDF noise     │
    │  • Tách giá dat-coc → hot   │
    │  • Emit intermediate JSONL  │
    └─────────────────────────────┘
           │
           ▼
    ┌─────────────────────────────┐
    │  scripts/clean_data/        │
    │  split_cold_hot.py          │
    │  • Cold → vector/*.jsonl    │
    │  • Hot  → postgres/*.csv    │
    │  • Link-only → manifest     │
    └─────────────────────────────┘
           │
           ▼
    ┌─────────────────────────────┐
    │  scripts/ingest/            │
    │  vector_ingest.py           │  embed qua OpenRouter
    │  sparse_ingest.py           │  (openai/text-embedding-3-small)
    │  postgres_ingest.py         │  + BM25 sparse + Postgres
    └─────────────────────────────┘
           │
           ▼
    ┌─────────────────────────────┐
    │  backend/retriever/         │
    │  hybrid_retriever.py        │
    │  • Dense + Sparse + RRF     │
    │  • Rerank (cohere/rerank)   │
    │  • Tool get_price (Postgres)│
    │  • Ghép prompt → trả lời    │
    └─────────────────────────────┘
```

### Nguyên tắc cốt lõi

| Quyết định | Lý do |
|---|---|
| Tách 2 DB (Vector + Postgres) | Giá hay đổi, không nên re-embed liên tục |
| Vector text không chứa số tiền | Tránh trả giá cũ, giá lỗi thời |
| Brochure PDF chỉ trả link | File nặng, không embed text |
| Version `v1`, `v2`... | Rollback dễ, so sánh đợt thu thập |
| `model_id` + `edition_id` làm khóa join | Chuẩn hóa giữa 2 DB |

---

## Slide 2 — Những task nào cần thực hiện?

### Phần A — Clean Data

| # | Task | Mô tả | Trạng thái |
|---|------|-------|-----------|
| A1 | Chuẩn hóa `model_id` / `edition_id` | Infer từ tên file raw; edition theo thứ tự giá | ✅ Done |
| A2 | Clean raw crawl | Parse header, bỏ HTML/PUA/nav noise, dedupe, de-space PDF | ✅ Done |
| A3 | Trích giá dat-coc (chính thống) | `vinfastauto.com/shop` → hot rows; không lấy từ dealer | ✅ Done |
| A4 | Chunk hóa dữ liệu | Theo heading → cắt theo câu, max_len 400, overlap câu cuối | ✅ Done |
| A5 | Split cold / hot | Emit `vector/*.jsonl` + `postgres/*.csv` | ✅ Done |
| A6 | Tạo `_manifest.json` | Index version, tracking thay đổi | ✅ Done |

### Phần B — Ingest Local

| # | Task | Mô tả | Trạng thái |
|---|------|-------|-----------|
| B1 | Docker Compose Qdrant + Postgres | `docker-compose.yml` chạy local | ✅ Done |
| B2 | Vector ingest | Embed qua **OpenRouter** (`openai/text-embedding-3-small`, 1536-dim) → Qdrant | ✅ Done |
| B3 | Sparse ingest | BM25/TF-IDF → collection `sparse` (không cần API) | ✅ Done |
| B4 | Postgres ingest | Tạo bảng, upsert `edition`, `price_list` | ✅ Done |
| B5 | Tracking `ingest_version` | Ghi metadata vào Postgres | ✅ Done |

### Phần C — Retrieval (tiếp theo)

| # | Task | Mô tả | Trạng thái |
|---|------|-------|-----------|
| C1 | Hybrid retriever | Dense + Sparse + RRF + **rerank** (`backend/retriever/hybrid_retriever.py`) | ✅ Done |
| C2 | Entity extractor | Regex detect `model_id` + `edition_id` từ query | ✅ Done |
| C3 | Tool `get_price` | Postgres JOIN qua `TOOL_REGISTRY` (deterministic fast-path, sẵn sàng tool-call) | ✅ Done |
| C4 | Context builder | Ghép chunk + giá + brochure → prompt LLM | ✅ Done |
| C5 | LLM response | `--answer` gọi OpenRouter chat (`deepseek/deepseek-v4-flash-0731`) sinh câu trả lời | ✅ Done |

### Phần D — Vận hành & Kiểm thử

| # | Task | Mô tả | Trạng thái |
|---|------|-------|-----------|
| D1 | Smoke test pipeline | Chạy end-to-end, kiểm tra output | ✅ Done |
| D2 | Validate no price leak | Kiểm tra vector text không có số tiền | ✅ Done |
| D3 | Unit tests | Test clean + ingest functions | ⏳ Todo |
| D4 | Update flow khi VinFast đổi giá | Chỉ UPDATE Postgres, không re-embed | ⏳ Todo |

---

## Slide 3 — Kết quả mong đợi

Sau khi hoàn thành pipeline:

- User hỏi "VF 9 Plus giá bao nhiêu" → retriever tìm specs VF 9 Plus → Postgres lấy giá hiện hành → LLM trả lời đúng giá.
- User hỏi "VF 9 có màu gì" → vector search trả về chunk màu sắc, không cần Postgres.
- User hỏi "Lăn bánh HN 2026" → chatbot trả link nguồn, không nhập số liệu.

---

## Slide 4 — Câu lệnh chạy nhanh

```bash
# 1. Clean data
python scripts/clean_data/clean_to_jsonl.py --version v1
python scripts/clean_data/split_cold_hot.py --version v1

# 2. Start local DB
docker compose up -d

# 3. Ingest
python scripts/ingest/vector_ingest.py --version v1 --recreate
python scripts/ingest/postgres_ingest.py --version v1
```

---

## Tham khảo

- `docs/UC01_PRODUCT_INFORMATION.md` — kiến trúc chi tiết.
- `data/DATA_PIPELINE_GUIDE.md` — hướng dẫn chạy pipeline.
- `scripts/ingest/README.md` — hướng dẫn ingest.
