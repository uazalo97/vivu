# Đề xuất — Chiến lược Chunking cho UC-01

> ⚠️ **TRẠNG THÁI: ĐÃ ÁP DỤNG** (2026-08-03) — được triển khai trong `scripts/clean_data/clean_to_jsonl.py`.
> Điểm khác so với proposal: đo thực tế cho thấy window embedding ≈ **400 chars** (không phải 500),
> nên dùng `max_len=400`, cắt theo **câu** (không phải ký tự), overlap = **câu cuối hoàn chỉnh**.
>
> 📌 **Cập nhật sau**: embedding đã chuyển sang **OpenRouter API** (`openai/text-embedding-3-small`, window 8191 token)
> — `max_len=400` hiện là dư địa an toàn, có thể tăng lên 1000-2000 (xem `data/DATA_PIPELINE_GUIDE.md` §3.2).
> `max_len=400` trong proposal dưới đây là số liệu cũ cho MiniLM local.

---

## 1. Vấn đề hiện tại

### 1.1. Tham số không khớp model embedding

Pipeline hiện dùng model **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** (384 chiều, max sequence length **~128 token**).

- Tiếng Việt trung bình ~1 token / 2–4 ký tự → model "nhìn" hiệu quả trong khoảng **300–500 ký tự** một lần.
- Các tham số hiện tại `target=1000`, `hard=1500` **quá dài** so với cửa sổ embedding.
- Hệ quả: phần vượt 128 token bị **truncate** khi embedding → thông tin cuối chunk mất khỏi vector, dù vẫn tốn công lưu trữ và vẫn được gán ID.

> Đây là vấn đề thực sự cần sửa, dù hiện chưa có chunk nào bị size-chunk cắt (vì ngưỡng 1500 quá cao so với dữ liệu thực — xem §1.2).

### 1.2. Size-chunking hiện là no-op trên dữ liệu thực

Đo trên `data/clean/v1/intermediate/vector.jsonl` (503 chunks trước khi gán ID):

| Nhóm | Số lượng |
|------|---------|
| ≤ 1000 chars (giữ nguyên) | 425 |
| 1000–1500 chars (giữ nguyên) | 78 |
| **> 1500 chars (bị cắt)** | **0** |

→ Không có chunk nào vượt 1500, nên `apply_chunking` (feature mới, chưa commit) không cắt được gì. Kết quả 496 chunks sau khi `split_cold_hot` loại bỏ các chunk chứa giá tiền.

### 1.3. Overlap cắt giữa câu

Trong `split_oversized_chunk`, overlap được tính bằng `"\n".join(cur[-3:])[-overlap:]`:
- Nếu dòng dài, 3 dòng cuối > 100 chars → chỉ giữ 100 chars **cuối** → cắt **giữa dòng/câu**.
- Overlap bắt đầu giữa câu → gây nhiễu embedding cho chunk kế.

### 1.4. Một thuật toán chung cho mọi loại nội dung

Chunk prose, bảng, key-value specs, FAQ hiện cùng đi qua `split_oversized_chunk` (chỉ phân biệt bảng markdown). Từng loại có đặc thù riêng nên xử lý khác nhau (§3).

---

## 2. Nguyên tắc cốt lõi

1. **Chunk theo ngữ nghĩa là chính**, size-chunk chỉ là lưới an toàn — giữ đúng hướng hiện tại (split theo heading trước, size chỉ xử lý chunk bất thường).
2. **Không cắt giữa câu / giữa bảng** — mọi thao tác cắt phải ở biên ngữ nghĩa.
3. **Khớp cửa sổ embedding** — kích thước chunk phải nằm trong 128-token window của model.
4. **Metadata giữ nguyên** — `section_path`, `model_id`, `edition_id`, `collection`, `source_url` phải có ở mọi mảnh (logic `apply_chunking` hiện đã đúng, giữ nguyên).
5. **Stable ID** vẫn gán sau cùng ở `split_cold_hot` (giữ nguyên).

---

## 3. Chiến lược đề xuất theo từng loại nội dung

### 3.1. Tham số đề xuất

| Tham số | Trước | **Đã áp dụng** | Lý do |
|---------|-------|----------------|-------|
| `max_len` | 1000/1500 (target/hard) | **400** | Đo thực tế: 128 token ≈ 400 chars tiếng Việt |
| Cách cắt | theo ký tự/dòng | **theo câu** | Cắt ở biên câu, không cắt giữa câu/từ |
| `overlap` | 100 chars | **câu cuối hoàn chỉnh** | Context liền mạch giữa 2 chunk kề |

> **Đo thực tế** (đã xác nhận): `MiniLM-L12-v2` có `max_seq_length=128`; 300 chars = 94 tokens, 500 chars = 150 tokens (>128 → truncate). Vector plateau ở ~500 chars → window hiệu dụng ≈ **400 chars**.

### 3.2. Prose / Mô tả sản phẩm (`chunkify_markdown` → `product_info`, brochure)

- Cắt theo **câu**: nhóm câu cho đến khi chạm `target`, cắt ở biên câu/đoạn.
- Overlap giữ nguyên **câu cuối hoàn chỉnh** của mảnh trước (không phải 100 ký tự cắt đôi câu).

### 3.3. Bảng markdown (specs brochure OCR)

- Giữ nguyên logic hiện tại: tách header `|...|` + separator `|---|`, lặp lại header ở mọi mảnh.
- Mỗi mảnh **3–5 dòng dữ liệu** (tùy độ dài mỗi dòng, tính để mảnh ≤ `target`).

### 3.4. Specs key-value (`model_specs.json`) — nguồn chính (312 chunk)

- Hiện: **1 section = 1 chunk** (dimension, powertrain, adas, exterior, interior, safety).
- Đề xuất: nhóm **2–4 cặp key:value** thành 1 chunk, **giữ section_path**. Chunk ngắn, sắc nét → retrieval chính xác hơn khi hỏi "VF9 dài bao nhiêu".
- Giữ `text_type=key_value` và `structured` nếu có.

### 3.5. Cách tính overlap (sửa bug hiện tại)

Thay vì `"\n".join(cur[-3:])[-overlap:]` (có thể cắt giữa câu), tìm **biên câu gần nhất** (`.\s`, `:\s`, `;\s`, hoặc `|` đối với bảng) trước ngưỡng overlap để lấy phần đuôi hoàn chỉnh.

---

## 4. Việc cần kiểm chứng trước khi áp dụng

1. **Đo thực tế cửa sổ embedding** của `paraphrase-multilingual-MiniLM-L12-v2`:
   - Embed một chuỗi dài dần (100→2000 chars), tìm điểm độ dài mà vector ngừng thay đổi → chính là max context thực tế theo ký tự.
   - Nếu max context thực tế lớn hơn ước lượng, có thể tăng `target` lên để giảm số chunk.
2. **Đo số chunk** sau khi áp dụng để dự báo chi phí lưu trữ Qdrant và thời gian ingest.

---

## 5. Ưu / nhược điểm

**Ưu điểm**
- Khớp window embedding → không mất thông tin cuối chunk.
- Chunk nhỏ hơn + sắc nét → retrieval chính xác hơn cho câu hỏi spec cụ thể.
- Tối ưu riêng từng loại nội dung → tận dụng tốt cấu trúc data có sẵn (bảng, key-value).

**Nhược điểm**
- Số chunk tăng mạnh (ước đoán 496 → 800–1200), tốn storage vector và thời gian ingest.
- Cần chạy lại pipeline (v1 hoặc đánh `v2`) và thường phải `--recreate` collection Qdrant vì ID/seq thay đổi.

---

## 6. Các phương án áp dụng

| Phương án | Mô tả | Khi nào chọn |
|-----------|-------|--------------|
| A. Sửa luôn v1 | Cập nhật `split_oversized_chunk` + tham số mặc định, chạy lại pipeline `v1` | Muốn cải thiện ngay, chấp nhận thay ID |
| B. Version v2 | Giữ v1 nguyên, tạo `v2` theo chiến lược mới | Muốn so sánh A/B, không phá dữ liệu cũ |
| C. Chỉ tài liệu | Viết lại §4 của `UC01_CLEAN_FORMAT_CHUNKING_RETRIEVER_LLM.md` cho khớp đề xuất, chưa đụng code | Chờ chốt tham số sau khi đo model |

---

## 7. File liên quan cần cập nhật khi áp dụng

- `scripts/clean_data/clean_to_jsonl.py` — `split_oversized_chunk`, `apply_chunking`, tham số mặc định trong `main()`.
- `data/DATA_PIPELINE_GUIDE.md` — bảng tham số `--target`/`--hard` (§2.2).
- `docs/UC01_CLEAN_FORMAT_CHUNKING_RETRIEVER_LLM.md` — §4 CHUNKING (target/hard mới, quy tắc theo loại).
- `docs/UC01_PRODUCT_INFORMATION.md` — nếu có nhắc kích thước chunk.
