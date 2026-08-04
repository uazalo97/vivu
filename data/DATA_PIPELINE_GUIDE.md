# Hướng dẫn chạy Data Pipeline — UC-01 Product Information

> Mục tiêu: tạo ra bộ dữ liệu clean, versioned, sẵn sàng ingest vào **Vector DB (Qdrant)** và **PostgreSQL** để phục vụ use-case tra cứu thông tin xe.

---

## 1. Chuẩn bị

### 1.1. Yêu cầu

- Python ≥ 3.10
- Các thư viện trong `requirements.txt` đã cài:

```bash
pip install -r requirements.txt
```

> Pipeline clean (`clean_to_jsonl.py`, `split_cold_hot.py`) chỉ dùng thư viện chuẩn (`json`, `re`, `csv`, `pathlib`, `argparse`). Không cần Qdrant/Postgres client ở bước này.

### 1.1b. OpenRouter API key

Embedding + rerank chạy hoàn toàn qua **OpenRouter API** (không còn model local). Tạo `.env` ở repo root:

```bash
OPENROUTER_API_KEY=sk-or-v1-...                    # https://openrouter.ai/keys
OPENROUTER_EMBED_MODEL=openai/text-embedding-3-small   # 1536-dim
OPENROUTER_RERANK_MODEL=cohere/rerank-v3.5
```

Key đọc qua `python-dotenv` (`.env` đã gitignore).

### 1.2. Cấu trúc dữ liệu đầu vào (raw)

Nguồn duy nhất: **`data/raw/`** — output của crawler (`scripts/crawl.py`):

```text
data/raw/
├── vn_vi_*.txt                        # Trang chính thức VinFast (vinfastauto.com / shop.vinfastauto.com)
│   ├── dat-coc-*                      #   → giá (Postgres) + mô tả sản phẩm
│   ├── dich-vu-bao-duong-*            #   → bảo dưỡng
│   ├── dich-vu-pin / sua-chua / chinh-sach-bao-hanh / cuu-ho / ve-chung-toi
│   │                                  #   → chính sách
├── *_pdf_*.txt, brochure_*.txt        # PDF extract: sổ bảo hành / thông số
├── san-pham_*, product_*, vinfast-*   # Web article/dealer (review, so sánh, thông số)
├── so-sanh-*, bang-doi-chieu-*        # Trang so sánh → bảng specs
└── link_brochure.md                   # 8 URL brochure PDF (link-only, không embed)
```

Mỗi file crawl có header chuẩn:

```text
# Nguồn: https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html
# Crawl lúc: 2026-07-30T21:32:33
# Loại: html
# Selector: (toàn trang / N/A với PDF)
================================================================================
<body content>
```

### 1.3. Nguyên tắc phân loại dữ liệu

| Loại | Ví dụ | Lưu đâu | Lý do |
|------|-------|---------|-------|
| Thông số, mô tả, chính sách, bảo dưỡng | "VF 9 dài bao nhiêu?", "bảo hành pin?" | Vector DB (Qdrant) | Ít đổi, cần hiểu ý user |
| Giá niêm yết + giá ưu đãi | "VF 9 Plus giá bao nhiêu?" | PostgreSQL | Thay đổi theo chiến dịch |
| Brochure PDF | "Tải brochure VF 9" | **Không lưu DB** — chỉ trả link | File nặng, không embed text |

> **Quan trọng**: Giá chỉ được trích từ **trang chính thống VinFast** (`vinfastauto.com`, `shop.vinfastauto.com`) — page `dat-coc-*`. Không lấy giá từ web article/dealer.

---

## 2. Chạy pipeline

### 2.1. Lệnh chuẩn

Từ thư mục gốc repo (`D:\FULearning\vivu`):

```bash
# Bước 1: clean raw → intermediate JSONL
python scripts/clean_data/clean_to_jsonl.py --version v1

# Bước 2: tách cold (vector JSONL) + hot (Postgres CSV) + manifest
python scripts/clean_data/split_cold_hot.py --version v1 --commit $(git rev-parse --short HEAD)
```

> `--version v1` đánh dấu đợt thu thập. Khi có dữ liệu mới toàn bộ, tạo `v2`, `v3`...
> `--commit` ghi hash git vào `_manifest.json` để truy vết.

### 2.2. Tham số

#### `scripts/clean_data/clean_to_jsonl.py`

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `--version` | `v1` | Thư mục version output |
| `--max-len` | `400` | Kích thước tối đa chunk (chars) — khớp cửa sổ embedding ~128 token |

#### `scripts/clean_data/split_cold_hot.py`

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `--version` | `v1` | Phải khớp với bước 1 |
| `--commit` | `""` | Hash git ghi vào manifest |

### 2.3. Quy trình đề xuất khi có dữ liệu mới

1. Crawl/cập nhật file trong `data/raw/` bằng `scripts/crawl.py <URL>`.
2. Chạy lại 2 lệnh trên với version mới (VD: `v2`).
3. So sánh `_manifest.json` của `v2` với `v1` để biết thay đổi.
4. Ingest `vector/*.jsonl` vào Qdrant, `postgres/*.csv` vào PostgreSQL theo diff. Xem thêm `scripts/ingest/`.

---

## 3. Chunking

### 3.1. Nguyên tắc 2 tầng

1. **Chunk theo heading** (`#`, `##`, `###`) → 1 section = 1 chunk ban đầu.
2. **Cắt theo câu** khi chunk > `max_len` (400):
   - Gom câu tới khi vượt 400 → cắt ở **biên câu** (sau `. `, `! `, `? `, xuống dòng).
   - Specs key:value không có dấu câu → cắt ở `; `.
   - **Overlap** = câu cuối hoàn chỉnh của chunk trước làm mở đầu chunk sau.
   - Bảng markdown → lặp lại header row ở mỗi mảnh.

### 3.2. Tại sao `max_len = 400`

`max_len=400` được chốt từ bản đầu (khớp cửa sổ MiniLM cũ ~128 token ≈ 400 chars tiếng Việt).
**Model hiện tại `openai/text-embedding-3-small` có window 8191 token** (rộng hơn nhiều) — vì vậy có thể
tăng `--max-len` lên 1000-2000 để ít chunk hơn, mỗi chunk mang nhiều ngữ nghĩa hơn. Muốn đổi:
chạy lại `clean_to_jsonl.py --max-len <n>` rồi re-ingest (xem §7).

---

## 4. Kết quả output

Sau khi chạy xong, output nằm tại:

```text
data/clean/<version>/
├── _manifest.json                      # index + tracking toàn bộ version
├── intermediate/                       # file trung gian (optional, có thể xóa sau split)
│   ├── vector.jsonl
│   ├── hot.jsonl
│   └── link_only.json
├── vector/                             # → ingest Qdrant
│   ├── vivu_specs.jsonl
│   ├── vivu_product_info.jsonl
│   ├── vivu_policy.jsonl
│   └── vivu_maintenance.jsonl
└── postgres/                           # → COPY INTO PostgreSQL
    ├── edition.csv
    ├── price_list.csv
    └── maintenance_schedule.csv
```

> Không còn collection `vivu_faq` — nguồn raw không có dữ liệu FAQ. `split_cold_hot.py` tự dọn file collection cũ khi chạy lại.

### 4.1. File `_manifest.json`

Ghi lại:

- `version`, `created_at`, `repo_commit`
- Số chunk mỗi vector collection (`added`/`modified`/`removed`)
- Số row Postgres (`upserted`)
- `link_only`: danh sách URL brochure

### 4.2. Schema mỗi dòng vector JSONL

```json
{
  "id": "vivu_specs:vf9:all:thong_so_ky_thuat:1",
  "collection": "vivu_specs",
  "vector_version": "v1",
  "model_id": "VF9",
  "edition_id": null,
  "category": "thong_so_ky_thuat",
  "section_path": ["thong_so_ky_thuat", "Hiệu suất và động cơ"],
  "text": "VF8 Eco tiết kiệm năng lượng hơn nhưng có hiệu suất vận hành thấp hơn. VF8 Plus có công suất...",
  "text_type": "prose",
  "structured": {},
  "language": "vi",
  "tags": ["thong_soky_thuat", "vf9"],
  "confidence": 0.8,
  "source_file": "data/raw/so-sanh-vf8-eco-va-vf8-plus-p56_....txt",
  "source_url": "https://www.vinfastmiennam.vn/so-sanh-vf8-eco-va-vf8-plus-p56",
  "source_type": "raw_html",
  "fetched_at": "2026-07-30T22:56:26",
  "ingested_at": "...",
  "is_hot": false
}
```

> **Quan trọng**: `text` không bao giờ chứa số tiền (giá). Số tiền chỉ nằm trong `postgres/price_list.csv`.

### 4.3. Schema CSV PostgreSQL

#### `edition.csv`

```csv
model_id|edition_id|model_label|edition_label|year_range|is_active|created_at|updated_at
VF9|Plus|VF 9|Plus|2026|t|2026-08-03T...|2026-08-03T...
```

#### `price_list.csv`

```csv
model_id|edition_id|price_list_vnd|price_promo_vnd|promo_label|vat_included|battery_included|valid_from|valid_to|updated_at|source_url
VF9|Plus|1529000000|1452550000|Ưu đãi đặt cọc 2026|t|t|2026-07-01||2026-08-03T...|https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html
```

---

## 5. Kiểm tra (smoke test)

Sau khi chạy, nên kiểm tra:

```bash
# 1. Số lượng chunk trong từng collection
wc -l data/clean/v1/vector/*.jsonl

# 2. Manifest hợp lệ
python -m json.tool data/clean/v1/_manifest.json

# 3. Vector text không chứa số tiền (price leak)
python -c "
import json, re
from pathlib import Path
pat = re.compile(r'(?:\d{1,3}(?:[.,]\d{3})+|\d{6,})\s*(?:triệu|tr|tỷ|nghìn|đồng|VNĐ|VND|\bđ\b)|(?:triệu|tr|tỷ|nghìn|đồng|VNĐ|VND|\bđ\b)\s*(?:\d{1,3}(?:[.,]\d{3})+|\d+)', flags=re.I)
for f in Path('data/clean/v1/vector').glob('*.jsonl'):
    for line in open(f, encoding='utf-8'):
        o = json.loads(line)
        if pat.search(o['text']):
            print('LEAK:', f.name, o['id'])
"
```

---

## 6. Xử lý lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|--------|-------------|------------|
| `intermediate dir not found` | Chưa chạy `clean_to_jsonl.py` | Chạy bước 1 trước |
| Chunk bị drop vì "money detected" | Raw còn đoạn giá tiền chưa bị strip | Hợp lệ — giá phải nằm ở Postgres. Kiểm tra `strip_price_spans` nếu drop nhầm |
| Thiếu edition trong `price_list.csv` | Dat-coc page không in rõ edition | `MODEL_EDITIONS` trong `clean_to_jsonl.py` gán theo thứ tự giá |
| Giá từ dealer page lọt vào Postgres | Sai `AUTHORITATIVE_DOMAINS` | Chỉ `vinfastauto.com` / `shop.vinfastauto.com` mới trích giá |
| PDF text bị cách chữ "T h ô n g" | `pdftotext` extract | `fix_pdf_spacing` xử lý theo dòng (chỉ dòng >50% token 1 ký tự) |

---

## 7. Ingest lên DB

Sau khi có `data/clean/<version>/`:

```bash
# 1. Vector dense — embed qua OpenRouter (openai/text-embedding-3-small, 1536-dim)
python scripts/ingest/vector_ingest.py --version v1 --recreate

# 2. Sparse BM25 (không cần API)
python scripts/ingest/sparse_ingest.py --version v1 --recreate

# 3. Postgres
python scripts/ingest/postgres_ingest.py --version v1
```

Đặc điểm:

- **Vector**: embed batch 64 + 8 luồng song song (~20-30s cho 2333 chunks), upsert lô 100.
- **Sparse**: tạo collection `sparse` (BM25/TF-IDF tự build vocab), lưu `sparse_index.json` cho retriever.
- **Postgres**: `COPY edition.csv`, `price_list.csv` (hoặc `INSERT ... ON CONFLICT UPDATE`).
- **Link-only**: `_manifest.json["link_only"]` (brochure URLs) — ghép vào prompt không cần query DB.

## 8. Retriever (hybrid search)

```bash
python backend/retriever/hybrid_retriever.py "VF 9 Plus giá bao nhiêu và có ADAS gì"
```

Luồng: **dense (OpenRouter embed) + sparse (BM25) → RRF fusion → rerank (cohere/rerank-v3.5)**
→ filter model/edition → join text từ `vector/*.jsonl` → giá Postgres (tool `get_price`) → ghép prompt LLM + brochure link.

Chi tiết: `backend/retriever/README.md`, `scripts/ingest/README.md`.
