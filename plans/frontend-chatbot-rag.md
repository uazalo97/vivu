# Kế hoạch: Giao diện Chatbot Frontend cho RAG UC-01

## Bối cảnh

Dự án `vivu` đã có pipeline RAG cho VinFast:
- Dữ liệu clean → ingest vào Qdrant + PostgreSQL.
- `scripts/retriever/hybrid_retriever.py` thực hiện dense + sparse + RRF để lấy context và giá.
- Hiện chưa có backend API nào cung cấp kết quả cho frontend.
- Chưa có thư mục `frontend/`.

## Mục tiêu

Xây dựng một giao diện chatbot đầy đủ cho phần RAG, cho phép người dùng:
1. Nhập câu hỏi tiếng Việt về xe VinFast (giá, thông số, màu sắc, chính sách...).
2. Nhận câu trả lời được LLM tổng hợp từ context RAG + giá PostgreSQL.
3. Xem nguồn tài liệu (sources) đã dùng để trả lời.
4. Trải nghiệm streaming response, typing indicator, responsive, light/dark mode.

## Phương án được chọn: FastAPI backend + Vanilla HTML/JS frontend

### Lý do

- **Backend FastAPI**: Khớp với hệ sinh thái Python hiện tại, dễ gọi `hybrid_retriever.py`, cung cấp endpoint `/api/chat` với SSE streaming.
- **Frontend vanilla HTML/JS + Tailwind CDN**: Không cần build step, Node.js hay cấu hình phức tạp. Phù hợp prototype và dễ chạy local cùng Docker DB.

### Các phương án khác đã xem xét

| Phương án | Ưu | Nhược | Lý do không chọn |
|---|---|---|---|
| React + Vite | Component rõ ràng, hot reload | Cần Node.js, build step | Dự án chưa có JS toolchain, làm prototype nặng |
| Next.js | SEO, full-stack | Quá nặng cho chatbot nội bộ | Không cần SSR/Routing |
| Chỉ frontend mock API | Nhanh demo | Không kết nối RAG thật | Không đáp ứng yêu cầu “cho phần RAG” |

## Kiến trúc

```text
frontend/
├── index.html          # Giao diện chính
├── styles.css          # Custom CSS bổ sung cho chat, animations
└── app.js              # Logic chat, gọi API, render messages/sources
backend/
├── api.py              # FastAPI app: /api/chat, /api/health, /api/suggestions
├── rag_engine.py       # Wrapper gọi retriever + build prompt + stream LLM
└── requirements.txt    # Thư viện bổ sung cho backend
```

Backend cũng sẽ refactor nhẹ `hybrid_retriever.py` để export các hàm `detect_entities`, `select_collections`, `retrieve_context`, `lookup_price` thay vì chỉ chạy CLI.

## Luồng dữ liệu

```text
User query
  → POST /api/chat (hoặc SSE /api/chat/stream)
  → FastAPI nhận query
  → detect_entities + select_collections
  → Qdrant dense + sparse + RRF
  → PostgreSQL lookup giá
  → Build prompt RAG (context + price + brochure links)
  → Stream LLM response về frontend
  → Frontend hiển thị message + expandable sources
```

## Thiết kế UI/UX

### Layout

- **Header**: Logo VinFast-style, toggle dark mode, tiêu đề "Trợ lý VinFast".
- **Khu vực chính**:
  - Sidebar trái (desktop): 5 câu hỏi gợi ý ("VF 9 Plus giá bao nhiêu?", "VF 8 có màu gì?", ...).
  - Chat area giữa: danh sách tin nhắn (user bên phải, bot bên trái).
  - Input sticky bottom: textarea + nút gửi + nút xóa cuộc trò chuyện.
- **Sources**: Mỗi câu trả lời bot có nút "Xem nguồn" mở accordion hiển thị top chunks, giá Postgres, link brochure.

### Visual

- Tailwind CDN, custom CSS cho chat bubbles, typing dots, markdown-like formatting.
- Màu chủ đạo: xanh lá/xanh dương hiện đại (theo hướng VinFast), hỗ trợ dark mode qua class `dark`.
- Responsive: mobile ≤768px ẩn sidebar, chuyển thành bottom sheet hoặc chip suggestions.

### Interactions

- `Enter` gửi tin nhắn, `Shift+Enter` xuống dòng.
- Auto-scroll xuống tin nhắn mới.
- Loading state: typing indicator 3 chấm.
- Error state: thông báo lỗi khi API fail.

## Backend API Spec

### `POST /api/chat/stream`

Request:
```json
{ "message": "VF 9 Plus giá bao nhiêu?", "history": [] }
```

Response: Server-Sent Events (SSE)
```text
event: sources
data: {"chunks": [...], "price": {...}, "brochures": [...]}

event: delta
data: {"content": "VF 9 Plus hiện có giá..."}

event: done
data: {}
```

### `GET /api/health`

Trả về trạng thái Qdrant + Postgres + LLM config.

### `GET /api/suggestions`

Trả về danh sách câu hỏi gợi ý.

## LLM

Dùng Google Gemini (Gemini 2.5 Flash) vì dự án đã có hướng dùng Gemini trong skill design. Cấu hình qua biến môi trường `GEMINI_API_KEY`. Nếu không có key, backend trả về context thô + prompt placeholder để demo giao diện.

## Các file sẽ tạo/sửa

### Tạo mới

1. `backend/api.py`
2. `backend/rag_engine.py`
3. `backend/requirements.txt`
4. `frontend/index.html`
5. `frontend/styles.css`
6. `frontend/app.js`
7. `frontend/README.md`

### Sửa đổi nhẹ

1. `scripts/retriever/hybrid_retriever.py`: tách thành các hàm reusable (`detect_entities`, `select_collections`, `retrieve_context`, `lookup_price`) để backend import.
2. `requirements.txt` gốc: thêm `fastapi`, `uvicorn`, `google-genai`.

## Cách chạy

```bash
# 1. Cài thêm thư viện backend
pip install -r backend/requirements.txt

# 2. Khởi động Qdrant + Postgres (nếu chưa chạy)
docker compose up -d

# 3. Chạy backend
python backend/api.py

# 4. Mở frontend
# Truy cập http://localhost:8000 hoặc mở frontend/index.html qua live-server
```

## Kiểm thử

1. Backend health check: `curl http://localhost:8000/api/health`.
2. Chat cơ bản: gửi "VF 9 Plus giá bao nhiêu" và kiểm tra response có sources + giá.
3. Frontend: kiểm tra responsive, dark mode, sources accordion, error handling.

## Lưu ý

- Nếu `GEMINI_API_KEY` chưa có sẵn, backend vẫn chạy và trả về context thô để demo UI.
- Giá và thông số luôn lấy từ Qdrant/Postgres, không hard-code trong frontend.
- Frontend không chứa secret key, tất cả LLM call đều qua backend.
