# Admin Dashboard — Tài liệu Chi Tiết

Hệ thống Admin trên nhánh `feature/admin`, xây theo plan `plans/ADMIN-DASHBOARD-METRICS.md`, tách từ nhánh `chatbot_ui`. Gồm **backend telemetry đầy đủ** (`request_metrics` mở rộng + 6 endpoints) và **frontend `/admin`** (React + Zustand + Recharts) đồng bộ design token landing (`#2C72C6`, Mulish 16px).

> Trạng thái: toàn bộ endpoint `/api/admin/*` **MỞ KHÔNG CẦN KEY** (theo yêu cầu). Không gửi header `X-Admin-Key`.

---

## 1. Kiến trúc tổng quan

```
Browser (React/Vite)
   │  /admin (AdminDashboard)      /  (Landing + ChatWidget)
   ▼
FastAPI (app/main.py)
   ├─ health_router        → /healthz, /ready, /api/health
   ├─ chat_router          → /api/chat, /api/chat/stream (?)
   ├─ metrics_router       → /api/admin/metrics/*   (6 endpoints)
   └─ admin_prompts_router → /api/admin/prompts/*   (Prompt Registry)
   ▼
app/core/telemetry.py → PostgreSQL table request_metrics (Neon)
frontend/src/api/metrics.ts + store/metricsStore.ts + pages/admin/*
```

**Router được mount trong `app/main.py`:**
```python
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(metrics_router)
app.include_router(admin_prompts_router)  # trước đây THIẾU → /api/admin/prompts/* 404
```

---

## 2. Backend — bảng `request_metrics` (Sprint 1)

File: `app/core/telemetry.py`

### 2.1 Schema đầy đủ (đã mở rộng)

`CREATE TABLE IF NOT EXISTS request_metrics` + **migrate idempotent** (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) — chạy mỗi lần `record_metric` để DB cũ tự thêm cột:

| Cột | Ý nghĩa |
|---|---|
| `request_id, session_id, created_at, query_text` | Identity |
| `intent, decision, model_used, prompt_version` | Phân loại |
| `prompt_tokens, completion_tokens, total_tokens` | Token |
| `cost_usd, cost_vnd` | Chi phí (MODEL_PRICING + USD_VND rate) |
| `ttft_ms` | Time-to-first-token (thật, từ stream) |
| `ttot_ms` | Time-to-output-last-token (mới) |
| `total_latency_ms` | Toàn pipeline |
| `latency_retrieval_ms`, `latency_generation_ms` | Breakdown theo giai đoạn (mới) |
| `cache_hit, cache_type` | Cache |
| `tools_used (JSONB), status_code, error_message` | Debug |
| `model_code, model_version` | Dòng xe (mới) |
| `retrieval_status, chunks_retrieved` | Retrieval (mới) |
| `reasoning_tokens` | Token reasoning (mới) |
| `user_feedback (SMALLINT), feedback_comment` | 👍/👎 (mới) |

Index: `created_at DESC, intent, cache_hit, session_id, model_code, decision`.

### 2.2 `record_metric()` — số liệu THẬT (bỏ `ttft * 0.4` giả)

- `app/api/chat.py` (non-stream): lấy `ttft/ttot/latency_retrieval/latency_generation/model_code/model_version/chunks_retrieved` từ `result.decision_log` + `entities`; fallback `ttft = latency_retrieval_ms` nếu không có stream.
- `app/api/chat.py` (stream): `ttft_ms` đo lúc **first token**; `ttot_ms = total_latency`; `model_code/version` từ `entities` event.
- Sai sót cũ đã sửa: `column "model_code" does not exist` → tự migrate + retry 1 lần trước khi `WARNING`.

### 2.3 Persist memory không chặn stream

`chat_stream` `finally` gói `save_turn/update_current_context/save_user_fact` vào `asyncio.create_task(_persist())` (fire-and-forget, fail-open) → kết nối SSE **đóng ngay sau `done`**, không để UI "đang load" thêm 200-500ms.

---

## 3. Backend — REST Endpoints (mở không key)

Tất cả trong `app/api/metrics.py` (prefix `/api/admin/metrics`).

| Endpoint | Tham số | Mô tả |
|---|---|---|
| `GET /overview?hours=1..720` | hours (mặc định 24) | KPI tổng: requests, tokens, cost, latency P50/P95/P99, TTFT P50/P95, cache hit, error rate |
| `GET /timeseries?hours=` | hours | Chuỗi theo giờ: requests, avg latency/TTFT, tokens, cost_vnd, cache_hits |
| `GET /intents?hours=` | hours (mặc định 168) | Phân bổ intent + percentage |
| `GET /logs?limit&offset&intent&cache_only` | limit≤200, offset, intent, cache_only | Log chi tiết phân trang + filter |
| `POST /feedback` | `{request_id, rating: 1\|-1, comment?}` | Ghi 👍/👎 → `UPDATE user_feedback` |
| `GET /realtime?window_min=1..60` | window_min (mặc định 5) | requests/min, avg latency/TTFT, cache/min, errors/min — poll 5-10s |

Backend function: `get_metrics_overview`, `get_metrics_timeseries`, `get_metrics_intents`, `get_metrics_logs`, `record_feedback`, `get_metrics_realtime`.

### Prompt Registry

`app/api/admin_prompts.py` (prefix `/api/admin/prompts`) — **bỏ `verify_admin_key`** (hàm đã gỡ, import lỗi `ImportError`), giờ mở hoàn toàn:
`GET ""` , `GET /active` , `GET /{type}/{version}` , `POST ""` , `POST /{type}/{version}/activate` , `POST /test-render`.

---

## 4. Frontend — Admin Dashboard `/admin` (Sprint 2)

Stack: Vite + React 18 + TS + Tailwind v4 + **Zustand** + **recharts** + react-router-dom v6 (tất cả trong `frontend/`).

### 4.1 Tệp

```
frontend/src/api/metrics.ts      # typed client cho 6 endpoints
frontend/src/store/metricsStore.ts # Zustand: hours/realtimeWindow + refresh()
frontend/src/pages/admin/AdminDashboard.tsx  # layout + charts + logs + feedback
frontend/src/App.tsx             # BrowserRouter: /admin → AdminDashboard, /* → Landing+Chat
```

### 4.2 Store

```ts
useMetricsStore: hours (24), realtimeWindow (5), overview, timeseries, intents,
                realtime, logs, logsTotal, loading, error
  setHours(h) → đổi window; refresh() → Promise.all 5 endpoints
```

### 4.3 UI (đồng bộ landing)

- Header: logo khối `#2C72C6`, title, dropdown `hours` (1h/24h/7d/30d), nút Refresh, checkbox Auto (poll 30s overview / 10s realtime).
- KPI cards: Requests, Cache hit %, Tokens, Cost ($/VND), Latency P95, TTFT P95, Error rate, Window.
- Line charts: Timeseries requests+latency, Realtime requests/min.
- Pie + Bar: phân bổ intent.
- Logs table: query, intent, TTFT/TTOT, cache, model, feedback 👍/👎 (gọi `POST /feedback`).
- Trạng thái: skeleton/empty/error banner.

Design token dùng chung `frontend/src/index.css`: `--color-primary #2C72C6`, `--color-primary-hover #24599E`, `--color-chat-border #E6EEF8`, `--font-sans "Mulish" 16px`.

---

## 5. Cách chạy & kiểm tra

```bash
# Backend
cp .env.example .env   # điền OPENAI_API_KEY, PG_DSN, REDIS_URL...
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
# mở http://localhost:5173/admin
```

Smoke test:
```bash
python tests/test_devops_and_metrics.py
# test_healthz_liveness, test_admin_metrics_auth_protection (open), test_prompt_registry_and_admin_api (200)
curl "http://localhost:8000/api/admin/metrics/overview?hours=24"
curl -X POST http://localhost:8000/api/admin/metrics/feedback -H "Content-Type: application/json" \
  -d '{"request_id":"req_xxx","rating":1}'
```

---

## 6. Lỗi đã sửa trong quá trình

1. `verify_admin_key` không tồn tại (metrics đã gỡ) → bỏ import + `Security()`.
2. `/api/admin/prompts/*` 404 → mount router trong `main.py`.
3. Test `test_admin_metrics_auth_protection` đòi 401 (lệch code open) → sửa thành open.
4. `column "model_code" does not exist` → auto-migrate + retry.
5. `llm_fallback_model` thiếu trong config → bot "Xin lỗi..." → thêm vào `Settings`.

---

## 7. Kế hoạch — Email Alert khi sự cố lớn (CHƯA THỰC HIỆN)

> Theo yêu cầu: gửi mail khi sự cố lớn; sự cố bé chỉ hiện ở Admin. **Chờ làm sau.**

### Phân cấp

| Mức | Điều kiện | Xử lý |
|---|---|---|
| **CRITICAL → EMAIL** | error rate > ngưỡng (vd 10%/5p), LLM fail toàn bộ, Redis/Qdrant/Postgres down kéo dài, stream 500 liên tục, 429 bùng nổ | Gửi mail SMTP (hoặc Resend/Brevo) + cooldown 10-15 phút/category + dedupe |
| **WARNING → Admin** | lỗi lẻ, latency cao cục bộ, cache miss nhiều | Chỉ ghi `request_metrics` + hiển thị dashboard |

### Chuẩn bị (khi làm)

1. `.env`: `SMTP_HOST/PORT/USER/PASS/FROM/TO` + `ALERT_EMAIL_ENABLED`.
2. `send_alert_email(subject, body)` (background task + cooldown per-category + dedupe).
3. Trigger định kỳ sau `record_metric` hoặc task scan 1-5 phút check cửa sổ CRITICAL.
4. Admin thêm tab/panel "Alert" liệt kê lịch sử cảnh báo (sự cố bé tách biệt sẵn).