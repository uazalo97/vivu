# Vivu Chatbot UI — Kế hoạch triển khai

> Mục tiêu: xây dựng giao diện chat tư vấn xe VinFast kết nối backend
> (branch `Trust-Foundation/Bao`). Tài liệu này là plan, chưa có code.
>
> ✅ **Đã chốt thiết kế:**
> - **Bố cục:** Landing page VinFast với nút mở chatbox (floating). Landing page tạm **để trắng** — chưa thiết kế chi tiết.
> - **Màu chủ đạo:** `#2C72C6` (xanh VF) + `#ffffff` (trắng)
> - **Font:** Mulish, cỡ chữ mặc định **16px**

---

## 1. Backend hiện tại — Contract API

FastAPI chạy port **8000**, không có CORS middleware.

### Endpoints

| Endpoint             | Method | Body → Response                                                                                         | Dùng để                                    |
| -------------------- | ------ | -------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `/api/chat`        | POST   | `{message, history}` → `{response, sources, needs_clarification, classify, decision, decision_log}` | Fallback khi SSE lỗi / không cần streaming |
| `/api/chat/stream` | POST   | `{message, history}` → **SSE**                                                                  | Chat chính                                   |
| `/api/logs`        | GET    | `?run_id=` → JSON                                                                                     | Debug                                         |
| `/api/logs/export` | GET    | JSONL download                                                                                           | Debug                                         |

### SSE event types (parse từ `data: ...\n\n`)

| Event                    | Content                                              | Frontend xử lý                         |
| ------------------------ | ---------------------------------------------------- | ---------------------------------------- |
| `decision`             | `"answer" \| "clarify" \| "out_of_scope" \| "refuse"` | Logic ẩn                                |
| `classify`             | `{specificity, entities}`                          | Logic ẩn                                |
| `tool_call`            | `{tool, success}`                                  | Hiện "🔧 đang tra cứu: get_price..."  |
| `token`                | text                                                 | Append vào bubble đang stream          |
| `answer` / `clarify` | text hoàn chỉnh                                    | Set nội dung cuối                      |
| `sources`              | `[{text, url, type, score}]` (tối đa 5, dedupe)  | Render chips nguồn                      |
| `done`                 | —                                                   | Push assistant vào history, reset state |

### Lưu ý contract

- **History** gửi lên: `[{role, content}]` — backend chỉ dùng **6 message gần nhất** (`history[-6:]`).
- **Flow `clarify`**: khi thiếu model/version → backend trả `clarify` → UI hiện câu hỏi lại, chờ user nhập tiếp để nối tiếp.
- **Nguồn**: `source_url` nếu là file path sẽ được backend map sang `https://shop.vinfastauto.com/...`, frontend không cần xử lý.
- **Không có CORS** → frontend dev phải dùng proxy hoặc thêm CORS vào backend.

---

## 2. Tech stack đề xuất

**Chọn: React + TypeScript + Vite + Tailwind CSS + Zustand + react-markdown**

| Tầng              | Chọn                                      | Lý do                                                                                 |
| ------------------ | ------------------------------------------ | -------------------------------------------------------------------------------------- |
| Framework          | React 18 + TypeScript                      | Quản lý state streaming (token dồn dần), hệ sinh thái UI lớn                    |
| Build/dev          | Vite                                       | HMR nhanh; proxy`/api → localhost:8000` giải quyết CORS khi dev                   |
| Giao tiếp backend | Fetch + đọc`response.body.getReader()` | SSE qua**POST** nên không dùng được EventSource; tự parse `data:` lines |
| UI                 | Tailwind CSS                               | Nhẹ, tùy biến, kiểm soát được; theme theo màu VinFast                         |
| Markdown           | react-markdown + remark-gfm                | Backend trả text thuần — hỗ trợ bảng so sánh, bullet                            |
| State              | Zustand                                    | Nhẹ, phù hợp flow chat (messages ↔ streaming ↔ clarify ↔ tools)                  |
| Test               | Vitest + React Testing Library             | Cùng hệ Vite                                                                         |

### Design tokens (đã chốt)

| Token | Giá trị | Ghi chú |
| --- | --- | --- |
| `color-primary` | `#2C72C6` | Xanh chủ đạo (nút, header, accent) |
| `color-bg` | `#ffffff` | Nền trắng |
| `font-family` | Mulish | Nhúng Google Fonts / self-host |
| `font-size-base` | `16px` | Cỡ chữ body mặc định |

**Bố cục ứng dụng (MVP hiện tại):**
- Landing page VinFast để **trắng** tạm thời (chưa chốt thiết kế → chưa làm).
- Nút mở chatbox nổi (floating) → bật widget chat.

**Ghi chú giữ nhất quán sau này:**
- Chỉ dùng bảng màu `#2C72C6` + `#ffffff` (+ biến thể light/dark của `#2C72C6` cho hover/active/shadow).
- Font Mulish cho cả heading lẫn body, base `16px`; size nhỏ (caption, sources) là scale giảm từ 16px, không đổi font khác.
- Khi thiết kế landing page sau, nút mở chat giữ style primary `#2C72C6`.

### Phương án thay thế (đã cân nhắc)

- **Vanilla HTML/JS + Tailwind** (kiểu `app/static/index.html` backend đang có) — đủ MVP nhưng khó bảo trì khi thêm clarify, sources, suggestion chips.
- **Next.js** — thừa so với nhu cầu; backend đã là FastAPI thuần, React SPA là đủ.
- **Ant Design / shadcn/ui** — có component sẵn nhưng nặng hơn; hiện tại Tailwind thuần là cân bằng tốt.

---

## 3. Kiến trúc frontend

```
frontend/
├── vite.config.ts            # proxy /api → http://localhost:8000
├── src/
│   ├── api/
│   │   ├── types.ts          # Event, Source, ChatRequest/Response
│   │   └── chat.ts           # chatStream(): đọc SSE, callback từng event
│   ├── store/chat.ts         # Zustand: messages, isStreaming, toolCalls, sources
│   ├── components/
│   │   ├── ChatWindow.tsx    # container + auto-scroll
│   │   ├── MessageBubble.tsx # markdown, sources, clarify
│   │   ├── ToolsIndicator.tsx# spinner "đang tra cứu: ..."
│   │   ├── SourceChips.tsx   # liên kết nguồn
│   │   ├── SuggestionChips.tsx # gợi ý câu hỏi
│   │   └── InputBar.tsx      # textarea, Enter gửi
│   └── App.tsx
```

### Luồng stream (lõi nhất)

```
user gửi → POST /api/chat/stream → nhận event:
  decision/classify  → logic ẩn
  tool_call          → hiện "🔧 đang tra cứu..."
  token              → append vào bubble đang stream
  answer/clarify     → set nội dung cuối
  sources            → lưu, render chips dưới bubble
  done               → push {role:'assistant'} vào history, reset state
```

Yêu cầu kỹ thuật:

- **AbortController** để hỗ trợ "dừng stream".
- **Bắt lỗi network** → message thân thiện + hotline 1900 23 23 89, tùy chọn fallback `/api/chat`.

---

## 4. Kế hoạch triển khai từng bước

### Phase 0 — Chuẩn bị (~0.5 ngày)

- Scaffold `frontend/` bằng Vite (React + TS + Tailwind).
- Cấu hình `vite.config.ts` proxy `/api → http://localhost:8000`.
- Cài: zustand, react-markdown, remark-gfm.

### Phase 1 — Core chat (~1–1.5 ngày)

- `types.ts` + `chatStream()` helper (đọc SSE, parse event, callback).
- ChatWindow + MessageBubble + InputBar.
- Xử lý: token streaming, sources, tool indicator, done.

### Phase 2 — Flow thông minh (~1 ngày)

- Flow `clarify`: backend hỏi lại → bubble chờ, câu trả lời sau tự nối tiếp.
- Suggestion chips: giá VF7, so sánh VF8 vs VF9, khuyến mãi,...
- Lịch sử chat trong phiên (gửi 6 message gần nhất lên).

### Phase 3 — UX / Polish (~1 ngày)

- Markdown render (bảng so sánh thông số).
- Theme VinFast (xanh VF, gradient), dark/light.
- Typing indicator, auto-scroll, loading states.
- Responsive mobile.

### Phase 4 — Cứng hóa (~0.5–1 ngày)

- AbortController (dừng stream), retry, fallback `/api/chat`.
- Error handling backend down.
- Vitest cho `chatStream()` parser (unit test SSE parsing).

### Phase 5 — Tích hợp & eval (~0.5 ngày)

- Test thật với backend chạy :8000, kiểm tra `decision`/`clarify` trên UI.
- Nếu không dùng proxy → thêm CORS middleware vào `app/main.py` (đụng backend, cần confirm).

---

## 5. Điểm cần chốt trước khi code

1. **React hay Vanilla?** — đề xuất React; chỉ chọn Vanilla nếu cần MVP 1 file gấp.
2. **CORS**: proxy Vite (không đụng backend) — recommended; hoặc thêm CORS vào backend.
3. **UI library**: Tailwind thuần (recommended) vs Ant Design/shadcn.
4. **Branch**: làm trên `UI_chatbot`, code trong `frontend/`.

---

## 6. Rủi ro & giả định

- Backend phải đang chạy mới test được luồng thật; cần cloud DB (Neon + Qdrant) + API keys theo `GUIDE.md`.
- Nếu backend thay đổi event types → `types.ts` cần cập nhật kèm.
- TTFT (time-to-first-token) có thể lâu do agent loop LLM + retrieval → UI cần trạng thái "đang suy nghĩ" tốt.
