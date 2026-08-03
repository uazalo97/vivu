# UC-01 — Product Information

> Priority: [MUST]
> User Story: Là người đang tìm hiểu mua xe, tôi muốn tra cứu thông số, tính năng, giá và chính sách để hiểu rõ một mẫu xe hoặc phiên bản.

---

## 1. Mục tiêu use case

Cung cấp cho người dùng thông tin chính xác, kịp thời về:

- **Thông số kỹ thuật** của từng mẫu xe và phiên bản.
- **Mô tả sản phẩm**, tính năng nổi bật, ngoại/nội thất, công nghệ.
- **Giá xe**: niêm yết và giá ưu đãi hiện hành.
- **Chính sách**: bảo hành, thuê pin, điều khoản pháp lý, FAQ bán hàng.
- **Link tham khảo**: chi phí lăn bánh, khuyến mãi, showroom/trạm sạc (không lưu chi tiết trong DB).

---

## 2. Kiến trúc dữ liệu

Dữ liệu được tách thành **2 DB** để cân bằng giữa độ chính xác và chi phí cập nhật.

```mermaid
flowchart LR
    A[User query] --> B{Retriever}
    B -- semantic search --> C[Vector DB Qdrant]
    B -- key lookup --> D[PostgreSQL]
    C -- model_id + edition_id --> D
    D -- price + policy --> E[LLM Prompt]
    C -- specs + features --> E
    E --> F[Response]
```

### 2.1. Vector DB (Cold — ít đổi)

| Collection | Nội dung | Cập nhật |
|---|---|---|
| `vivu_specs` | Thông số kỹ thuật: kích thước, động cơ, pin, ADAS, nội/ngoại thất | Theo tháng/quý |
| `vivu_product_info` | Mô tả sản phẩm, tính năng, màu sắc, công nghệ | Theo tháng/quý |
| `vivu_policy` | Điều khoản pháp lý, chính sách bảo hành, thuê pin | Theo tháng/quý |
| `vivu_faq` | FAQ bán hàng, lái thử | Theo tháng/quý |
| `vivu_maintenance` | Link bảo dưỡng theo model + năm | Theo năm |

### 2.2. PostgreSQL (Hot — hay đổi)

| Bảng | Nội dung | Cập nhật |
|---|---|---|
| `edition` | Bản đồ model × edition | Theo đợt ra mắt xe/phiên bản |
| `price_list` | Giá niêm yết, giá ưu đãi, khuyến mãi | Theo ngày/tuần/chiến dịch |
| `maintenance_schedule` | Lịch bảo dưỡng chi tiết (nếu có) | Theo năm |
| `ingest_version` | Tracking version đã ingest | Mỗi lần ingest |

### 2.3. Không lưu DB — chỉ trả link

| Thông tin | Lý do không lưu |
|---|---|
| Chi phí lăn bánh | Phụ thuộc tỉnh, năm, nghị định |
| Khuyến mãi chiến dịch | Thay đổi liên tục theo chiến dịch |
| Showroom/trạm sạc | Đại lý mở/đóng/đổi địa chỉ thường xuyên |

---

## 3. Luồng xử lý câu hỏi

### 3.1. Ví dụ: "VF 9 Plus giá bao nhiêu?"

1. **Vector search** trên `vivu_specs` + `vivu_product_info` với query embedding.
2. Từ chunk match, lấy `model_id = VF9`, `edition_id = Plus`.
3. **PostgreSQL JOIN**: `SELECT * FROM price_list WHERE model_id='VF9' AND edition_id='Plus' AND valid_to IS NULL`.
4. Ghép thông tin specs + giá vào prompt LLM.
5. LLM trả lời bằng tiếng Việt, dùng số giá từ Postgres.

### 3.2. Ví dụ: "VF 9 có những màu ngoại thất nào?"

1. Vector search trên `vivu_product_info`.
2. Trả về chunk màu sắc (không cần Postgres).

### 3.3. Ví dụ: "Lăn bánh HN 2026 có khuyến mãi gì?"

1. Không query DB lấy số liệu.
2. Trả link nguồn từ `_manifest.json["link_only"]`:
   - Chi phí lăn bánh: `https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh`
   - Khuyến mãi: `https://vinfastauto.com/vn_vi/khuyen-mai`

---

## 4. Pipeline dữ liệu

```text
scripts/clean_data/clean_to_jsonl.py --version v1
        ↓
data/clean/v1/intermediate/
        ↓
scripts/clean_data/split_cold_hot.py --version v1
        ↓
data/clean/v1/vector/*.jsonl
data/clean/v1/postgres/*.csv
data/clean/v1/_manifest.json
        ↓
scripts/ingest/vector_ingest.py --version v1  → Qdrant
scripts/ingest/postgres_ingest.py --version v1 → PostgreSQL
```

Chi tiết chạy từng bước xem:

- `data/DATA_PIPELINE_GUIDE.md`
- `scripts/ingest/README.md`

---

## 5. Schema tóm tắt

### 5.1. Vector chunk (mỗi dòng JSONL)

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
  "ingested_at": "..."
}
```

### 5.2. Postgres bảng `price_list`

| Cột | Ý nghĩa |
|---|---|
| `model_id` | Mã model chuẩn hóa, VD: `VF9` |
| `edition_id` | Mã edition chuẩn hóa, VD: `Eco`, `Plus` |
| `price_list_vnd` | Giá niêm yết gốc |
| `price_promo_vnd` | Giá ưu đãi hiện hành |
| `promo_label` | Tên chương trình khuyến mãi |
| `vat_included` | Đã bao gồm VAT |
| `battery_included` | Đã bao gồm pin |
| `valid_from` / `valid_to` | Hiệu lực giá |
| `source_url` | Link nguồn |

---

## 6. Quy tắc bắt buộc

1. **Vector text không chứa giá tiền**. Số tiền chỉ nằm trong Postgres.
2. **Giá ưu đãi lấy từ Postgres**, không từ embedding text.
3. **Version** (`v1`, `v2`...) chỉ đánh khi toàn bộ đợt thu thập xong.
4. **Showroom / khuyến mãi / lăn bánh chỉ trả link**, không trả số liệu cụ thể từ DB.
5. **Mỗi model × edition = 1 row trong `edition.csv`**.
6. **Stable IDs**: `collection:model:edition:section:seq` trong JSONL, chuyển thành UUIDv5 khi ingest Qdrant.

---

## 7. Trạng thái hiện tại

| Thành phần | Trạng thái |
|---|---|
| Clean pipeline | ✅ `scripts/clean_data/` |
| Vector output | ✅ `data/clean/v1/vector/*.jsonl` |
| Postgres CSV output | ✅ `data/clean/v1/postgres/*.csv` |
| Ingest Qdrant local | ✅ `scripts/ingest/vector_ingest.py` |
| Ingest Postgres local | ✅ `scripts/ingest/postgres_ingest.py` |
| Docker Compose local DB | ✅ `docker-compose.yml` |
| Retriever + LLM prompt | ⏳ Phase tiếp theo |
| Maintenance schedule chi tiết | ⏳ Chờ data bổ sung |

---

## 8. Tham khảo

- `data/EXAMPLE_DATA_FORMAT.md` — kiến trúc 2 DB chi tiết.
- `data/DATA_PIPELINE_GUIDE.md` — hướng dẫn chạy clean pipeline.
- `scripts/ingest/README.md` — hướng dẫn ingest local.
