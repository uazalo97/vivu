# Tài Liệu Kỹ Thuật: Hệ Thống Admin Telemetry & Metrics (Dashboard Giám Sát)

Tài liệu này hướng dẫn chi tiết về hệ thống theo dõi vận hành, cơ chế tính toán chi phí LLM, thời hạn dữ liệu, đo lường độ trễ và cung cấp các REST API cho Dashboard quản trị / Frontend.

---

## 1. Tổng Quan Kiến Trúc

Hệ thống Telemetry & Metrics được thiết kế non-blocking, tự động thu thập và lưu trữ thông tin của mọi request qua chatbot:
- **Thời gian phản hồi:** TTFT (Time-to-First-Token) & Total Latency (P50, P95, P99).
- **Tiêu thụ Token:** Prompt Tokens, Completion Tokens, Total Tokens.
- **Chi phí vận hành:** Tự động tính tiền theo bảng giá model (USD và VNĐ).
- **Phân bổ hành vi:** Ý định người dùng (Intent), Công cụ sử dụng (Tools), Tỷ lệ Cache Hit, Tỷ lệ lỗi.

Dữ liệu được lưu trữ tự động trong bảng `request_metrics` trên cơ sở dữ liệu PostgreSQL (Neon Cloud / Local).

---

## 2. Thời Hạn Tính Toán & Lưu Trữ Dữ Liệu (Time Window & Data Retention)

### 2.1. Khung thời gian trượt (Rolling Time Window)
- Mọi endpoint phân tích đều nhận tham số query param **`hours`** (mặc định: `24` giờ đối với overview/timeseries, và `168` giờ = 7 ngày đối với phân bổ intent).
- Phép tính được thực hiện dựa trên mệnh đề SQL:
  ```sql
  WHERE created_at >= now() - ($1 || ' hours')::interval
  ```
- **Ý nghĩa:** Hệ thống sẽ quét ngược chính xác số giờ tương ứng tính từ thời điểm hiện tại (`now()`). Bạn có thể truyền bất kỳ số giờ nào, ví dụ:
  - `hours=1`: Xem số liệu trong 1 giờ gần nhất.
  - `hours=24`: Xem 24 giờ qua (1 ngày).
  - `hours=168`: Xem 7 ngày qua (1 tuần).
  - `hours=720`: Xem 30 ngày qua (1 tháng).

### 2.2. Thời hạn lưu trữ dữ liệu (Data Retention)
- Mọi bản ghi request log đều được lưu trữ **vĩnh viễn (persistent)** trong bảng `request_metrics` của PostgreSQL.
- Dữ liệu không bị mất khi server khởi động lại hoặc redeploy.

---

## 3. Công Thức & Cách Tính Chi Tiết Từng Chỉ Số

### 3.1. Bảng Giá Mô Hình & Công Thức Tính Chi Phí

Hệ thống định nghĩa bảng giá USD trên 1 Triệu tokens (1M tokens) theo niêm yết của các nhà cung cấp:

| Nhà cung cấp / Model | Giá Input (USD / 1M tokens) | Giá Output (USD / 1M tokens) |
| :--- | :--- | :--- |
| **OpenAI GPT-4o-mini** | $0.15 | $0.60 |
| **OpenAI GPT-4o** | $2.50 | $10.00 |
| **DeepSeek V4 Flash / Chat** | $0.14 | $0.28 |
| **DeepSeek V3** | $0.27 | $1.10 |
| **DeepSeek R1** | $0.55 | $2.19 |
| **Claude 3.5 Haiku** | $0.80 | $4.00 |
| **Claude 3.5 Sonnet** | $3.00 | $15.00 |
| **Gemini 2.0 Flash** | $0.10 | $0.40 |

**Công thức tính chi phí:**
$$\text{Cost USD} = \left(\frac{\text{Prompt Tokens}}{1.000.000} \times \text{Input Price}\right) + \left(\frac{\text{Completion Tokens}}{1.000.000} \times \text{Output Price}\right)$$
$$\text{Cost VND} = \text{Cost USD} \times \text{USD\_VND\_EXCHANGE\_RATE (mặc định: 25.400 đ)}$$

---

### 3.2. Số Lượng Yêu Cầu & Tỷ Lệ Lỗi (Error Rate)
- **`total_requests`**: Tổng số lượt gọi trong khoảng thời gian (`COUNT(*)`).
- **`successful_requests`**: Số lượt gọi thành công (`status_code < 400`).
- **`failed_requests`**: Số lượt gọi gặp lỗi (`status_code >= 400`).
- **`error_rate_pct`**: Tỷ lệ phần trăm lỗi:
  $$\text{Error Rate (\%)} = \frac{\text{failed\_requests}}{\text{total\_requests}} \times 100$$

---

### 3.3. Độ Trễ (Latency) & Thời Gian Phản Hồi Đầu Tiên (TTFT)
- **TTFT (Time-to-First-Token):** Khoảng thời gian từ lúc server nhận request đến khi token/chunk đầu tiên được stream ra cho người dùng ($t_{\text{first token}} - t_0$). Chỉ số này phản ánh độ nhạy phản hồi của chatbot.
- **Total Latency:** Tổng thời gian từ lúc bắt đầu xử lý request đến khi hoàn tất toàn bộ chuỗi streaming ($t_{\text{end}} - t_0$).
- **Phân vị Latency (P50, P95, P99):** Sử dụng hàm thống kê chuẩn `PERCENTILE_CONT` trong PostgreSQL:
  - **P50 (Median):** 50% người dùng có thời gian phản hồi nhanh hơn mức này.
  - **P95:** 95% người dùng có thời gian phản hồi nhanh hơn mức này (đại diện cho chất lượng dịch vụ SLA cam kết).
  - **P99:** 99% người dùng phản hồi nhanh hơn mức này (dùng để phát hiện các tình huống nghẽn mạng nghiêm trọng).

---

### 3.4. Tỷ Lệ Cache Hit (Cache Hit Rate)
- **`cache_hits`**: Số lượng request được phục vụ trực tiếp từ bộ nhớ đệm (Semantic Cache / Exact Cache).
- **`cache_hit_rate_pct`**: Tỷ lệ phần trăm cache:
  $$\text{Cache Hit Rate (\%)} = \frac{\text{cache\_hits}}{\text{total\_requests}} \times 100$$

---

### 3.5. Phân Bổ Ý Định (Intent Distribution)
- Gom nhóm theo từng chủ đề câu hỏi (`specs` - thông số xe, `price` - giá bán, `compare` - so sánh xe, `policy` - chính sách ưu đãi, `out_of_scope` - ngoài phạm vi).
- Tính tỷ lệ phần trăm mức độ quan tâm:
  $$\text{Intent Percentage (\%)} = \frac{\text{Số lượng câu hỏi của Intent}}{\text{Tổng số lượng tất cả câu hỏi}} \times 100$$

---

## 4. Chi Tiết Các REST API Endpoints

Toàn bộ các endpoint này mở trực tiếp cho Frontend / Dashboard gọi dữ liệu mà không cần xác thực header.

### 4.1. Tổng quan KPI Vận Hành (`GET /api/admin/metrics/overview`)
- **Query Params:**
  - `hours` (int, mặc định: `24`, phạm vi: `1-720`): Khoảng thời gian thống kê.
- **Response `200 OK`:**
```json
{
  "status": "success",
  "window_hours": 24,
  "total_requests": 1420,
  "successful_requests": 1410,
  "failed_requests": 10,
  "error_rate_pct": 0.7,
  "tokens": {
    "prompt_tokens": 1250000,
    "completion_tokens": 480000,
    "total_tokens": 1730000
  },
  "costs": {
    "total_cost_usd": 0.3094,
    "total_cost_vnd": 7858.76
  },
  "latency_ms": {
    "avg": 820,
    "p50": 650,
    "p95": 1450,
    "p99": 2100
  },
  "ttft_ms": {
    "avg": 240,
    "p50": 190,
    "p95": 420
  },
  "caching": {
    "cache_hits": 450,
    "cache_hit_rate_pct": 31.69
  }
}
```

---

### 4.2. Chuỗi Thời Gian Vẽ Biểu Đồ (`GET /api/admin/metrics/timeseries`)
- **Query Params:**
  - `hours` (int, mặc định: `24`): Khoảng thời gian thống kê.
- **Response `200 OK`:**
```json
{
  "status": "success",
  "points": [
    {
      "bucket": "2026-08-18T10:00:00+00:00",
      "requests": 85,
      "avg_latency_ms": 610,
      "avg_ttft_ms": 180,
      "total_tokens": 110500,
      "cost_vnd": 512.4,
      "cache_hits": 28
    }
  ]
}
```

---

### 4.3. Phân Bổ Ý Định Người Dùng (`GET /api/admin/metrics/intents`)
- **Query Params:**
  - `hours` (int, mặc định: `168` — 7 ngày): Khoảng thời gian thống kê.
- **Response `200 OK`:**
```json
{
  "status": "success",
  "intents": [
    { "intent": "specs", "count": 680, "percentage": 47.89 },
    { "intent": "price", "count": 390, "percentage": 27.46 },
    { "intent": "compare", "count": 180, "percentage": 12.68 },
    { "intent": "policy", "count": 110, "percentage": 7.75 },
    { "intent": "out_of_scope", "count": 60, "percentage": 4.22 }
  ]
}
```

---

### 4.4. Danh Sách Request Logs Chi Tiết (`GET /api/admin/metrics/logs`)
- **Query Params:**
  - `limit` (int, mặc định: `50`, tối đa `200`): Số bản ghi mỗi trang.
  - `offset` (int, mặc định: `0`): Vị trí bắt đầu phân trang.
  - `intent` (string, tùy chọn): Lọc theo loại ý định (vd: `specs`, `price`, `general`).
  - `cache_only` (bool, mặc định: `false`): Lọc riêng các request có cache hit.
- **Response `200 OK`:**
```json
{
  "total": 1420,
  "limit": 50,
  "offset": 0,
  "logs": [
    {
      "id": 1,
      "request_id": "req_abc123",
      "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "created_at": "2026-08-18T12:00:00Z",
      "query_text": "VF 8 Plus pin bao nhiêu kWh?",
      "intent": "specs",
      "decision": "answer",
      "model_used": "openai/gpt-4o-mini",
      "prompt_version": "v1.0.0",
      "prompt_tokens": 850,
      "completion_tokens": 120,
      "total_tokens": 970,
      "cost_usd": 0.000199,
      "cost_vnd": 5.07,
      "ttft_ms": 195,
      "total_latency_ms": 720,
      "cache_hit": false,
      "cache_type": "none",
      "tools_used": ["get_specs"],
      "status_code": 200,
      "error_message": null
    }
  ]
}
```

---

## 5. Mã Mẫu Tích Hợp Frontend (TypeScript / React)

```typescript
// services/metricsService.ts
export interface MetricsOverview {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  error_rate_pct: number;
  tokens: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  costs: { total_cost_usd: number; total_cost_vnd: number };
  latency_ms: { avg: number; p50: number; p95: number; p99: number };
  ttft_ms: { avg: number; p50: number; p95: number };
  caching: { cache_hits: number; cache_hit_rate_pct: number };
}

export async function fetchOverviewKPI(hours = 24): Promise<MetricsOverview> {
  const res = await fetch(`/api/admin/metrics/overview?hours=${hours}`);
  if (!res.ok) throw new Error('Failed to fetch overview metrics');
  return res.json();
}
```
