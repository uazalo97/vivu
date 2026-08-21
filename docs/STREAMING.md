# True Streaming — Tài liệu Chi Tiết

Từ nhánh `feature/admin`, chat stream **từng token thật** (như ChatGPT), không còn "hiện cả cục" sau khi đợi LLM xong.

---

## 1. Flow tổng quan

```
POST /api/chat/stream (SSE)
  └─ app/api/chat.py::chat_stream → StreamingResponse(generate())
       └─ agent.run_stream(query, history, ctx)
            ├─ classify  → event decision + classify
            ├─ call_tools → event tool_call + cache
            ├─ generate  → OPENAI stream=True
            │     └─ stream_chat_with_fallback → get_writer() {"type":"token", content:…}
            │           └─ (graph custom stream_mode) → queue → forward NGAY
            ├─ validate  → (nhanh, không LLM)
            ├─ respond   → sources + done
            └─ finally: _persist() background, không chặn đóng SSE
```

---

## 2. Backend — từng thành phần

### 2.1 `app/agent/llm.py` (đã chuyển sang OpenAI thuần)

- `get_llm()` → `AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)` (trước là deepinfra).
- Token limits: `OUTPUT_MAX_TOKENS=1024`, `TOOL_CALL_MAX_TOKENS=512`, `USER_INPUT_MAX_TOKENS=4000`, `INPUT_MAX_TOKENS=8000` (fallback `getattr`).
- `llm_extra_kwargs(model)` fallback — gpt-* sẽ 400 nếu gửi `reasoning`.
- `_stream_chat(llm, model, messages, writer, **kw)`:
  - `llm.chat.completions.create(stream=True)`
  - Mỗi `delta.content` → gom `word_buffer`, khi gặp ranh giới từ (space/newline/tab) → `writer({"type":"token","content": <đến hết từ>})`
  - Cuối câu flush phần còn lại.
  - Lỗi sau khi đã stream token → `PartialStreamError` (KHÔNG fallback nữa, tránh duplicate).
- `stream_chat_with_fallback(llm, messages, writer=None, **kw)`:
  - Chain `[llm_model, llm_fallback_model]`; thử model chính, lỗi trước token đầu → thử fallback; trả `(content, tool_calls, model_used)`.
  - **Yêu cầu** `settings.llm_fallback_model` — thiếu sẽ `AttributeError` → bot "Xin lỗi..." (đã sửa ở `app/config.py`).

### 2.2 `app/agent/nodes/generate.py`

```python
new_response, _, _ = await stream_chat_with_fallback(llm, messages, max_tokens=OUTPUT_MAX_TOKENS)
```
- `get_writer()` (LangGraph) tự lấy writer của custom stream trong node; nếu không có writer → vẫn accumulate full text làm fallback.
- Không còn `await llm.chat.completions.create()` không stream (bản cũ gây "cả cục").

### 2.3 `app/agent/agent_loop.py::run_stream`

- Dùng `self.graph.astream(state, stream_mode=["updates", "custom"])` + `asyncio.Queue` + `_producer` task.
- `custom` mode = token từ `get_writer()` → forward **ngay** (`yield payload`), đánh dấu `yielded_tokens=True`.
- `updates`: classify/call_tools/respond như cũ; **generate node không còn yield cả cục**.
- Heartbeat: `asyncio.wait_for(queue.get(), timeout=3.0)` → nếu timeout `yield {"type":"ping"}` (giữ kết nối qua proxy).
- Lỗi giữa stream → `yield {"type":"error"}`; cuối cùng `yield {"type":"done"}`.

### 2.4 `app/api/chat.py::chat_stream`

- `ttft_ms` đo lúc `first_token`; `ttot_ms = total_latency`.
- `finally` → `_persist()` chạy **background task** (`asyncio.create_task`) cho `save_turn / update_current_context / save_user_fact` → **SSE đóng ngay sau `done`** (trước đây chờ Redis ~200-500ms → UI "đang load" thêm dù text đã xong).
- Telemetry cũng fire-and-forget (`log_metric_background`).

---

## 3. Frontend — render từng token

Widget chat hiện dùng **`frontend/src/store/chatStore.ts` (Zustand)** — không phải `hooks/useChat.ts` (bản cũ không được dùng).

### 3.1 Trước (bug "cả cục")

```ts
if (ev.type === "token") {
  bufferedContent += ev.content;   // chỉ gom vào biến
  return;                           // KHÔNG set state
}
if (ev.type === "done") {
  set({ messages: ... content: bufferedContent }) // đổ 1 cục khi xong
}
```

### 3.2 Sau (fix `92fdc9b`)

```ts
if (ev.type === "token") {
  bufferedContent += ev.content;
  set((s) => ({ messages: s.messages.map((m) =>
    m.id === assistantMsg.id ? { ...m, content: bufferedContent, status: "streaming" } : m
  )}));
  return;
}
// answer / clarify → set luôn
// sources → set luôn
// done → chỉ chốt status: "done"
```

Thêm field `status: "sending" | "streaming" | "done" | "error"` vào `ChatMessage`.

### 3.3 API client (`frontend/src/api.ts` / `api/chat.ts`)

- `fetch('POST /api/chat/stream')` → `res.body.getReader()` → đọc chunk → tách `data: <json>\n\n` → `onEvent(event)`.
- AbortController cho nút Dừng; fallback `chatOnce` (`POST /api/chat`) nếu stream lỗi.

---

## 4. Kiểm tra

```bash
# Backend — xem backend có stream per-word không:
python - <<'PY'
import asyncio
from app.agent.agent_loop import AgentLoop
async def t():
    async for ev in AgentLoop().run_stream("Giá xe VF 7 là bao nhiêu?", [], current_context={}):
        if ev["type"] == "token": print(repr(ev["content"]))
asyncio.run(t())
PY
# mong đợi: 'Giá ' 'xe ' 'VF ' '7 ' 'là:...' (từng token nhỏ)

# Frontend
cd frontend && npm run dev   # Ctrl+Shift+R, hỏi "Giá xe VF7..." → chữ chảy từng token
```

---

## 5. Lỗi đã sửa liên quan

1. `generate` không stream → đợi LLM xong mới yield cả cục (`6c24d24`).
2. Frontend (store cũ) gom buffer chờ `done` mới set → cả cục (`92fdc9b`).
3. `Settings.llm_fallback_model` thiếu → flow LLM lỗi tất cả → "Xin lỗi" (`e844245`).
4. `finally` await Redis/PG chặn đóng SSE → UI "đang load" sau khi xong (`2689152`).