# Retriever — Hybrid search (dense + BM25) + tool fast-path

Retriever hoàn chỉnh cho UC-01, chạy hoàn toàn bằng OpenRouter API.

## Luồng xử lý

```
Query: "VF 9 Plus giá bao nhiêu và có ADAS gì?"
   │
   ▼
┌────────────────────────────────────────────────────┐
│ 1. Entity detection (regex)          "VF 9 Plus"   │
│                                       → VF9/Plus   │
│ 2. Intent → collection hoặc tool                   │
│    • Bảo dưỡng          → get_maintenance_info     │  tool fast-path
│    • Danh mục dòng xe   → get_model_list           │  (không tra vector)
│    • Thông số/sản phẩm/chính sách → dense+sparse   │
│ 3. Vector search (các intent còn lại)              │
│    Dense  (text-embedding) + filter model/edition  │
│    Sparse (BM25 local)                             │
│ 4. RRF fusion — gộp dense + sparse                 │
│ 5. Join text từ vector/*.jsonl (payload Qdrant     │
│    không lưu text)                                 │
│ 6. Giá Postgres qua TOOL REGISTRY (get_price)      │  deterministic fast-path
│ 7. Brochure links từ manifest                      │
└────────────────────────────────────────────────────┘
```

## Cách dùng

```bash
# Hybrid đầy đủ (dense + sparse + RRF)
python backend/retriever/hybrid_retriever.py "VF 9 Plus giá bao nhiêu và có ADAS gì"

# Sinh câu trả lời cuối bằng LLM (C5) — thêm --answer
python backend/retriever/hybrid_retriever.py "VF 9 Plus giá bao nhiêu" --answer

# Tool fast-path — không cần Qdrant
python backend/retriever/hybrid_retriever.py "bảo dưỡng xe"
python backend/retriever/hybrid_retriever.py "vinfast có mấy loại xe"

# Tùy chọn
python backend/retriever/hybrid_retriever.py "bảo hành pin" --top-k 5
python backend/retriever/hybrid_retriever.py "bảo hành pin" --no-sparse   # chỉ dense
python backend/retriever/hybrid_retriever.py "trễ hạn phí" --no-dense    # chỉ sparse
```

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `--version` | `v1` | Version dữ liệu clean |
| `--top-k` | `3` | Số chunk cuối trả về |
| `--per-collection` | `10` | Kết quả mỗi nguồn trước fusion |
| `--no-sparse` / `--no-dense` | — | Tắt bước tương ứng |
| `--answer` | off | Gọi LLM sinh câu trả lời cuối (C5) |
| `--chat-model` | từ `.env` | Chat model (`OPENROUTER_CHAT_MODEL`) |

## LLM response (`--answer`)

Retrieve xong → ghép prompt **system + user** → gọi **OpenRouter chat completions**.

- **System prompt**: vai trò Trợ lý Vivu, tiếng Việt, tự nhiên/chi tiết/đầy đủ, giá chỉ dùng
  số Postgres (thiếu → nói "chưa có giá hiện hành"), không bịa số liệu, kèm nguồn, không nhắc
  'context'/'Postgres'/quy trình nội bộ, luôn xưng hô "Trợ lý Vivu".
- **User message** ghép động theo kết quả retrieve: chunks (THÔNG TIN TỪ CƠ SỞ TRI THỨC),
  lịch bảo dưỡng (THÔNG TIN LỊCH BẢO DƯỠNG), danh mục xe (DANH MỤC DÒNG XE VINFAST),
  giá (GIÁ HIỆN HÀNH), brochure (BROCHURE THAM KHẢO), rồi câu hỏi user ở cuối.
- `chat_completion()` trong `backend/lib/openrouter.py` (max_tokens 4096 — reasoning ngốn token;
  fallback `reasoning` nếu `content` None).

## Tool Registry

Các lookup được đăng ký trong `TOOL_REGISTRY` (deterministic fast-path, không để LLM tự gọi):

| Tool | Khi nào gọi | Trả về |
|------|-------------|--------|
| `get_price` | mọi câu hỏi detect được model/edition | giá niêm yết + ưu đãi từ Postgres |
| `get_maintenance_info` | intent bảo dưỡng | lịch bảo dưỡng chung + link chính thức |
| `get_model_list` | hỏi danh mục dòng xe | số lượng + danh sách dòng xe |

Cấu trúc registry sẵn sàng để sau này expose cho **LLM function-calling** (tool call)
mà không cần đổi kiến trúc.

## Dependencies

- `backend/lib/openrouter.py` — helper dùng chung: `embed_text`, `embed_texts`, `rerank` (retry rate-limit).
- `data/clean/<version>/sparse_index.json` — vocab + idf (do `sparse_ingest.py` tạo).
- Qdrant: 4 dense collections + `sparse` collection.
- PostgreSQL: bảng `price_list`.

> ⚠️ Payload Qdrant **không lưu text** — retriever join text từ `data/clean/<version>/vector/*.jsonl`
> theo id (Qdrant point id = UUIDv5 của chunk id).
