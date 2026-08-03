# UC-01 — Clean / Format / Chunking / Retriever / LLM

> Tài liệu tham khảo chi tiết phần đầu pipeline: làm sạch, định dạng, chunking hóa dữ liệu, và cách retriever + LLM sử dụng.

---

## 1. Tổng quan luồng

```text
RAW (markdown + specs.json)
        │
        ▼
┌─────────────────┐
│     CLEAN       │  ← bỏ noise, ảnh, OCR typo, giá tiền
└─────────────────┘
        │
        ▼
┌─────────────────┐
│     FORMAT      │  ← schema JSONL cố định, model_id/edition_id, metadata
└─────────────────┘
        │
        ▼
┌─────────────────┐
│    CHUNKING     │  ← chia theo heading, target 1000 chars, hard 1500 chars
└─────────────────┘
        │
        ▼
┌─────────────────┐
│    RETRIEVER    │  ← embed query, vector search, filter model/edition
└─────────────────┘
        │
        ▼
┌─────────────────┐
│      LLM        │  ← ghép context + giá (Postgres) + link-only
└─────────────────┘
```

---

## 2. CLEAN — Làm sạch gì?

### 2.1. Input

- Markdown từ `data/01_thong_tin_san_pham/`, `data/02_thong_so_ky_thuat/`, `data/04_ho_tro_mua_xe/`, `data/05_chinh_sach_dich_vu/`, `data/08_dat_lich_bao_duong/`.
- `data/02_thong_so_ky_thuat/model_specs.json`.

### 2.2. Các bước clean

| # | Việc | Ví dụ | Lý do |
|---|---|---|---|
| C1 | Bỏ markdown images | `![alt](url)` | Ảnh không mang ngữ nghĩa search |
| C2 | Bỏ HTML tags | `<div>`, `<span>` | Chỉ giữ text có ý nghĩa |
| C3 | Bỏ internal notes | `> FAQ excerpt...`, `> Lưu ý ingest...` | Ghi chú nội bộ team |
| C4 | Bỏ YAML frontmatter | `--- url: ... ---` | Đưa metadata vào field, không nhúng text |
| C5 | Sửa lỗi OCR | `CÂM HƯNG` → `Cảm hứng`, `croundClearance` → `groundClearance` | Brochure PDF OCR lỗi font/dấu |
| C6 | Chuẩn hóa số | `5.119 x 2.254` → `5119 × 2254` | Dễ lookup, tránh nhầm decimal |
| C7 | Tách giá khỏi text vector | Đoạn "Giá bán từ 1.280.600.000 VNĐ" → bỏ | Giá hay đổi, không để trong embedding |
| C8 | Bỏ navigation noise | `Đăng nhập / Đăng ký`, `Hero Background` | UI elements không phải nội dung |
| C9 | Gộp fragment ngắn | `"VF 9"`, `"Lựa chọn"`, `"tận hưởng"` → `"VF 9 Lựa chọn tận hưởng"` | Tránh chunk vô nghĩa |

### 2.3. Quy tắc drop giá

Chỉ drop paragraph khi **đồng thời**:

- Chứa từ khóa giá: `giá bán`, `giá niêm yết`, `giá ưu đãi`, `triệu đồng`, `vnđ`, `đặt cọc`, `lăn bánh`...
- VÀ có số tiền kèm đơn vị: `1.280.600.000 VNĐ`, `188 triệu`.

Không drop số kỹ thuật như `626 km`, `123 kWh`, `402 hp` vì chúng không kèm đơn vị tiền.

---

## 3. FORMAT — Định dạng thế nào?

### 3.1. Schema mỗi chunk (JSONL)

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
  "structured": {
    "dimension": {
      "length_mm": 5119,
      "width_mm": 2254,
      "height_mm": 1697
    }
  },
  "language": "vi",
  "tags": ["ky_thuat", "vf9", "kich_thuoc"],
  "confidence": 1.0,
  "source_file": "data/02_thong_so_ky_thuat/model_specs.json",
  "source_url": "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html",
  "source_type": "specs_json",
  "fetched_at": "...",
  "ingested_at": "..."
}
```

### 3.2. Các `text_type`

| Type | Khi nào dùng |
|---|---|
| `prose` | Đoạn văn mô tả |
| `table` | Bảng Markdown có `|` và `---` |
| `list` | Danh sách item `-` hoặc `1. 2. 3.` |
| `key_value` | Thông số kỹ thuật dạng `key: value` |
| `qa_pair` | FAQ 1 câu hỏi + 1 câu trả lời |
| `legal_clause` | Điều khoản pháp lý từng Điều |
| `link_list` | Danh sách link bảo dưỡng |

### 3.3. Chuẩn hóa khóa

- `model_id`: `VF9`, `VF8`, `VF7`, `VF5`, `VF3`, `VF2`, `VFMPV7`, `ECVAN`...
- `edition_id`: `Eco`, `Plus`, `PlusCaptain`, `TieuChuan`...
- Map từ raw: `Products-Car-VF9` → `VF9`, `NE3LV` → `Eco`.

### 3.4. Phân loại collection

| Collection | Nguồn | Mục đích |
|---|---|---|
| `vivu_specs` | `model_specs.json` + brochure | Trả lời thông số kỹ thuật |
| `vivu_product_info` | `01_thong_tin_san_pham/*.md` | Trả lời mô tả, tính năng, màu sắc |
| `vivu_faq` | `04_ho_tro_mua_xe/*.md` | Trả lời FAQ bán hàng, lái thử |
| `vivu_policy` | `05_chinh_sach_dich_vu/*.md` | Trả lời chính sách, điều khoản |
| `vivu_maintenance` | `08_dat_lich_bao_duong/*.md` | Trả link bảo dưỡng |

---

## 4. CHUNKING — Chia nhỏ thế nào?

### 4.1. Chiến lược

- **Split theo heading hierarchy** (`#`, `##`, `###`).
- **Target** ~1000 chars.
- **Hard limit** 1500 chars.
- **Overlap** 100 chars giữa các chunk liền kề (nếu split).
- **Không cắt giữa bảng** — nếu bảng bị cắt, lặp lại header row.
- **Không cắt giữa câu** — ưu tiên cắt ở dấu xuống dòng giữa các đoạn.

### 4.2. Quy tắc đặc biệt theo loại dữ liệu

| Loại dữ liệu | Quy tắc chunk |
|---|---|
| FAQ | 1 Q&A = 1 chunk (`qa_pair`) |
| Legal | 1 Điều = 1 chunk (`legal_clause`) |
| Specs JSON | 1 section = 1 chunk (dimension, powertrain, adas, exterior, interior, safety) |
| Product info | Theo heading section |
| Brochure OCR | Theo block/page, confidence thấp hơn |
| Maintenance links | 1 model × 1 năm = 1 chunk |

### 4.3. Stable ID

```text
<collection>:<model_id_lower>:<edition_id_lower>:<section_slug>:<seq>

vd:
  vivu_specs:vf9:eco:kich_thuoc:1
  vivu_faq:general:all:faq_lai_thu:5
  vivu_maintenance:vf5:all:bao_duong_2026:1
```

---

## 5. RETRIEVER — Tìm kiếm như thế nào?

### 5.1. Input

Câu hỏi user, ví dụ: `"VF 9 Plus giá bao nhiêu, có ADAS gì?"`

### 5.2. Các bước

1. **Embed query** bằng cùng model embedding (MiniLM-L12-v2).
2. **Entity detection**: thử nhận diện `model_id`, `edition_id` từ query.
   - VD: `VF 9` → `VF9`, `Plus` → `Plus`.
3. **Chọn collection**:
   - Hỏi thông số → `vivu_specs`
   - Hỏi mô tả/tính năng/màu → `vivu_product_info`
   - Hỏi chính sách/lái thử → `vivu_faq` / `vivu_policy`
   - Nếu không rõ → search trên tất cả collection.
4. **Vector search** với filter `model_id`/`edition_id` nếu detect được.
5. **Trả về top-k** (k=3~5) chunks kèm metadata.

### 5.3. Lấy giá từ Postgres

Nếu chunk match có `model_id` + `edition_id`, thực hiện:

```sql
SELECT price_list_vnd, price_promo_vnd, promo_label, updated_at
FROM price_list
WHERE model_id = 'VF9' AND edition_id = 'Plus'
  AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
ORDER BY valid_from DESC
LIMIT 1;
```

---

## 6. LLM — Ghép prompt và trả lời

### 6.1. Prompt template

```text
Thông tin xe từ cơ sở tri thức:
{vector_context}

Giá hiện hành (cập nhật {updated_at}):
- Niêm yết: {price_list_vnd}
- Ưu đãi: {price_promo_vnd} ({promo_label})

Tham khảo (link mới nhất):
- Khuyến mãi: {promo_url}
- Chi phí lăn bánh: {roadside_url}
- Showroom: {showroom_url}

Trả lời câu hỏi: "{user_query}"
```

### 6.2. Quy tắc response

- Trả lời bằng tiếng Việt.
- Nếu hỏi giá: đọc số từ Postgres, không tự bịa.
- Nếu hỏi showroom/lăn bánh/khuyến mãi: chỉ trả link, không trả số liệu cụ thể.
- Nếu không tìm thấy thông tin: thừa nhận và gợi ý link nguồn.
- Luôn kèm nguồn/thời điểm cập nhật nếu có.

### 6.3. Ví dụ output mong đợi

**User:** "VF 9 Plus giá bao nhiêu?"

**LLM:**
> VF 9 Plus giá niêm yết 1.529.000.000 VNĐ, giá ưu đãi hiện hành 1.452.550.000 VNĐ (chương trình Ưu đãi đặt cọc 2026, cập nhật 2026-08-03).
> Giá đã bao gồm VAT và pin.
> Tham khảo chi phí lăn bánh và khuyến mãi mới nhất: [link].

---

## 7. Tóm tắt các quy tắc bắt buộc

1. **Clean**: text vector sạch, không ảnh, không noise, không giá.
2. **Format**: schema cố định, khóa chuẩn hóa, metadata đầy đủ.
3. **Chunking**: theo heading, target 1000/hard 1500, giữ nguyên bảng/Q&A/Điều.
4. **Retriever**: embed query, search collection phù hợp, filter model/edition.
5. **LLM**: ghép context + giá Postgres + link-only; không bịa số liệu.

---

## 8. Tham khảo

- `docs/UC01_PRODUCT_INFORMATION.md` — kiến trúc tổng thể.
- `data/DATA_PIPELINE_GUIDE.md` — chạy clean pipeline.
- `scripts/clean_data/clean_to_jsonl.py` — code clean/format.
- `scripts/clean_data/split_cold_hot.py` — code chunking + split.
