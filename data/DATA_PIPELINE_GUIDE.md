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

> Pipeline hiện tại chỉ dùng thư viện chuẩn (`json`, `re`, `csv`, `pathlib`, `argparse`). Không cần Qdrant hay PostgreSQL client ở bước này.

### 1.2. Cấu trúc dữ liệu đầu vào (raw)

Repo đã có sẵn các nguồn raw tại `data/`:

```text
data/
├── raw/                                # text thô từ crawl (không dùng trực tiếp)
├── 01_thong_tin_san_pham/              # mô tả sản phẩm: vf2.md, vf3.md, vf5.md...
├── 02_thong_so_ky_thuat/
│   ├── model_specs.json                # specs + giá + khuyến mãi
│   └── vf*_brochure.md / vf*_specs.md  # brochure OCR
├── 04_ho_tro_mua_xe/                   # FAQ bán hàng, lái thử
├── 05_chinh_sach_dich_vu/              # điều khoản pháp lý, chính sách
├── 06_showroom_tram_sac/               # link showroom
├── 07_khuyen_mai_uu_dai/               # nội dung khuyến mãi (chỉ lấy link)
└── 08_dat_lich_bao_duong/              # link bảo dưỡng
```

### 1.3. Nguyên tắc phân loại dữ liệu

| Loại | Ví dụ | Lưu đâu | Lý do |
|------|-------|---------|-------|
| Thông số, mô tả, chính sách, FAQ, link bảo dưỡng | "VF 9 dài bao nhiêu?", "Có ADAS gì?" | Vector DB (Qdrant) | Ít đổi, cần hiểu ý user |
| Giá niêm yết + giá ưu đãi | "VF 9 Plus giá bao nhiêu?" | PostgreSQL | Thay đổi theo chiến dịch |
| Showroom, trạm sạc, khuyến mãi chiến dịch, chi phí lăn bánh | "Lăn bánh HN 2026?" | **Không lưu DB** — chỉ trả link nguồn | Phụ thuộc tỉnh/năm/đại lý, dễ lỗi thời |

---

## 2. Chạy pipeline

### 2.1. Lệnh chuẩn

Từ thư mục gốc repo (`D:\FULearning\vivu`):

```bash
# Bước 1: clean raw markdown + model_specs.json → intermediate JSONL
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
| `--target` | `1000` | Kích thước target chunk (chars) |
| `--hard` | `1500` | Kích thước tối đa chunk (chars) |

#### `scripts/clean_data/split_cold_hot.py`

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `--version` | `v1` | Phải khớp với bước 1 |
| `--commit` | `""` | Hash git ghi vào manifest |

### 2.3. Quy trình đề xuất khi có dữ liệu mới

1. Crawl/cập nhật file `.md` hoặc `model_specs.json` trong `data/01..08/`.
2. Chạy lại 2 lệnh trên với version mới (VD: `v2`).
3. So sánh `_manifest.json` của `v2` với `v1` để biết thay đổi.
4. Ingest `vector/*.jsonl` vào Qdrant, `postgres/*.csv` vào PostgreSQL theo diff. Xem thêm `scripts/ingest/`.

---

## 3. Kết quả output

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
│   ├── vivu_faq.jsonl
│   └── vivu_maintenance.jsonl
└── postgres/                           # → COPY INTO PostgreSQL
    ├── edition.csv
    ├── price_list.csv
    └── maintenance_schedule.csv
```

### 3.1. File `_manifest.json`

Ghi lại:

- `version`, `created_at`, `repo_commit`
- Số chunk mỗi vector collection (`added`/`modified`/`removed`)
- Số row Postgres (`upserted`)
- `link_only`: danh sách URL showroom / khuyến mãi / chi phí lăn bánh

Dùng để đối chiếu giữa các version và hỗ trợ incremental ingest.

### 3.2. Schema mỗi dòng vector JSONL

```json
{
  "id": "vivu_specs:vf9:eco:kich_thuoc:1",
  "collection": "vivu_specs",
  "vector_version": "v1",
  "model_id": "VF9",
  "edition_id": "Eco",
  "category": "thong_so_ky_thuat",
  "section_path": ["Thông số kỹ thuật", "KÍCH THƯỚC & TẢI TRỌNG"],
  "text": "VF 9 Eco — Dài × Rộng × Cao 5119 × 2254 × 1697 mm; ...",
  "text_type": "key_value",
  "structured": { "dimension": { "length_mm": 5119, ... } },
  "language": "vi",
  "tags": ["ky_thuat", "vf9", "kich_thuoc"],
  "confidence": 1.0,
  "source_file": "data/02_thong_so_ky_thuat/model_specs.json",
  "source_url": "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html",
  "source_type": "specs_json",
  "fetched_at": "...",
  "ingested_at": "...",
  "is_hot": false
}
```

> **Quan trọng**: `text` không bao giờ chứa số tiền (giá). Số tiền chỉ nằm trong `postgres/price_list.csv`.

### 3.3. Schema CSV PostgreSQL

#### `edition.csv`

```csv
model_id|edition_id|model_label|edition_label|year_range|is_active|created_at|updated_at
VF9|Eco|VF 9|Eco|2025-2026|t|2026-08-03T...|2026-08-03T...
```

#### `price_list.csv`

```csv
model_id|edition_id|price_list_vnd|price_promo_vnd|promo_label|vat_included|battery_included|valid_from|valid_to|updated_at|source_url
VF9|Eco|1348000000|||t|t|2026-07-01||2026-08-03T...|https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html
```

#### `maintenance_schedule.csv`

Hiện chỉ có header (chưa có dữ liệu chi tiết). Có thể bổ sung thủ công hoặc crawl từ `om.vinfastauto.com` sau.

---

## 4. Kiểm tra (smoke test)

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

## 5. Xử lý lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|--------|-------------|------------|
| `intermediate dir not found` | Chưa chạy `clean_to_jsonl.py` | Chạy bước 1 trước |
| Chunk bị drop vì "money detected" | Markdown còn đoạn giá tiền | Hợp lệ — giá phải nằm ở Postgres. Nếu drop nhầm, kiểm tra regex `has_money` trong `split_cold_hot.py` |
| Duplicate edition trong `price_list.csv` | 2 edition code cùng map về 1 edition_id | Cập nhật `EDITION_ID_MAP` trong `clean_to_jsonl.py` cho đúng |
| `source_file` dùng `\` thay vì `/` | Windows path | Pipeline đã chuẩn hóa thành `/` khi có thể. Nếu vẫn thấy `\`, dùng `.replace('\\', '/')` |

---

## 6. Ingest lên DB (bước tiếp theo)

Sau khi có `data/clean/<version>/`:

1. **Vector**: đọc từng dòng `vector/*.jsonl`, embed `text`, upsert vào Qdrant với `id`, `collection`, metadata đi kèm.
2. **Postgres**: `COPY edition.csv`, `price_list.csv` vào bảng tương ứng, hoặc dùng `INSERT ... ON CONFLICT UPDATE`.
3. **Link-only**: lấy từ `_manifest.json["link_only"]` để ghép vào prompt/response mà không cần query DB.

Xem chi tiết trong `scripts/ingest/README.md` và các script:

```bash
python scripts/ingest/vector_ingest.py --version v1
python scripts/ingest/postgres_ingest.py --version v1
```
