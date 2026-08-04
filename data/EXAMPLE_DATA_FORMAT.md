# Example Data Format — Kiến trúc 2 DB cho RAG (Vector + PostgreSQL)

> ⚠️ **DEPRECATED** — file mẫu review dựa trên layout dữ liệu cũ (`data/01..08/`, `model_specs.json`, `target=1000/hard=1500`, collection `vivu_faq`).
> Pipeline hiện tại đã chuyển sang nguồn **`data/raw/`** với chunking **`max_len=400`** (xem `docs/UC01_CLEAN_FORMAT_CHUNKING_RETRIEVER_LLM.md` + `data/DATA_PIPELINE_GUIDE.md`).
> **Schema JSONL / CSV dưới đây vẫn dùng làm chuẩn format output** — chỉ các ví dụ `source_file`/collection/tham số chunking là cũ.

---


## Trước khi đọc chi tiết — Tại sao lại chia 2 DB?

### 1. Chatbot cần 2 loại kiến thức khác nhau

| Loại kiến thức | Ví dụ câu hỏi | Đặc điểm | Cách lưu trữ |
|---|---|---|---|
| **Kiến thức "cứng"** | "VF 9 dài bao nhiêu mét? Có ADAS gì?" | Ít thay đổi, trả lời theo ngữ cảnh, cần hiểu ý user | **Vector DB** (tìm theo nghĩa) |
| **Thông tin "hay đổi"** | "VF 9 Eco giá bao nhiêu hôm nay?" | Thay đổi liên tục theo chiến dịch, cần số chính xác | **PostgreSQL** (tra theo khóa) |
| **Thông tin "cực kỳ hay đổi / phụ thuộc địa phương"** | "Lăn bánh HN bao nhiêu? Có khuyến mãi gì? Showroom gần nhất?" | Đổi theo tỉnh/năm/chiến dịch/đại lý, dễ lỗi thời | **KHÔNG lưu DB**, chỉ trả **link nguồn** |

### 2. Minh họa bằng 1 câu hỏi thực tế

**User hỏi:** *"VF 9 Plus giá bao nhiêu, có khuyến mãi gì không?"*

**Cách chatbot xử lý:**

1. **Tìm hiểu "đang nói về xe gì"** — dùng Vector DB để tìm đoạn mô tả VF 9 Plus (thiết kế, động cơ, công nghệ). Từ đó lấy được "mã xe" (model_id) và "phiên bản" (edition_id).
2. **Tra giá chính xác** — dùng PostgreSQL, nhập mã xe vừa lấy → ra giá niêm yết + giá ưu đãi hiện hành.
3. **Trả lời khuyến mãi** — không lưu chi tiết khuyến mãi trong DB (vì đổi liên tục), chatbot chỉ trả **link trang khuyến mãi** để user tự xem thông tin mới nhất.

**Kết quả:** chatbot trả lời đúng giá *tại thời điểm hỏi*, kèm thông tin xe chuẩn, và không bao giờ trả nhầm giá cũ vì giá được đọc trực tiếp từ PostgreSQL.

### 3. Tại sao không lưu giá vào Vector DB?

Nếu lưu giá trong text để embed:
- VinFast đổi giá → phải tìm lại đoạn text chứa giá cũ → xóa → tạo text mới → embed lại toàn bộ → rất tốn kém.
- Có nguy cơ trả giá cũ cho user nếu chưa kịp embed lại.

Giải pháp: text vector chỉ nói *"VF 9 Plus có giá, xem giá hiện hành"*; con số cụ thể lấy từ PostgreSQL ngay lúc user hỏi.

### 4. Tại sao lăn bánh/khuyến mãi/showroom/bảo dưỡng chỉ trả link?

| Thông tin | Tại sao không lưu chi tiết? |
|---|---|
| **Lăn bánh** | Phụ thuộc tỉnh, năm, nghị định mới. Lưu bảng 63 tỉnh × 10 xe × năm = khổng lồ, dễ sai. |
| **Khuyến mãi** | Thay đổi theo chiến dịch tuần/tháng. Lưu chi tiết = phải cập nhật liên tục, dễ lỗi thời. |
| **Showroom** | Đại lý mở/đóng/đổi địa chỉ thường xuyên. Không thể crawl liên tục hết danh sách. |
| **Bảo dưỡng** | Hạng mục bảo dưỡng cụ thể do VinFast quản lý trên trang riêng; chỉ cần trả link đúng model + năm. |

### 5. Version là gì? Tại sao lại có v1, v2?

Mỗi khi thu thập toàn bộ dữ liệu 1 đợt (crawl mới + làm sạch + kiểm tra thủ công xong hết), team sẽ đánh một **version** như `v1`, `v2`, `v3`. Cách này giúp:
- Quay lại version cũ nếu version mới bị lỗi (rollback).
- So sánh đợt này khác đợt trước gì để biết cần cập nhật những gì.
- Không xóa dữ liệu cũ khi tạo version mới.

Version **không** được đánh trong lúc đang thu thập từng phần — chỉ đánh khi xong toàn bộ đợt.

---

## 0. Tóm tắt quyết định

| Quyết sách | Chốt |
|---|---|
| Tách 2 DB | Vector (Qdrant) cho dữ liệu ít đổi + PostgreSQL cho dữ liệu hay đổi |
| Giá trong vector? | **KHÔNG**. Text vector không chứa số tiền. Lấy giá từ Postgres lúc query. |
| Khóa join | `model_id` + `edition_id` (VD: `VF9` + `Eco`) |
| Chi phí lăn bánh | **KHÔNG lưu DB** — chỉ trả link nguồn (đổi theo tỉnh + năm + nghị định, dễ lỗi thời) |
| Showroom/trạm sạc | **KHÔNG lưu DB** — chỉ lưu link nguồn, trả cho user tự xem |
| Khuyến mãi chiến dịch | **KHÔNG lưu DB** — chỉ trả link nguồn (đổi liên tục, dễ lỗi thời) |
| Versioning | Đánh version `v1`, `v2`... **sau khi thu thập XONG cả đợt** dữ liệu; không đánh version từng bước. Không xóa version cũ |
| Layout | `data/clean/<version>/vector/*.jsonl` + `data/clean/<version>/postgres/*.csv` |

---

## 1. Bố cục thư mục output

```
data/
├── raw/                                    # text thô crawl (hiện có, KHÔNG version)
├── 01_thong_tin_san_pham/  ... 08_.../     # markdown đã clean (hiện có)
│
└── clean/                                  # JSONL + CSV versioned (MỚI)
    └── v1/                                   # version thứ 1 (đánh SAU KHI xong cả đợt thu thập)
        ├── _manifest.json                  # index toàn bộ version này
        │
        ├── vector/                         # → ingest Qdrant (COLD, ít đổi)
        │   ├── vivu_specs.jsonl
        │   ├── vivu_product_info.jsonl
        │   ├── vivu_policy.jsonl
        │   ├── vivu_faq.jsonl
        │   └── vivu_maintenance.jsonl
        │
        └── postgres/                       # → COPY INTO PostgreSQL (HOT, hay đổi)
            ├── edition.csv
            ├── price_list.csv
            └── maintenance_schedule.csv
```

> Version chỉ được đánh **khi toàn bộ dữ liệu thu thập xong 1 đợt** (crawl + clean + verify): `v1`, `v2`, `v3`... Không đánh version trong lúc thu thập từng phần.

---

## 2. Phân chia: cái nào đi DB nào

### DB 1 — Vector (Cold: re-embed đắt, update theo tháng/quãng)
- Thông số kỹ thuật: kích thước, pin, động cơ, ADAS, nội/ngoại thất
- Mô tả sản phẩm: tính năng, màu sắc, thiết kế, công nghệ
- Điều khoản pháp lý, chính sách bảo hành, thuê pin
- FAQ bán hàng, lái thử
- Link bảo dưỡng theo model + năm

### DB 2 — PostgreSQL (Hot: UPDATE/UPSERT rẻ, update theo ngày/tuần/chiến dịch)
- **Giá niêm yết + giá ưu đãi** (theo model, edition)
- Lịch bảo dưỡng chi tiết

### KHÔNG lưu DB — chỉ trả link nguồn
- **Showroom/trạm sạc**: không lưu bảng — chỉ lưu link, trả cho user tự xem
- **Khuyến mãi chiến dịch**: không lưu bảng — chỉ trả link nguồn (đổi liên tục theo chiến dịch, lưu dễ lỗi thời)
- **Chi phí lăn bánh**: không lưu bảng — chỉ trả link nguồn (đổi theo tỉnh + năm + nghị định, dễ lỗi thời)

**Key idea:** Vector chunk **không** chứa giá. Khi user hỏi giá → retriever tìm chunk specs → lấy `model_id`+`edition_id` → Postgres JOIN → ghép giá tươi vào prompt LLM.

---

## 3. Schema chunk Vector (JSONL) — 1 dòng = 1 chunk

```jsonc
{
  "id": "vivu_specs:vf9:eco:dimension",           // stable id, = collection:model:edition:section
  "collection": "vivu_specs",                      // tên collection Qdrant
  "vector_version": "v1",            // = tên thư mục version (v1, v2, v3...)

  // ── Khóa join sang Postgres (KHÔNG có giá trong text) ──
  "model_id": "VF9",
  "edition_id": "Eco",

  // ── Phân loại ngữ nghĩa (RAG filter) ──
  "category": "thong_so_ky_thuat",
  "section_path": ["Thông số kỹ thuật", "KÍCH THƯỚC & TẢI TRỌNG"],

  // ── Nội dung clean (KHÔNG có số tiền) ──
  "text": "VF 9 Eco — Chiều dài cơ sở 3.149 mm; Dài × Rộng × Cao 5.119 × 2.254 × 1.697 mm; Khoảng sáng gầm 174 mm; Dung tích cốp (có/gập hàng ghế sau) 212/926 L.",
  "text_type": "table",                            // prose | table | list | key_value | qa_pair | legal_clause | link_list
  "structured": {
    "dimension": {
      "wheelbase_mm": 3149,
      "length_mm": 5119,
      "width_mm": 2254,
      "height_mm": 1697,
      "ground_clearance_mm": 174
    }
  },

  // ── Metadata retrieval ──
  "language": "vi",
  "tags": ["ky_thuat", "kich_thuoc", "vf9"],
  "confidence": 0.9,                               // 1.0 = verify thủ công, <1.0 = OCR lỗi
  "source_file": "data/02_thong_so_ky_thuat/vf9_brochure.md",
  "source_url": "https://storage.googleapis.com/vinfast-data-01/brochure/VF%209_Brochure.pdf",
  "source_type": "brochure",
  "fetched_at": "2026-07-30T21:40:36Z",
  "ingested_at": "2026-08-01T14:00:00Z"
}
```

### Quy ước `id`
```
<collection>:<model_id_lower>:<edition_id_lower>:<section>
vd: vivu_specs:vf9:eco:dimension
    vivu_specs:vf9:eco:powertrain
    vivu_product_info:vf9:exterior_colors
    vivu_faq:chinh_sach_ban_hang:5
    vivu_maintenance:maintenance_links:vf5:2026
```

---

## 4. Schema bảng PostgreSQL

```sql
-- Bảng trung tâm: edition (mỗi model × edition = 1 row)
CREATE TABLE edition (
    model_id        TEXT NOT NULL,         -- "VF9" (chuẩn hóa, không dấu cách)
    edition_id      TEXT NOT NULL,         -- "Eco", "Plus", "NE3LV"
    model_label     TEXT NOT NULL,         -- "VF 9" (hiển thị)
    edition_label   TEXT NOT NULL,         -- "Eco"
    year_range      TEXT,                  -- "2025-2026"
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (model_id, edition_id)
);

-- Giá — đổi liên tục, join qua (model_id, edition_id)
CREATE TABLE price_list (
    model_id            TEXT NOT NULL,
    edition_id          TEXT NOT NULL,
    price_list_vnd      BIGINT,            -- giá niêm yết gốc
    price_promo_vnd     BIGINT,            -- giá ưu đãi hiện hành
    promo_label         TEXT,              -- "Mùa Hè Rực Rỡ"
    vat_included        BOOLEAN DEFAULT true,
    battery_included    BOOLEAN DEFAULT true,
    valid_from          DATE,
    valid_to            DATE,
    updated_at          TIMESTAMPTZ DEFAULT now(),
    source_url          TEXT,
    PRIMARY KEY (model_id, edition_id, valid_from),
    FOREIGN KEY (model_id, edition_id) REFERENCES edition(model_id, edition_id)
);
CREATE INDEX idx_price_active ON price_list(model_id, edition_id) WHERE valid_to IS NULL;

-- Lịch bảo dưỡng chi tiết
CREATE TABLE maintenance_schedule (
    model_id        TEXT NOT NULL,
    year            INT NOT NULL,
    service_type    TEXT NOT NULL,         -- 'kiem_tra', 'bao_duong_10k', 'bao_duong_20k'
    mileage_km      INT,                   -- 10000, 20000, ...
    items           JSONB,                 -- list hạng mục kiểm tra/thay thế
    cost_est_vnd    BIGINT,
    source_url      TEXT,
    updated_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (model_id, year, service_type)
);

-- Tracking version ingest: đánh version SAU KHI thu thập xong cả đợt (v1, v2, v3...)
CREATE TABLE ingest_version ( 
    version                 TEXT PRIMARY KEY,  -- "v1", "v2", "v3"...
    created_at              TIMESTAMPTZ DEFAULT now(),
    prev_version            TEXT,
    repo_commit             TEXT,
    vector_chunks_added     INT,
    vector_chunks_modified  INT,
    vector_chunks_removed   INT,
    pg_rows_upserted        INT,
    notes                   TEXT
);
```

---

## 5. Ví dụ VẬN HÀNH — dữ liệu thật trong repo

### 5.1. Vector JSONL — `vector/vivu_specs.jsonl` (mỗi dòng 1 chunk)

> **Lưu ý:** File `.jsonl` thật mỗi chunk = 1 dòng (compact, không xuống dòng). Bên dưới pretty-print thành JSON array để dễ review. Khi ingest thật vẫn giữ 1 dòng/chunk.

```json
[
  {
    "id": "vivu_specs:vf9:eco:dimension",
    "collection": "vivu_specs",
    "vector_version": "v1",
    "model_id": "VF9",
    "edition_id": "Eco",
    "category": "thong_so_ky_thuat",
    "section_path": ["Thông số kỹ thuật", "KÍCH THƯỚC & TẢI TRỌNG"],
    "text": "VF 9 Eco — Chiều dài cơ sở 3.149 mm; Dài × Rộng × Cao 5.119 × 2.254 × 1.697 mm; Khoảng sáng gầm 174 mm; Khối lượng không tải/trọng tải 2.911/550 kg; Dung tích cốp (có/gập hàng ghế sau) 212/926 L.",
    "text_type": "table",
    "structured": {
      "dimension": {
        "wheelbase_mm": 3149,
        "length_mm": 5119,
        "width_mm": 2254,
        "height_mm": 1697,
        "ground_clearance_mm": 174,
        "kerb_weight_kg": 2911,
        "payload_kg": 550
      }
    },
    "language": "vi",
    "tags": ["ky_thuat", "kich_thuoc", "vf9"],
    "confidence": 0.9,
    "source_file": "data/02_thong_so_ky_thuat/model_specs.json",
    "source_url": "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html",
    "source_type": "specs_json",
    "fetched_at": "2026-07-30T23:01:18Z",
    "ingested_at": "2026-08-01T14:00:00Z"
  },
  {
    "id": "vivu_specs:vf9:eco:powertrain",
    "collection": "vivu_specs",
    "vector_version": "v1",
    "model_id": "VF9",
    "edition_id": "Eco",
    "category": "thong_so_ky_thuat",
    "section_path": ["Thông số kỹ thuật", "ĐỘNG CƠ & VẬN HÀNH"],
    "text": "VF 9 Eco — Động cơ điện AWD/2 cầu toàn thời gian; Công suất tối đa 402 hp (300 kW); Mô-men xoắn 620 Nm; Quãng đường/lần sạc 626 km (WLTP); Dung lượng pin 123 kWh; Sạc nhanh 35 phút (10%-70%); Sạc AC 6,6 kW 1 pha / 11 kW 3 pha; Tốc độ tối đa 200 km/h; Số chỗ ngồi 7.",
    "text_type": "key_value",
    "structured": {
      "powertrain": {
        "max_power_hp": 402,
        "max_power_kw": 300,
        "max_torque_nm": 620,
        "drivetrain": "AWD",
        "range_wltp_km": 626,
        "battery_kwh": 123,
        "fast_charging_min": 35,
        "top_speed_kmh": 200,
        "seats": 7
      }
    },
    "language": "vi",
    "tags": ["ky_thuat", "dong_co", "vf9"],
    "confidence": 1.0,
    "source_file": "data/02_thong_so_ky_thuat/model_specs.json",
    "source_url": "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html",
    "source_type": "specs_json",
    "fetched_at": "2026-07-30T23:01:18Z",
    "ingested_at": "2026-08-01T14:00:00Z"
  },
  {
    "id": "vivu_specs:vf9:eco:adas",
    "collection": "vivu_specs",
    "vector_version": "v1",
    "model_id": "VF9",
    "edition_id": "Eco",
    "category": "thong_so_ky_thuat",
    "section_path": ["Thông số kỹ thuật", "AN TOÀN & ADAS"],
    "text": "VF 9 Eco — ADAS: Hỗ trợ làn đường (las), Kiểm soát làn giữa, Giám sát hành trình thích ứng, Nhận biết biển báo, Cảnh báo va chạm trước, Phanh khẩn cấp trước, Cảnh báo điểm mù, Cảnh báo giao cắt phía sau, Tự động chuyển làn, Giám sát lái xe. Không có: Phanh khẩn cấp sau, Cảnh báo va chạm tại nút giao.",
    "text_type": "key_value",
    "structured": {
      "adas": {
        "las": true,
        "midlanecontrol": true,
        "cruiseControl": "adaptive",
        "forwardCollisionWarning": true,
        "frontEmergencyAutoBraking": true,
        "rearEmergencyAutoBraking": false,
        "blindSpotWarning": true,
        "rearCrossTrafficWarning": true,
        "automaticLaneChange": true,
        "drivingSupervision": true
      }
    },
    "language": "vi",
    "tags": ["ky_thuat", "adas", "an_toan", "vf9"],
    "confidence": 1.0,
    "source_file": "data/02_thong_so_ky_thuat/model_specs.json",
    "source_url": "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html",
    "source_type": "specs_json",
    "fetched_at": "2026-07-30T23:01:18Z",
    "ingested_at": "2026-08-01T14:00:00Z"
  }
]
```

### 5.2. Vector JSONL — `vector/vivu_product_info.jsonl`

```json
[
  {
    "id": "vivu_product_info:vf9:overview",
    "collection": "vivu_product_info",
    "vector_version": "v1",
    "model_id": "VF9",
    "edition_id": "Eco",
    "category": "thong_tin_san_pham",
    "section_path": ["Tổng quan sản phẩm"],
    "text": "VF 9 là mẫu eSUV cỡ lớn hạng sang 7 chỗ hàng đầu của VinFast. Thiết kế lấy cảm hứng từ du thuyền hạng sang, đường nét mạnh mẽ phóng khoáng. Bảo hành xe 200.000 km hoặc 10 năm. Tùy chọn ghế cơ trưởng chỉnh điện tích hợp làm mát, sưởi, massage, sạc không dây. Tùy chọn trần kính toàn cảnh. Màn hình cảm ứng 8 inch cho hàng ghế sau. Trợ lý ảo AI hỗ trợ Tiếng Việt, trợ lái nâng cao cấp độ 2.",
    "text_type": "prose",
    "structured": {
      "warranty": "200.000 km hoặc 10 năm",
      "seats": 7,
      "assistant": "AI Tiếng Việt",
      "adas_level": 2
    },
    "language": "vi",
    "tags": ["mo_ta", "vf9", "hang_sang"],
    "confidence": 1.0,
    "source_file": "data/01_thong_tin_san_pham/vf9.md",
    "source_url": "https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf9",
    "source_type": "product_page",
    "fetched_at": "2026-07-30T22:58:42Z",
    "ingested_at": "2026-08-01T14:00:00Z"
  },
  {
    "id": "vivu_product_info:vf9:exterior_colors",
    "collection": "vivu_product_info",
    "vector_version": "v1",
    "model_id": "VF9",
    "edition_id": "Eco",
    "category": "thong_tin_san_pham",
    "section_path": ["Ngoại thất", "Màu ngoại thất"],
    "text": "VF 9 có 7 màu ngoại thất: Zenith Grey, Urban Mint, Jet Black, Ivy Green, Infinity Blanc, Desat Silver, Crimson Red.",
    "text_type": "list",
    "structured": {
      "colors_exterior": ["Zenith Grey", "Urban Mint", "Jet Black", "Ivy Green", "Infinity Blanc", "Desat Silver", "Crimson Red"]
    },
    "language": "vi",
    "tags": ["mau_sac", "vf9", "ngoai_that"],
    "confidence": 1.0,
    "source_file": "data/01_thong_tin_san_pham/vf9.md",
    "source_url": "https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf9",
    "source_type": "product_page",
    "fetched_at": "2026-07-30T22:58:42Z",
    "ingested_at": "2026-08-01T14:00:00Z"
  }
]
```

### 5.3. Vector JSONL — `vector/vivu_faq.jsonl`

```json
[
  {
    "id": "vivu_faq:chinh_sach_ban_hang:5",
    "collection": "vivu_faq",
    "vector_version": "v1",
    "model_id": null,
    "edition_id": null,
    "category": "ho_tro_mua_xe",
    "section_path": ["FAQ", "Lái thử xe"],
    "text": "Q: Tôi cần chuẩn bị gì để có thể tham gia lái thử?\nA: Khách hàng cần sắp xếp thời gian theo lịch đã hẹn. Ngoài ra cần đảm bảo: ký cam kết trước khi lái thử; chuẩn bị GPLX còn hạn sử dụng bản cứng/VNeID (không bị tước/giữ); đảm bảo sức khỏe đủ điều kiện tham gia giao thông; không sử dụng rượu bia, chất kích thích trước khi lái thử.",
    "text_type": "qa_pair",
    "structured": {
      "question": "Tôi cần chuẩn bị gì để có thể tham gia lái thử?",
      "answer": "Khách hàng cần sắp xếp thời gian theo lịch đã hẹn...",
      "faq_node_url": "https://vinfastauto.com/vn_vi/node/11766"
    },
    "language": "vi",
    "tags": ["lai_thu", "faq"],
    "confidence": 0.8,
    "source_file": "data/04_ho_tro_mua_xe/chinh_sach_ban_hang.md",
    "source_url": "https://vinfastauto.com/vn_vi/chinh-sach-ban-hang",
    "source_type": "faq",
    "fetched_at": "2026-07-30T22:40:00Z",
    "ingested_at": "2026-08-01T14:00:00Z"
  }
]
```

### 5.4. Vector JSONL — `vector/vivu_maintenance.jsonl`

```json
[
  {
    "id": "vivu_maintenance:maintenance_links:vf5:2026",
    "collection": "vivu_maintenance",
    "vector_version": "v1",
    "model_id": "VF5",
    "edition_id": null,
    "category": "dat_lich_bao_duong",
    "section_path": ["Link bảo dưỡng theo model + năm"],
    "text": "Lịch bảo dưỡng VF5 năm 2026. Xem chi tiết hạng mục bảo dưỡng tại trang quản trị VinFast (om.vinfastauto.com). Lưu ý: link năm mới nhất đã verify; link năm cũ = đổi tham số year= trên URL, nên verify lại khi ingest.",
    "text_type": "link_list",
    "structured": {
      "maintenance_url": "https://om.vinfastauto.com/vi_vn/detail?car=VF5&year=2026&lv1=1094661&lv2=1094663&lv3=owfkowqxzmfimdzlmdux",
      "note": "Link năm mới nhất đã verify; link năm cũ = đổi year=, verify lại khi ingest"
    },
    "language": "vi",
    "tags": ["bao_duong", "vf5", "2026"],
    "confidence": 1.0,
    "source_file": "data/08_dat_lich_bao_duong/maintenance_links.md",
    "source_url": "https://om.vinfastauto.com/vi_vn/detail",
    "source_type": "maintenance_link",
    "fetched_at": "2026-07-28T00:00:00Z",
    "ingested_at": "2026-08-01T14:00:00Z"
  }
]
```

### 5.5. Vector JSONL — `vector/vivu_policy.jsonl`

```json
[
  {
    "id": "vivu_policy:dieu_khoan_phap_ly:thue_pin:dieu1",
    "collection": "vivu_policy",
    "vector_version": "v1",
    "model_id": null,
    "edition_id": null,
    "category": "chinh_sach_dich_vu",
    "section_path": ["Điều khoản Pháp lý", "CHÍNH SÁCH DỊCH VỤ CHO THUÊ PIN", "Điều 1. Quyền và nghĩa vụ của VinFast Trading"],
    "text": "Điều 1. Quyền và nghĩa vụ của VinFast Trading (Chính sách cho thuê pin xe ô tô điện): 1.1 VinFast Trading có nghĩa vụ đảm bảo Pin cung cấp cho Khách Hàng theo tiêu chuẩn công bố của nhà sản xuất Pin. 1.2 VinFast Trading có trách nhiệm xử lý các khiếu nại của Khách Hàng về chất lượng Pin và Dịch Vụ. 1.3 Trong phạm vi được pháp luật cho phép, nhà sản xuất Pin và VinFast Trading được miễn trừ trách nhiệm về Pin và Dịch Vụ trong trường hợp có lỗi của Khách Hàng hoặc Khách Hàng không thực hiện đúng quy định nêu tại Hợp Đồng. 1.4 Với tư cách là chủ sở hữu của Pin, VinFast Trading có trách nhiệm bảo trì, bảo dưỡng Pin. 1.5 VinFast Trading có toàn quyền khấu trừ các nghĩa vụ tài chính của Khách Hàng vào khoản Tiền Đặt Cọc Thuê Pin (nếu có).",
    "text_type": "legal_clause",
    "structured": {
      "policy_name": "Chính sách dịch vụ cho thuê pin xe ô tô điện VinFast",
      "clause": "Điều 1",
      "clause_title": "Quyền và nghĩa vụ của VinFast Trading",
      "points": [
        "1.1 Đảm bảo Pin theo tiêu chuẩn nhà sản xuất",
        "1.2 Xử lý khiếu nại chất lượng Pin và Dịch Vụ",
        "1.3 Miễn trừ trách nhiệm khi lỗi từ Khách Hàng",
        "1.4 Bảo trì, bảo dưỡng Pin",
        "1.5 Khấu trừ nghĩa vụ tài chính vào Tiền Đặt Cọc"
      ]
    },
    "language": "vi",
    "tags": ["phap_ly", "thue_pin", "vinfast_trading"],
    "confidence": 1.0,
    "source_file": "data/05_chinh_sach_dich_vu/dieu_khoan_phap_ly.md",
    "source_url": "https://vinfastauto.com/vn_vi/dieu-khoan-phap-ly",
    "source_type": "policy_legal",
    "fetched_at": "2026-07-30T21:35:52Z",
    "ingested_at": "2026-08-01T14:00:00Z"
  }
]
```

---

### 5.6. PostgreSQL CSV — `postgres/edition.csv`

```csv
model_id|edition_id|model_label|edition_label|year_range|is_active|created_at|updated_at
VF9|Eco|VF 9|Eco|2025-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF9|Plus|VF 9|Plus tùy chọn 7 chỗ|2025-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF9|Plus8|VF 9|Plus tùy chọn 8 chỗ|2025-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF8|Eco|VF 8|Eco|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF8|Plus|VF 8|Plus|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF7|Eco|VF 7|Eco|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF7|Plus|VF 7|Plus|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF6|Eco|VF 6|Eco|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF6|Plus|VF 6|Plus|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF5|Eco|VF 5|Eco|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF5|Plus|VF 5|Plus|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF3|Eco|VF 3|Eco|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF3|Plus|VF 3|Plus|2024-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VF2|Eco|VF 2|Eco|2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
VFMPV7|Eco|VF MPV 7|Eco|2025-2026|t|2026-08-01T14:00:00Z|2026-08-01T14:00:00Z
```

### 5.7. PostgreSQL CSV — `postgres/price_list.csv` (HOT — update khi VinFast đổi giá)

```csv
model_id|edition_id|price_list_vnd|price_promo_vnd|promo_label|vat_included|battery_included|valid_from|valid_to|updated_at|source_url
VF9|Eco|1348000000|1280600000|Ưu đãi đặt cọc 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf9
VF9|Plus|1529000000|1452550000|Ưu đãi đặt cọc 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf9
VF8|Eco|1090000000|990000000|Ưu đãi đặt cọc 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf8-the-all-new
VF8|Plus|1290000000|1180000000|Ưu đãi đặt cọc 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf8-the-all-new
VF7|Eco|990000000|890000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf7
VF7|Plus|1190000000|1090000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf7
VF6|Eco|890000000|790000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf6
VF6|Plus|990000000|890000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf6
VF5|Eco|590000000|520000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf5
VF5|Plus|690000000|620000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf5
VF3|Eco|290000000|258000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf3
VF3|Plus|350000000|318000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf3
VF2|Eco|240000000|188000000|Đặt cọc 15-17/7/2026|t|t|2026-07-15|2026-07-17|2026-08-01T14:00:00Z|https://vinfastauto.com/vn_vi/dat-coc-xe-vf2
VFMPV7|Eco|1550000000|1450000000|Ưu đãi 2026|t|t|2026-07-01||2026-08-01T14:00:00Z|https://shop.vinfastauto.com/vn_vi/san-pham/vinfast-vf-mpv7
```

> Khi VinFast đổi giá → chỉ cần 1 câu SQL `UPDATE price_list SET price_promo_vnd = ... WHERE model_id='VF9' AND edition_id='Eco'`. Không cần re-embed vector.

### 5.8. Khuyến mãi chiến dịch — KHÔNG lưu DB, chỉ trả link nguồn

> Khuyến mãi đổi liên tục theo chiến dịch → không lưu bảng `promotion`. Chatbot chỉ trả **link nguồn** để user tự xem thông tin mới nhất:

```text
07_khuyen_mai_uu_dai/dat_coc_vf2.md   → https://vinfastauto.com/vn_vi/dat-coc-xe-vf2
07_khuyen_mai_uu_dai/MinioGreen.md    → https://vinfastauto.com/vn_vi/khuyen-mai/minio-green
07_khuyen_mai_uu_dai/chuyen_doi_xe_xang.md → https://vinfastauto.com/vn_vi/uu-dai-chuyen-doi
```

### 5.9. Chi phí lăn bánh — KHÔNG lưu DB, chỉ trả link nguồn

> Chi phí lăn bánh đổi theo tỉnh + năm + nghị định → không lưu bảng `roadside_cost`. Chỉ trả **link nguồn** để user tự tính mới nhất (`data/03_chi_phi_lan_banh/` đang rỗng, link sẽ bổ sung khi crawl):

```text
03_chi_phi_lan_banh/  → https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh
```

### 5.10. Showroom/trạm sạc — KHÔNG lưu DB, chỉ trả link nguồn

> Showroom/trạm sạc mở/đóng đổi liên tục → không lưu bảng `showroom`. Chỉ lưu **link nguồn** (`data/06_showroom_tram_sac/utility_links.md`), chatbot trả link cho user tự xem danh sách mới nhất:

```text
06_showroom_tram_sac/utility_links.md → https://banggiavinfast.vn/danh-sach-cac-showroom-dai-ly-vinfast-tai-ha-noi/
```

---

## 6. File `_manifest.json` (index mỗi version)

```jsonc
{
  "version": "v1",
  "created_at": "2026-08-01T14:00:00Z",
  "created_by": "scripts/clean_to_jsonl.py + scripts/split_cold_hot.py",
  "prev_version": null,
  "repo_commit": "a1b2c3d",

  "vector": {
    "collections": {
      "vivu_specs":          { "file": "vector/vivu_specs.jsonl",          "chunks": 180, "added": 12, "modified": 2, "removed": 0 },
      "vivu_product_info":   { "file": "vector/vivu_product_info.jsonl",   "chunks": 120, "added": 4,  "modified": 0, "removed": 0 },
      "vivu_policy":         { "file": "vector/vivu_policy.jsonl",         "chunks": 95,  "added": 0,  "modified": 0, "removed": 0 },
      "vivu_faq":            { "file": "vector/vivu_faq.jsonl",            "chunks": 30,  "added": 0,  "modified": 0, "removed": 0 },
      "vivu_maintenance":   { "file": "vector/vivu_maintenance.jsonl",   "chunks": 28,  "added": 4,  "modified": 0, "removed": 0 }
    },
    "total_chunks": 453,
    "total_added": 20, "total_modified": 2, "total_removed": 0
  },

  "postgres": {
    "tables": {
      "edition":              { "file": "postgres/edition.csv",              "rows": 14, "upserted": 14 },
      "price_list":           { "file": "postgres/price_list.csv",           "rows": 13, "upserted": 13, "price_changed": 8 },
      "maintenance_schedule": { "file": "postgres/maintenance_schedule.csv", "rows": 0,  "upserted": 0 }
    },
    "total_rows_upserted": 27
  },

  "link_only": {  // showroom + khuyến mãi + lăn bánh: không lưu DB, chỉ trả link nguồn
    "showroom_urls": ["https://banggiavinfast.vn/danh-sach-cac-showroom-dai-ly-vinfast-tai-ha-noi/"],
    "promotion_urls": ["https://vinfastauto.com/vn_vi/dat-coc-xe-vf2", "https://vinfastauto.com/vn_vi/khuyen-mai/minio-green"],
    "roadside_cost_urls": ["https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh"]
  },

  "pipeline_steps": ["clean_to_jsonl", "split_cold_hot", "ingest_vector", "ingest_postgres"],
  "schema_version": "1.0.0"
}
```

---

## 7. Query time — Hybrid retrieval (minh họa cho dev)

**Câu hỏi user:** "VF 9 Plus giá bao nhiêu, lăn bánh HN 2026 có khuyến mãi gì không?"

```python
# Bước 1: Vector search — tìm chunk specs/product info (KHÔNG có giá)
vector_hits = qdrant.search(
    collection="vivu_specs",
    query=embed("VF 9 Plus giá lăn bánh"),
    filter={"model_id": "VF9", "edition_id": "Plus"},
    limit=3
)
# → trả chunk specs có model_id="VF9", edition_id="Plus"

model_id, edition_id = vector_hits[0].model_id, vector_hits[0].edition_id

# Bước 2: Postgres JOIN — lấy giá hiện hành
price = pg.execute("""
    SELECT price_list_vnd, price_promo_vnd, promo_label, updated_at
    FROM price_list
    WHERE model_id = %s AND edition_id = %s
      AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
    ORDER BY valid_from DESC LIMIT 1
""", [model_id, edition_id])
# → price_list_vnd=1,529,000,000, price_promo_vnd=1,452,550,000, promo_label="Ưu đãi đặt cọc 2026"

# Khuyến mãi + showroom + lăn bánh: KHÔNG query DB — chỉ trả link nguồn cho user tự xem
link_only = [
    "Khuyến mãi: https://vinfastauto.com/vn_vi/khuyen-mai",
    "Showroom: https://banggiavinfast.vn/danh-sach-cac-showroom-dai-ly-vinfast-tai-ha-noi/",
    "Chi phí lăn bánh: https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh",
]

# Bước 3: Ghép prompt cho LLM
prompt = f"""
Thông tin xe từ cơ sở tri thức:
{vector_hits[0].text}

Giá hiện hành (cập nhật {price.updated_at}):
- Niêm yết: {format_vnd(price.price_list_vnd)}
- Ưu đãi: {format_vnd(price.price_promo_vnd)} ({price.promo_label})

Tham khảo (link mới nhất, không nhập số liệu cụ thể):
{chr(10).join(link_only)}

Trả lời câu hỏi: "VF 9 Plus giá bao nhiêu, lăn bánh HN 2026 có khuyến mãi gì không?"
"""
```

**Kết quả LLM trả (mong đợi):**
> VF 9 Plus giá niêm yết 1.529.000.000 VNĐ, giá ưu đãi hiện hành 1.452.550.000 VNĐ (chương trình Ưu đãi đặt cọc 2026). Về chi phí lăn bánh, khuyến mãi hiện hành và danh sách showroom, quý khách vui lòng xem thêm: [Chi phí lăn bánh](https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh), [Link khuyến mãi](https://vinfastauto.com/vn_vi/khuyen-mai), [Link showroom](https://banggiavinfast.vn/danh-sach-cac-showroom-dai-ly-vinfast-tai-ha-noi/) (không trả số liệu cụ thể từ DB).

---

## 8. Quy tắc clean (áp dụng trước khi emit JSONL/CSV)

| # | Việc | Lý do |
|---|---|---|
| C1 | Bỏ ảnh markdown `![...](url)` | noise |
| C2 | Bỏ ghi chú verify `> ...` + YAML front-matter (nạp vào metadata) | nội bộ |
| C3 | Sửa lỗi OCR font brochure ("CÂM HƯNG" → "CẢM Hứng", "CÂN BĂNG dòng" → "Cân bằng dòng") | PDF OCR lỗi dấu |
| C4 | Chuẩn hóa số: `5.119 x 2.254` → `5119 × 2254`; đơn vị gắn liền `mm`, `kWh`, `km` | dễ lookup |
| C5 | Bảng Markdown → giữ nguyên, kèm `text_type=table` | LLM đọc tốt |
| C6 | Chunk theo heading → cắt theo câu, `max_len=400`, overlap câu cuối, không cắt giữa bảng/câu | `clean_to_jsonl.py` (`apply_chunking` + `split_by_sentences`) |
| C7 | FAQ: 1 Q&A = 1 chunk `qa_pair` | `chinh_sach_ban_hang.md` có 30 Q&A |
| C8 | Legal: 1 Điều = 1 chunk `legal_clause` | `dieu_khoan_phap_ly.md` có Điều 1-7 |
| C9 | **Tách giá khỏi text vector** — số tiền chỉ vào Postgres | tránh giá lỗi thời trong embedding |
| C10 | `model_specs.json`: key `priceValue`/`promoPrice` → Postgres; key `specs`/`adas`/`dimension` → Vector | tách hot/cold trong cùng file |

---

## 9. Lợi ích & đánh đổi

| Lợi ích | Đánh đổi |
|---|---|
| Giá luôn tươi — update 1 câu SQL, không re-embed | Phải duy trì 2 DB + join logic ở retriever |
| Tiết kiệm chi phí embedding (cold chunk giữ lâu) | `model_specs.json` cần split cẩn thận |
| Rollback dễ: version cũ (v1, v2...) vector + Postgres snapshot | Cần sync version giữa 2 DB (manifest quản lý) |
| Vector text sạch, không nguy cơ trả giá cũ | Retriever 2 bước thay vì 1 |
| Không lo showroom/khuyến mãi/lăn bánh lỗi thời trong DB — chỉ trả link nguồn | User phải tự xem link để biết chi tiết |

---

## 10. Pipeline đề xuất (versioned)

```
data/raw/*.txt ─┐
                ├─► 1. clean_to_jsonl.py ─┐
data/01..08 md ─┤                          ├─► data/clean/<version>/  (đánh v1, v2... SAU KHI xong cả đợt)
data/02/specs.json┘                         │   ├── vector/*.jsonl  → ingest Qdrant
                  ├─► 2. split_cold_hot.py ─┤   └── postgres/*.csv  → COPY INTO Postgres
                  └─► 3. verify (manual) ──┘        │
                                                      └─► _manifest.json (tracking cả 2 DB)
```

> **Khi nào đánh version:** thu thập toàn bộ dữ liệu 1 đợt (crawl → clean → verify) xong hết mới đánh `v1`, `v2`... Trong lúc thu thập từng phần KHÔNG đánh version.

**Cơ chế diff incremental:**
1. Ingest mới đọc `_manifest.json`.
2. `vector.added` → insert vector. `vector.modified` → delete+insert. `vector.removed` → delete.
3. `postgres.upserted` → `INSERT ... ON CONFLICT UPDATE`.
4. Chunk/row không đổi → skip, tiết kiệm chi phí.

---

## 11. Trạng thái dữ liệu hiện tại (review để team biết gap)

| Category | File có | Trạng thái | Đi DB nào |
|---|---|---|---|
| 01_thong_tin_san_pham | 9 file .md | Có dữ liệu, cần clean ảnh/OCR | Vector |
| 02_thong_so_ky_thuat | 10 brochure .md + `model_specs.json` 147KB | Có specs (cold) + price/promo (hot) lẫn nhau | **Split cả 2 DB** |
| 03_chi_phi_lan_banh | rỗng | Có link nguồn | KHÔNG lưu DB — chỉ trả link |
| 04_ho_tro_mua_xe | `chinh_sach_ban_hang.md` 30 Q&A | Có (cần crawl sâu từng node FAQ) | Vector |
| 05_chinh_sach_dich_vu | `dieu_khoan_phap_ly.md` 46KB | Có | Vector |
| 06_showroom_tram_sac | 1 link | Có link nguồn | KHÔNG lưu DB — chỉ trả link |
| 07_khuyen_mai_uu_dai | 8 file .md | Có nội dung | KHÔNG lưu DB — chỉ trả link nguồn |
| 08_dat_lich_bao_duong | `maintenance_links.md` | Có link, chưa crawl chi tiết | Vector (link) + Postgres (schedule) |

---

**Hết file.** Mọi thắc mắc/điều chỉnh schema — thảo luận trước khi triển khai `scripts/clean_to_jsonl.py` và `scripts/split_cold_hot.py`.