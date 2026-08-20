# Plan — Admin Dashboard Metrics (nhánh riêng, tận dụng `chatbot_ui`)

> Mục tiêu: tách 1 nhánh mới để xây **Admin Dashboard** theo dõi vận hành chatbot
> (KPI, latency, token, chi phí, intent, errors, sessions). **Không** làm tracing
> sâu (Phoenix/OpenTelemetry toàn diện) — chỉ cần **dữ liệu theo dõi vận hành đầy đủ**
> hiển thị trực quan. Tận dụng tối đa stack + setup của nhánh `chatbot_ui`
> (React + TS + Vite + Tailwind + Zustand).
>
> Đây là **plan**, chưa code. Nhánh đề xuất: `admin-dashboard-metrics`.

---

## 1. Bối cảnh & hiện trạng (đã đọc code)

### Backend đã có sẵn (tốt, tận dụng được)

- Bảng `request_metrics` (Postgres) qua `app/core/telemetry.py` — ghi mọi request:
  `request_id, session_id, created_at, query_text, intent, decision, model_used,
  prompt_version, prompt_tokens/completion_tokens/total_tokens, cost_usd/vnd,
  ttft_ms, total_latency_ms, cache_hit, cache_type, tools_used(JSONB), status_code, error_message`.
- 4 API có sẵn trong `app/api/metrics.py`:
  - `GET /api/admin/metrics/overview?hours=` → KPI tổng (requests, tokens, cost, latency P50/P95/P99, TTFT, cache hit rate, error rate).
  - `GET /api/admin/metrics/timeseries?hours=` → chuỗi theo giờ (requests, avg latency/TTFT, tokens, cost, cache_hits).
  - `GET /api/admin/metrics/intents?hours=` → phân bổ intent + %.
  - `GET /api/admin/metrics/logs?limit&offset&intent&cache_only` → log chi tiết, phân trang.
- Auth: user chọn **mở công khai** (giữ nguyên, không thêm login).
- UI chat hiện có rất tối giản (`app/static/index.html`) — **không** dùng cho dashboard.

### Vấn đề / lỗ hổng cần sửa để data "đầy đủ"

1. **`ttft_ms` đang là số GIẢ**: `app/api/chat.py` tính `ttft_ms = total_latency_ms * 0.4`
   (không đo thật). Nhưng agent **đã đo thật** + ghi vào `decision_log`:
   `latency_total_ms`, `latency_retrieval_ms`, `latency_generation_ms`
   (xem `GUIDE.md` mục 5, schema P0). → Cần **đẩy các mốc thật vào `request_metrics`**.
2. **Chưa có `TTOT`** (time-to-output-last-token = thời điểm token cuối cùng).
   `total_latency_ms` hiện gần bằng TTOT nhưng không tách bạch; cần tách
   `latency_total_ms` (toàn pipeline) vs `ttot_ms` (token cuối).
3. **Chưa có breakdown theo giai đoạn** trong `request_metrics`:
   `latency_retrieval_ms`, `latency_generation_ms` (khi coach cá biệt hoá nhanh/chậm).
4. **Chưa có `model_code` / `model_version`** trong log → ko phân tích theo từng dòng xe.
5. **Chưa có `retrieval_status`** (success/fail) và số chunks retrieved.
6. **Chưa có user feedback 👍/👎** để biết chất lượng câu trả lời.
7. **Chưa có realtime** (chỉ query Postgres lịch sử) — dashboard tự refresh / hiển thị
   "requests / phút" theo thời gian thực qua một endpoint nhẹ.

---

## 2. Nhánh & cấu trúc (tận dụng `chatbot_ui`)

- **Nhánh mới**: `admin-dashboard-metrics` (fork từ `origin/chatbot_ui`, hoặc tạo
  branch chứa cả backend đã có + frontend mới).
- **Frontend dashboard** đặt trong `frontend/` (cùng repo structure như chatbot_ui):
  - Nếu chatbot_ui có `frontend/` là chat widget → ta thêm **route `/admin`**
    (react-router hoặc toggle view) để hiển thị dashboard, dùng chung stack.
  - Đề xuất phân tách:
    ```
    frontend/src/
      api/metrics.ts        # client gọi 4 API + API mới
      api/types.ts          # MetricsOverview, TimeseriesPoint, Intent, LogRow...
      store/metricsStore.ts # Zustand: window hours, data, loading, interval
      pages/admin/          # AdminDashboard (layout + tabs)
        OverviewCards.tsx   # KPI cards (requests, tokens, cost, cache hit, error rate)
        TimeSeriesChart.tsx # biểu đồ (requests, latency, cost) theo giờ
        IntentPie.tsx       # phân bổ intent
        RealtimeLine.tsx    # requests/phút realtime (poll 5–10s)
        LogsTable.tsx       # bảng logs chi tiết + search/filter + phân trang
        FeedbackPanel.tsx   # 👍/👎 (nếu có)
      components/ui/*        # Card, Selector (hours), Skeleton, Tooltip
      App.tsx / router
    ```
- **Chart lib đề xuất**: `recharts` (nhẹ, quen thuộc với React, đủ line/bar/pie).

---

## 3. Backend — bổ sung dữ liệu "đầy đủ" (đụng nhẹ, mở rộng schema)

### 3.1. Mở rộng bảng `request_metrics` (migration bằng `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` trong `telemetry._SCHEMA_SQL` — an toàn, idempotent)

Thêm cột:

```sql
ALTER TABLE request_metrics
    ADD COLUMN IF NOT EXISTS ttot_ms             INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS latency_retrieval_ms INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS latency_generation_ms INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS model_code          TEXT,
    ADD COLUMN IF NOT EXISTS model_version       TEXT,
    ADD COLUMN IF NOT EXISTS retrieval_status    TEXT,
    ADD COLUMN IF NOT EXISTS chunks_retrieved    INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS reasoning_tokens    INT DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_req_metrics_model_code ON request_metrics(model_code);
CREATE INDEX IF NOT EXISTS idx_req_metrics_decision ON request_metrics(decision);
```

### 3.2. Sửa `record_metric()` + `chat.py` để truyền số liệu THẬT

- Trong `app/api/chat.py` (cả `/api/chat` và `/api/chat/stream`):
  - Lấy `decision_log` từ `result.decision_log` (đã có `latency_*`).
  - Tính `ttot_ms` = thời điểm event `done`/kết thúc stream (stream) hoặc `total` (non-stream).
  - Lấy `model_code`/`model_version` từ `result.classify_result.entities`.
  - Lấy `retrieval_status`/`chunks_retrieved` từ decision_log (nếu có) hoặc tool_results.
  - Truyền vào `record_metric(...)` thay vì `ttft_ms = total*0.4`.
- **TTFT thật**: với stream, đo `t0 → thời điểm event `token` đầu tiên` (hiện đã có
  `ttft_ms = int((time.time()-t0)*1000)` ở `first_token` — đúng, chỉ cần đẩy qua
  telemetry là đủ; bỏ dòng giả `total*0.4` ở nhánh non-stream, dùng `latency_retrieval_ms`
  làm xấp xỉ nếu không stream).
- `reasoning_tokens`: đọc từ `resp.usage` nếu model hỗ trợ (`generate.py`) — optional.

### 3.3. `user_feedback` (👍/👎)

- API mới `POST /api/admin/metrics/feedback {request_id, rating: 1|-1, comment?}`
  → `UPDATE request_metrics SET user_feedback=$1, feedback_comment=$2 WHERE request_id=$3`
  (thêm 2 cột `user_feedback SMALLINT`, `feedback_comment TEXT`).
- Chat UI gửi feedback để admin theo dõi tỷ lệ hài lòng + lọc log xấu.

### 3.4. Realtime nhẹ (không tracing nặng)

- Endpoint `GET /api/admin/metrics/realtime?window_min=5` →
  `SELECT date_trunc('minute', created_at) ... GROUP BY 1` trong 5–15 phút gần nhất,
  trả requests/min, avg latency, cache hit, error. Dashboard poll 5–10s.

---

## 4. Metrics cụ thể hiển thị (đáp ứng "đầy đủ")

Nhóm KPI (overview, theo window `hours`):

| Nhóm | Chỉ số |
|---|---|
| **Traffic** | total_requests, successful, failed, error_rate_pct, unique_sessions |
| **Latency** | **TTFT** (p50/p95/p99), **TTOT** (p50/p95/p99), total_latency (p50/p95/p99), breakdown retrieval/generation (avg) |
| **Tokens** | prompt/completion/total tokens, reasoning_tokens, tokens/request |
| **Cost** | cost_usd, cost_vnd, cost/request, theo model |
| **Cache** | cache_hit_rate_pct, cache_hits, theo cache_type |
| **Chất lượng** | intent distribution, decision distribution (answer/clarify/refuse/out_of_scope), **feedback 👍/👎 rate** |
| **Per-model** | model_code × version bảng so sánh (giá trị/quan tâm) |
| **Realtime** | requests/min, avg latency/min, cache hit/min, errors/min (line chart) |

Biểu đồ đề xuất trên dashboard:
- **Line**: timeseries requests + avg latency + cost theo giờ (multi-axis hoặc toggle).
- **Line realtime**: requests/min (5–15 phút).
- **Pie/Bar**: intent distribution, decision distribution.
- **Bar**: per-model, cost theo model.
- **Table**: logs chi tiết (filter by intent/decision/model, search query_text, pagination).

---

## 5. Thiết kế UI dashboard (React, theo style chatbot_ui)

- **Layout**: header (title + dropdown chọn window `hours`: 1h/24h/7d/30d + realtime toggle),
  grid các KPI cards, 2–3 biểu đồ hàng đầu, bảng logs bên dưới, tabs nhóm.
- **Token**: màu chủ đạo VinFast `#2C72C6` + trắng + scale gray, font Mulish (giữ
  đồng bộ chatbot_ui — xem `frontend/plan.md` design tokens).
- **Refresh**: nút "Refresh" + auto-poll 30–60s cho overview; realtime line poll 5–10s.
- **Không auth** (theo lựa chọn user): dashboard mở công khai ở route `/admin`.
- **Trạng thái**: skeleton loading, empty-state khi không có data, error banner khi backend/PG lỗi (endpoint trả về mảng rỗng thay vì crash — đã được xử lý trong `metrics.py`).

---

## 6. Thứ tự triển khai (sprint)

### Sprint 1 — Nền backend dữ liệu đầy đủ (trước, vì frontend cần data thật)
- [ ] Mở rộng `_SCHEMA_SQL` (cột mới + index) — idempotent.
- [ ] Sửa `record_metric()` nhận tham số mới (`ttot_ms`, `latency_retrieval_ms`,
      `latency_generation_ms`, `model_code`, `model_version`, `retrieval_status`,
      `reasoning_tokens`).
- [ ] Sửa `chat.py` truyền số liệu thật; bỏ `ttft_ms = total*0.4`; đo `ttot_ms`.
- [ ] API `POST .../feedback` + cột `user_feedback`/`feedback_comment`.
- [ ] API `GET .../realtime`.
- [ ] Backfill/query mới: overview/timeseries/logs đọc thêm cột mới (ttot, breakdown, model_code).
- [ ] Chạy thử + verify data ghi đúng (curl /api/admin/metrics/overview; kiểm tra log có TTOT ≠ 0).

### Sprint 2 — Frontend dashboard (tận dụng chatbot_ui stack)
- [ ] Scaffold `frontend/` (nếu chưa có trong nhánh); thêm `recharts`.
- [ ] `api/metrics.ts` + `types.ts` + `metricsStore.ts`.
- [ ] Overview KPI cards (traffic, latency TTFT/TTOT, tokens, cost, cache, error).
- [ ] TimeSeries + Realtime line charts.
- [ ] Intent/Decision pie + per-model bar.
- [ ] Logs table (search/filter/paginate) + feedback panel.
- [ ] Window selector, refresh, skeleton, empty/error states.
- [ ] Route `/admin`; tích hợp với App.

### Sprint 3 — Cứng hóa
- [ ] Test Real API với DB thật (Neon) + LLM (OpenRouter).
- [ ] Unit test parser/format (Vitest) cho `metrics.ts`.
- [ ] Update docs (kế thừa `METRICS_TELEMETRY_API.md` — thêm endpoint mới + cột mới, bỏ ghi chú "TTFT giả").

---

## 7. Phạm vi KHÔNG làm (tránh "tracing kinh khủng")

- Không tích hợp Phoenix/OpenTelemetry dạng đầy đủ (giữ code `tracing.py` hiện tại như-is).
- Không dựng Grafana/Metabase.
- Không thêm login/auth (user đã chọn mở công khai).
- Không refactor lớn agent loop — chỉ đọc số liệu có sẵn từ `decision_log`/`entities`.

---

## 8. Rủi ro & lưu ý

- **Cột mới = migration**: dùng `ADD COLUMN IF NOT EXISTS` để không vỡ DB đang chạy;
  code cũ chạy song song vẫn OK (cột mới default 0/null).
- **`ttft_ms` bỏ giả**: non-stream request không có TTFT thật → dùng `latency_retrieval_ms`
  hoặc ghi 0; dashboard cần label rõ "TTFT (stream)".
- **`decision_log.latency_*`**: cần chắc chắn `result.decision_log` chứa `latency_retrieval_ms`
  / `latency_generation_ms` (đã có trong GUIDE schema); nếu một số case thiếu → default 0.
- **Perf**: realtime endpoint chỉ quét vài phút + có index `created_at` → nhẹ. Tránh quét
  `intents` mặc định 168h thường xuyên; giữ nguyên.
- **Nhánh**: tạo từ `origin/chatbot_ui` để kế thừa sẵn `frontend/`; nếu chatbot_ui chưa
  có backend metrics → merge `main`/`feature/metric` code `app/api/metrics.py` vào nhánh.
- Đồng bộ design tokens (màu `#2C72C6`, font Mulish, base 16px) với chatbot_ui để 1 giao diện thống nhất.

---

## 9. Giao nhận / Deliverables

1. Nhánh `admin-dashboard-metrics` (sẵn sàng chạy).
2. Backend: schema mới + `record_metric` đầy đủ + API `/feedback`, `/realtime` + số liệu thật (TTFT/TTOT/breakdown/model).
3. Frontend: dashboard `/admin` (React) — KPI, timeseries, realtime, intent, per-model, logs, feedback.
4. Docs cập nhật (`METRICS_TELEMETRY_API.md`) + test (Vitest + smoke gọi API thật).

---

*Plan này chỉ là khuyến nghị từ phân tích code read-only; chưa có thay đổi nào được thực thi. Bước tiếp theo: checkout nhánh mới + Sprint 1 backend (cần quyền ghi).*
