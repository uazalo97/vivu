# Tài Liệu Kỹ Thuật: Hệ Thống Admin Telemetry & Metrics (Dashboard Giám Sát)

Tài liệu này hướng dẫn chi tiết về hệ thống theo dõi vận hành, đo lường chi phí LLM, phân tích độ trễ và cung cấp các REST API cho Dashboard quản trị / Frontend.

---

## 1. Tổng Quan Kiến Trúc

Hệ thống Telemetry & Metrics được thiết kế non-blocking, tự động thu thập và lưu trữ thông tin của mọi request qua chatbot:
- **Thời gian phản hồi:** TTFT (Time-to-First-Token) & Total Latency (P50, P95, P99).
- **Tiêu thụ Token:** Prompt Tokens, Completion Tokens, Total Tokens.
- **Chi phí vận hành:** Tự động tính tiền theo bảng giá model (USD và VNĐ).
- **Phân bổ hành vi:** Ý định người dùng (Intent), Công cụ sử dụng (Tools), Tỷ lệ Cache Hit, Tỷ lệ lỗi.

Dữ liệu được lưu trữ tự động trong bảng `request_metrics` trên cơ sở dữ liệu PostgreSQL.

---

## 2. Bảng Giá Mô Hình & Công Thức Tính Chi Phí

Chi phí được tính tự động dựa trên số lượng token vào/ra và tỷ giá hối đoái cấu hình trong hệ thống:

| Nhà cung cấp / Model | Giá Input (USD / 1M tokens) | Giá Output (USD / 1M tokens) |
| :--- | :--- | :--- |
| **OpenAI GPT-4o-mini** | $0.15 | $0.60 |
| **OpenAI GPT-4o** | $2.50 | $10.00 |
| **DeepSeek V4 Flash / Chat** | $0.14 | $0.28 |
| **DeepSeek V3** | $0.27 | $1.10 |
| **Claude 3.5 Haiku** | $0.80 | $4.00 |
| **Gemini 2.0 Flash** | $0.10 | $0.40 |

> **Công thức:**
> - `Total Cost USD = (Prompt Tokens / 1,000,000 * Input Rate) + (Completion Tokens / 1,000,000 * Output Rate)`
> - `Total Cost VND = Total Cost USD * USD_VND_EXCHANGE_RATE`

---

## 3. Chi Tiết Các REST API Endpoints

Toàn bộ các endpoint này mở trực tiếp cho Frontend / Dashboard gọi dữ liệu mà không cần xác thực header.

### 3.1. Tổng quan KPI Vận Hành (`GET /api/admin/metrics/overview`)
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

### 3.2. Chuỗi Thời Gian Vẽ Biểu Đồ (`GET /api/admin/metrics/timeseries`)
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

### 3.3. Phân Bổ Ý Định Người Dùng (`GET /api/admin/metrics/intents`)
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

### 3.4. Danh Sách Request Logs Chi Tiết (`GET /api/admin/metrics/logs`)
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

## 4. Mã Mẫu Tích Hợp Frontend (TypeScript / React)

```typescript
// services/metricsService.ts
export interface MetricsOverview {
  total_requests: number;
  tokens: { total_tokens: number };
  costs: { total_cost_usd: number; total_cost_vnd: number };
  latency_ms: { avg: number; p50: number; p95: number; p99: number };
  ttft_ms: { avg: number; p50: number; p95: number };
  caching: { cache_hit_rate_pct: number };
}

export async function fetchOverviewKPI(hours = 24): Promise<MetricsOverview> {
  const res = await fetch(`/api/admin/metrics/overview?hours=${hours}`);
  if (!res.ok) throw new Error('Failed to fetch overview metrics');
  return res.json();
}
```
