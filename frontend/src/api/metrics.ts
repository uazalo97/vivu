/** Admin Metrics API client — gọi 6 endpoint backend (overview, timeseries, intents, logs, realtime, feedback) */
const BASE = "";

export type MetricsOverview = {
  status: string;
  window_hours: number;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  error_rate_pct: number;
  tokens: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  costs: { total_cost_usd: number; total_cost_vnd: number };
  latency_ms: { avg: number; p50: number; p95: number; p99: number };
  ttft_ms: { avg: number; p50: number; p95: number };
  caching: { cache_hits: number; cache_hit_rate_pct: number };
};

export type TimeseriesPoint = {
  bucket: string;
  requests: number;
  avg_latency_ms: number;
  avg_ttft_ms: number;
  total_tokens: number;
  cost_vnd: number;
  cache_hits: number;
};

export type IntentItem = { intent: string; count: number; percentage: number };

export type LogRow = {
  id: number;
  request_id: string;
  session_id: string | null;
  created_at: string;
  query_text: string;
  intent: string;
  decision: string;
  model_used: string;
  prompt_version: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_vnd: number;
  ttft_ms: number;
  ttot_ms?: number;
  total_latency_ms: number;
  latency_retrieval_ms?: number;
  latency_generation_ms?: number;
  cache_hit: boolean;
  cache_type: string;
  tools_used: string[];
  status_code: number;
  error_message: string | null;
  model_code: string | null;
  model_version: string | null;
  retrieval_status: string | null;
  chunks_retrieved: number;
  reasoning_tokens: number;
  user_feedback: number | null;
  feedback_comment: string | null;
};

export type RealtimePoint = {
  bucket: string;
  requests: number;
  avg_latency_ms: number;
  avg_ttft_ms: number;
  cache_hits: number;
  errors: number;
};

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`GET ${url} ${r.status}`);
  return r.json() as Promise<T>;
}

export function fetchOverview(hours: number) {
  return getJSON<MetricsOverview>(`${BASE}/api/admin/metrics/overview?hours=${hours}`);
}
export function fetchTimeseries(hours: number) {
  return getJSON<{ status: string; points: TimeseriesPoint[] }>(`${BASE}/api/admin/metrics/timeseries?hours=${hours}`);
}
export function fetchIntents(hours: number) {
  return getJSON<{ status: string; intents: IntentItem[] }>(`${BASE}/api/admin/metrics/intents?hours=${hours}`);
}
export function fetchLogs(params: { limit?: number; offset?: number; intent?: string; cache_only?: boolean } = {}) {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.intent) q.set("intent", params.intent);
  if (params.cache_only) q.set("cache_only", "true");
  return getJSON<{ total: number; limit: number; offset: number; logs: LogRow[] }>(`${BASE}/api/admin/metrics/logs?${q}`);
}
export function fetchRealtime(window_min = 5) {
  return getJSON<{ status: string; window_min: number; points: RealtimePoint[] }>(
    `${BASE}/api/admin/metrics/realtime?window_min=${window_min}`,
  );
}
export async function postFeedback(request_id: string, rating: 1 | -1, comment?: string) {
  const r = await fetch(`${BASE}/api/admin/metrics/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id, rating, comment }),
  });
  if (!r.ok) throw new Error(`feedback ${r.status}`);
  return r.json();
}
