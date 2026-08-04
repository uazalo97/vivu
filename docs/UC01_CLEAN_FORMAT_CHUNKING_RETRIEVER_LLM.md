# UC-01 — Clean / Format / Chunking / Retriever / LLM

> Tài liệu tham khảo chi tiết phần đầu pipeline: làm sạch, định dạng, chunking hóa dữ liệu, và cách retriever + LLM sử dụng.

---

## 1. Tổng quan luồng

```text
RAW (data/raw/*.txt — crawl output)
        │
        ▼
┌─────────────────┐
│     CLEAN       │  ← bỏ noise, HTML comment, PDF cách chữ, giá tiền
└─────────────────┘
        │
        ▼
┌─────────────────┐
│     FORMAT      │  ← schema JSONL cố định, model_id/edition_id, metadata
└─────────────────┘
        │
        ▼
┌─────────────────┐
│    CHUNKING     │  ← theo heading, cắt theo câu, max_len 400, overlap câu cuối
└─────────────────┘
        │
        ▼
┌─────────────────┐
│    RETRIEVER    │  ← dense (OpenRouter embed) + sparse (BM25) → RRF → rerank
└─────────────────┘
        │
        ▼
┌─────────────────┐
│      LLM        │  ← ghép context + giá (Postgres, tool) + link-only (brochure)
└─────────────────┘
```

---

## 2. CLEAN — Làm sạch gì?

### 2.1. Input

- `data/raw/*.txt` — crawl output của `scripts/crawl.py` (49 file hiện tại).
- `data/raw/link_brochure.md` — URL brochure PDF (link-only).

Mỗi file có header chuẩn:

```text
# Nguồn: <url>     # Crawl lúc: <timestamp>     # Loại: pdf|html
================================================================================
<body content>
```

### 2.2. Các bước clean

| # | Việc | Ví dụ | Lý do |
|---|---|---|---|
| C1 | Parse header `# Nguồn/# Loại` | URL, timestamp → metadata | Không nhúng header vào text |
| C2 | Bỏ HTML tags + HTML comments | `<div>`, `[if IE 9]> <![endif]` | Chỉ giữ text có ý nghĩa |
| C3 | Bỏ PUA/Unicode lạ | `` (WingDings bullet) | Ký tự vô nghĩa từ PDF |
| C4 | Bỏ navigation noise | breadcrumb, "Đăng nhập/Đăng ký", "Chọn địa chỉ nhận hàng", phone, email | UI elements không phải nội dung |
| C5 | Dedupe dòng lặp (≥3 lần) | tên dealer lặp trong sidebar | Nav/sidebar lặp lại |
| C6 | De-space PDF (theo dòng) | `"T h ô n g"` → `"Thông"` | Chỉ dòng Mục lục bị pdftotext cách chữ |
| C7 | Chuẩn hóa số | `5.119 x 2.254` → `5119 × 2254` | Dễ lookup, tránh nhầm decimal |
| C8 | Tách giá khỏi text vector | `613.700.000 VNĐ` → bỏ | Giá hay đổi, không để trong embedding |
| C9 | Gộp fragment ngắn | `"VF 9"`, `"Lựa chọn"` → gộp | Tránh chunk vô nghĩa |

### 2.3. Quy tắc drop giá

Chỉ drop paragraph khi **đồng thời**:

- Chứa từ khóa giá: `giá bán`, `giá niêm yết`, `giá ưu đãi`, `triệu đồng`, `vnđ`, `đặt cọc`, `lăn bánh`...
- VÀ có số tiền kèm đơn vị: `1.280.600.000 VNĐ`, `188 triệu`.

Không drop số kỹ thuật như `626 km`, `123 kWh`, `402 hp` vì chúng không kèm đơn vị tiền.
`strip_price_spans` xử lý thêm trường hợp số tiền tách dòng khỏi `VNĐ` (VD `613.700.000\n\nVNĐ\*`).

### 2.4. Trích giá (chỉ từ nguồn chính thống)

| Nguồn | Có trích giá không |
|---|---|
| `vinfastauto.com`, `shop.vinfastauto.com` — page `dat-coc-*` | ✅ → Postgres |
| PDF, web article, dealer page | ❌ Không |

Edition gán theo thứ tự giá tăng dần (`MODEL_EDITIONS`): block rẻ nhất = edition đầu (Eco/Base).

---

## 3. FORMAT — Định dạng thế nào?

### 3.1. Schema mỗi chunk (JSONL)

```json
{
  "id": "vivu_specs:vf9:all:thong_so_ky_thuat:1",
  "collection": "vivu_specs",
  "vector_version": "v1",
  "model_id": "VF9",
  "edition_id": null,
  "category": "thong_so_ky_thuat",
  "section_path": ["thong_so_ky_thuat", "Hiệu suất và động cơ"],
  "text": "VF8 Plus có công suất tối đa 300 kW (402 hp), mô-men xoắn cực đại 620 Nm...",
  "text_type": "prose",
  "structured": {},
  "language": "vi",
  "tags": ["thong_soky_thuat", "vf9"],
  "confidence": 0.8,
  "source_file": "data/raw/so-sanh-vf8-eco-va-vf8-plus-p56_....txt",
  "source_url": "https://www.vinfastmiennam.vn/so-sanh-vf8-eco-va-vf8-plus-p56",
  "source_type": "raw_html",
  "fetched_at": "2026-07-30T22:56:26",
  "ingested_at": "..."
}
```

### 3.2. Các `text_type`

| Type | Khi nào dùng |
|---|---|
| `prose` | Đoạn văn mô tả |
| `table` | Bảng Markdown có `|` và `---` |
| `list` | Danh sách item `-` hoặc `1. 2. 3.` |
| `qa_pair` | FAQ 1 câu hỏi + 1 câu trả lời |

### 3.3. Chuẩn hóa khóa

- `model_id`: `VF2`, `VF3`, `VF5`, `VF6`, `VF7`, `VF8`, `VF9`, `VFMPV7`, `VFE34`...
- `edition_id`: `Eco`, `Plus`, `PlusCaptain`, `TieuChuan`, `NangCao`, `CaoCap`.
- `model_id` infer từ tên file raw (vd `vinfast-vf9-*` → `VF9`).

### 3.4. Phân loại collection

| Collection | Nguồn raw | Mục đích |
|---|---|---|
| `vivu_specs` | `so-sanh-*`, `bang-doi-chieu-*`, `thong-so-ky-thuat-*` | Bảng so sánh thông số, ADAS |
| `vivu_product_info` | `dat-coc-*`, `san-pham_*`, `product_*`, tin tức, dealer | Mô tả, tính năng, màu sắc |
| `vivu_policy` | `chinh-sach-bao-hanh`, `dich-vu-pin/sua-chua/cuu-ho`, PDF sổ bảo hành | Chính sách, điều khoản bảo hành |
| `vivu_maintenance` | `dich-vu-bao-duong-*` | Lịch trình & hạng mục bảo dưỡng |

> Không còn `vivu_faq` — nguồn raw không có FAQ.

---

## 4. CHUNKING — Chia nhỏ thế nào?

### 4.1. Chiến lược

- **Tầng 1 — theo heading** (`#`, `##`, `###`): 1 section heading = 1 chunk.
- **Tầng 2 — cắt theo câu** khi chunk > `max_len` (400 chars):
  - Gom câu tới khi thêm câu tiếp vượt 400 → cắt ở **biên câu**.
  - Specs key:value không có dấu câu → cắt ở `; ` (giữ nguyên cặp `key: value`).
  - **Overlap** = câu cuối hoàn chỉnh của chunk trước làm mở đầu chunk sau.
  - Bảng markdown → lặp header row ở mỗi mảnh.
- **max_len = 400** — hiện giữ từ bản đầu (khớp cửa sổ MiniLM cũ). Model mới `text-embedding-3-small`
  có window 8191 token (rộng hơn nhiều), nên **có thể tăng max-len lên 1000-2000** để ít chunk hơn,
  mỗi chunk mang nhiều ngữ nghĩa. Muốn đổi: chạy lại `clean_to_jsonl.py --max-len <n>` + re-ingest.

### 4.2. Ví dụ

Section prose 750 chars, các câu dài 150/120/180/130/170:

```text
buf=""        +"A."(150) → 150   ✓
              +"B."(120) → 270   ✓
              +"C."(180) → 450 > 400 → emit "A. B."  ; buf = "B." + "C."
              +"D."(130) → 430 > 400 → emit "B. C."  ; buf = "C." + "D."
              +"E."(170) → 480 > 400 → emit "C. D."  ; buf = "D." + "E."
  end → emit "D. E."

Kết quả: ["A. B.", "B. C.", "C. D.", "D. E."] — mỗi chunk ≤400, overlap 1 câu.
```

### 4.3. Stable ID

```text
<collection>:<model_id_lower>:<edition_id_lower>:<section_slug>:<seq>
```

---

## 5. RETRIEVER — Luồng xử lý câu hỏi

Retriever nhận câu hỏi user, phân tích intent rồi quyết định **trả lời bằng tool (fast-path)**
hay **đi tìm kiếm vector**. Kết quả luôn là một dict gồm: model/edition detect được, danh sách
collection, chunks (nếu có), giá, lịch bảo dưỡng, danh mục xe, brochure — để bước LLM ghép thành prompt.

### 5.1. Input

Câu hỏi user, ví dụ: "VF 9 Plus giá bao nhiêu, có ADAS gì?"

### 5.2. Các bước xử lý

1. **Entity detection** — nhận diện model/edition từ câu hỏi bằng regex.
   VD: "VF 9 Plus" → model VF9, edition Plus.
2. **Intent detection** — xác định chủ đề theo keyword:
   - Thông số (kích thước, công suất, pin, ADAS…) → tìm trên `vivu_specs`
   - Mô tả/tính năng/màu/thiết kế → `vivu_product_info`
   - Chính sách/bảo hành/phí thuê pin → `vivu_policy`
   - Bảo dưỡng → **tool fast-path** (bước 3)
   - Hỏi danh mục dòng xe → **tool fast-path** (bước 3)
   - Không khớp intent nào → tìm trên tất cả collection.
3. **Tool fast-path** — hai loại câu hỏi KHÔNG tra vector, trả lời trực tiếp bằng tool:
   - Bảo dưỡng → tool `get_maintenance_info`: lịch bảo dưỡng chung + link trang chính thức.
   - Danh mục dòng xe → tool `get_model_list`: danh sách + số lượng dòng xe trong KB.
   Lý do tách fast-path: dữ liệu vector của 2 chủ đề này dễ bị LLM tóm tắt/liệt kê sai
   (lịch bảo dưỡng theo từng xe, danh mục xe lấy từ trang bên thứ ba).
4. **Vector search** — cho các câu hỏi còn lại:
   - **Dense**: nhúng câu hỏi qua OpenRouter (text-embedding) rồi tìm vector trên các
     collection ứng với intent, lọc theo model/edition nếu detect được.
   - **Sparse**: tokenize + BM25 trên collection sparse (chạy local, không tốn API).
   - **RRF fusion**: gộp điểm 2 nguồn (reciprocal rank fusion) → chọn top-k chunk.
   - (Bước rerank đã bỏ khỏi luồng.)
   - Text lấy từ `data/clean/<version>/vector/*.jsonl` theo id — payload Qdrant không lưu text.
5. **Giá** — nếu detect được model → gọi tool `get_price` lấy từ Postgres.
6. **Brochure** — link brochure theo model detect; không detect được thì trả toàn bộ.

### 5.3. Tool Registry

Ba tool đăng ký trong `TOOL_REGISTRY`, gọi theo kiểu **deterministic fast-path** (detect
intent/model bằng regex rồi gọi handler trực tiếp — không để LLM tự quyết định gọi tool):

| Tool | Tham số | Trả về | Khi nào gọi |
|------|---------|--------|-------------|
| `get_price` | model, edition | giá niêm yết + ưu đãi + nguồn | mọi câu hỏi detect được model |
| `get_maintenance_info` | model (tùy chọn) | lịch bảo dưỡng chung + link chính thức | intent bảo dưỡng |
| `get_model_list` | — | số lượng + danh sách dòng xe | hỏi danh mục xe |

Cấu trúc registry sẵn sàng bật **LLM function-calling** (tool call) sau này mà không phải
đổi kiến trúc.

### 5.4. Tool get_price — giá từ Postgres

Khi detect được model/edition, retriever gọi `get_price` đọc bảng `price_list` (Postgres):
chỉ lấy bản giá mới nhất còn hiệu lực (valid_to trống hoặc từ hôm nay trở đi), ưu tiên theo
ngày áp dụng gần nhất. Kết quả được gắn kèm model/edition để LLM biết giá thuộc đúng phiên
bản nào, tránh suy diễn sang phiên bản khác.

---

## 6. LLM — Ghép prompt và trả lời

### 6.1. Cấu trúc prompt

Prompt gồm 2 phần: **system** (cố định) và **user** (ghép động theo kết quả retrieve).

**System prompt** — vai trò và quy tắc ứng xử:
- Vai trò: Trợ lý Vivu, tư vấn xe VinFast, trả lời bằng tiếng Việt.
- Phong cách: tự nhiên, chi tiết, đầy đủ.
- Giá: chỉ dùng số được cung cấp từ Postgres; không có giá thì nói rõ "chưa có giá hiện hành".
- Không bịa số liệu, thông số, tính năng không có trong context.
- Kèm nguồn (source_url) nếu có.
- Không nhắc tới 'context', 'Postgres' hay quá trình nội bộ.
- Luôn xưng hô là "Trợ lý Vivu".

**User message** — các phần ghép theo thứ tự (phần không có thì bỏ qua):
1. **THÔNG TIN TỪ CƠ SỞ TRI THỨC** — từng chunk: [collection | model | section] + nội dung + (nguồn: url).
2. **THÔNG TIN LỊCH BẢO DƯỠNG** — khi intent bảo dưỡng: tóm tắt lịch chung + link trang chính thức.
3. **DANH MỤC DÒNG XE VINFAST** — khi hỏi danh mục: số lượng + danh sách dòng xe.
4. **GIÁ HIỆN HÀNH cho model edition** — niêm yết, ưu đãi (tên chương trình), lưu ý giá chỉ áp dụng cho đúng phiên bản.
5. **BROCHURE THAM KHẢO** — tối đa 3 link.
6. **Câu hỏi** của user đặt ở cuối.
- Nếu không có chunk cũng không có tool nào khớp: ghi rõ "(Không tìm thấy thông tin liên
  quan trong cơ sở tri thức.)" để LLM thừa nhận thay vì bịa.

### 6.2. Quy tắc response theo loại câu hỏi

- **Giá**: đọc số từ Postgres, nói rõ phiên bản giá áp dụng, kèm nguồn.
- **Bảo dưỡng**: trả lời lịch bảo dưỡng chung + link chính thức, không đi sâu theo từng xe.
- **Danh mục xe**: liệt kê đầy đủ các dòng xe kèm số lượng.
- **Không đủ context**: thừa nhận chưa có thông tin và gợi ý link nguồn/brochure.
- Luôn kèm nguồn nếu có; không nhắc quy trình nội bộ.

### 6.3. Ví dụ output mong đợi

**User:** "VF 9 Plus giá bao nhiêu?"

**LLM:**
> VF 9 Plus giá niêm yết 1.529.000.000 VNĐ, giá ưu đãi hiện hành 1.452.550.000 VNĐ
> (chương trình Ưu đãi đặt cọc 2026). Giá đã bao gồm VAT. Tải brochure tham khảo: [link].

**User:** "bảo dưỡng xe"

**LLM:**
> Bảo dưỡng định kỳ là điều kiện cần để được hưởng bảo hành; lịch tính theo quãng đường
> (km) hoặc thời gian theo tháng, tùy điều kiện nào đến trước, hạng mục cụ thể theo từng
> dòng xe. Tra cứu lịch bảo dưỡng chi tiết: https://vinfastauto.com/vn_vi/dich-vu-bao-duong-oto

**User:** "VinFast có mấy loại xe?"

**LLM:**
> VinFast có 9 dòng xe: VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 9, VF e34, VF MPV 7.

---

## 7. Tóm tắt các quy tắc bắt buộc

1. **Nguồn duy nhất**: `data/raw/`. Không dùng `data/01..08/`, `model_specs.json`.
2. **Clean**: text vector sạch, không HTML comment/PUA/nav noise, không giá.
3. **Giá**: chỉ trích từ trang chính thống `dat-coc-*`, nằm ở Postgres.
4. **Chunking**: theo heading + câu, max_len 400, overlap câu cuối, giữ nguyên bảng.
5. **Retriever**: bảo dưỡng & danh mục xe → tool fast-path (không tra vector); còn lại embed
   query, search collection phù hợp, filter model/edition, join text theo id.
6. **LLM**: ghép context + giá Postgres + link brochure + tool output (nếu có); không bịa số liệu.

---

## 8. Tham khảo

- `docs/UC01_PRODUCT_INFORMATION.md` — kiến trúc tổng thể.
- `data/DATA_PIPELINE_GUIDE.md` — chạy clean pipeline.
- `scripts/clean_data/clean_to_jsonl.py` — code clean/format/chunking.
- `scripts/clean_data/split_cold_hot.py` — code split cold/hot.
- `docs/CHUNKING_PROPOSAL.md` — quyết định chunking (đã áp dụng).
