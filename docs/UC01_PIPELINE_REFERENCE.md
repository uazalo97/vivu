# Tài liệu tham khảo — Luồng triển khai UC-01 Product Information

> Mục tiêu: có 1 luồng data ổn định từ raw → clean → ingest → sẵn sàng cho retrieval.

---

## Slide 1 — Pipeline đề xuất xử lý như thế nào?

### Luồng tổng quan

```text
RAW DATA
    ├── Markdown files (01..08)
    └── model_specs.json
           │
           ▼
    ┌─────────────────────────────┐
    │  scripts/clean_data/        │
    │  clean_to_jsonl.py          │
    │  • Clean ảnh, noise, OCR    │
    │  • Tách giá ra khỏi text    │
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
    │  vector_ingest.py           │
    │  postgres_ingest.py         │
    │  • Embed + upsert Qdrant    │
    │  • COPY/UPSERT PostgreSQL   │
    └─────────────────────────────┘
           │
           ▼
    ┌─────────────────────────────┐
    │  RETRIEVER + LLM            │
    │  • Vector search lấy model  │
    │  • Postgres JOIN lấy giá    │
    │  • Ghép prompt → trả lời    │
    └─────────────────────────────┘
```

### Nguyên tắc cốt lõi

| Quyết định | Lý do |
|---|---|
| Tách 2 DB (Vector + Postgres) | Giá hay đổi, không nên re-embed liên tục |
| Vector text không chứa số tiền | Tránh trả giá cũ, giá lỗi thời |
| Showroom / khuyến mãi / lăn bánh chỉ trả link | Dữ liệu địa phương, thay đổi liên tục |
| Version `v1`, `v2`... | Rollback dễ, so sánh đợt thu thập |
| `model_id` + `edition_id` làm khóa join | Chuẩn hóa giữa 2 DB |

---

## Slide 2 — Những task nào cần thực hiện?

### Phần A — Clean Data

| # | Task | Mô tả | Trạng thái |
|---|------|-------|-----------|
| A1 | Chuẩn hóa `model_id` / `edition_id` | Map `Products-Car-VF9` → `VF9`, `NE3LV` → `Eco` | ✅ Done |
| A2 | Clean markdown | Bỏ ảnh, noise, ghi chú nội bộ, giá tiền trong text | ✅ Done |
| A3 | Parse `model_specs.json` | Tách specs → vector, price → hot rows | ✅ Done |
| A4 | Chunk hóa dữ liệu | Theo section heading, target 1000 chars, hard 1500 | ✅ Done |
| A5 | Split cold / hot | Emit `vector/*.jsonl` + `postgres/*.csv` | ✅ Done |
| A6 | Tạo `_manifest.json` | Index version, tracking thay đổi | ✅ Done |

### Phần B — Ingest Local

| # | Task | Mô tả | Trạng thái |
|---|------|-------|-----------|
| B1 | Docker Compose Qdrant + Postgres | `docker-compose.yml` chạy local | ✅ Done |
| B2 | Vector ingest | Embed text + upsert vào Qdrant collection | ✅ Done |
| B3 | Postgres ingest | Tạo bảng, upsert `edition`, `price_list` | ✅ Done |
| B4 | Tracking `ingest_version` | Ghi metadata vào Postgres | ✅ Done |

### Phần C — Retrieval (tiếp theo)

| # | Task | Mô tả | Trạng thái |
|---|------|-------|-----------|
| C1 | Vector retriever | Tìm chunk specs/product theo câu hỏi user | ⏳ Todo |
| C2 | Entity extractor | Nhận diện `model_id` + `edition_id` từ query | ⏳ Todo |
| C3 | Postgres JOIN | Lấy giá + chính sách theo khóa | ⏳ Todo |
| C4 | Prompt builder | Ghép context + giá + link-only → prompt LLM | ⏳ Todo |
| C5 | Response formatter | Trả lời tiếng Việt, không bịa số liệu | ⏳ Todo |

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
