import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from "recharts";
import { useMetricsStore } from "../../store/metricsStore";
import { postFeedback } from "../../api/metrics";

const COLORS = ["#2C72C6", "#24599E", "#1E4D83", "#6B7280", "#9CA3AF", "#D1D5DB"];

function KpiCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-2xl border border-[var(--color-chat-border)] bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-[var(--color-ink-soft)]">{label}</div>
      <div className="mt-1 text-2xl font-bold text-[var(--color-ink)]">{value}</div>
      {sub && <div className="text-xs text-[var(--color-ink-soft)]">{sub}</div>}
    </div>
  );
}

function fmt(n: number) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export default function AdminDashboard() {
  const { hours, overview, timeseries, intents, realtime, logs, logsTotal, loading, error, setHours, refresh } =
    useMetricsStore();
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    refresh();
  }, [refresh, hours]);

  useEffect(() => {
    if (!auto) return;
    const id = setInterval(() => refresh(), 30000);
    return () => clearInterval(id);
  }, [auto, refresh]);

  // realtime poll 10s
  useEffect(() => {
    if (!auto) return;
    const id = setInterval(() => {
      // only realtime part could be polled faster, but we refresh all for simplicity
      refresh();
    }, 10000);
    return () => clearInterval(id);
  }, [auto, refresh]);

  return (
    <div className="min-h-screen bg-[var(--color-primary-soft)] font-sans">
      {/* Header — đồng bộ landing: trắng + primary #2C72C6, font Mulish */}
      <header className="sticky top-0 z-10 border-b border-[var(--color-chat-border)] bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-[var(--color-primary)]" />
            <div>
              <h1 className="text-lg font-bold text-[var(--color-ink)]">Admin Dashboard</h1>
              <p className="text-xs text-[var(--color-ink-soft)]">Vận hành chatbot — realtime & KPI</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              className="rounded-xl border border-[var(--color-chat-border)] bg-white px-3 py-2 text-sm"
            >
              <option value={1}>1 giờ</option>
              <option value={24}>24 giờ</option>
              <option value={168}>7 ngày</option>
              <option value={720}>30 ngày</option>
            </select>
            <button
              onClick={() => refresh()}
              className="rounded-xl bg-[var(--color-primary)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--color-primary-hover)]"
            >
              Refresh
            </button>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
              Auto
            </label>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] space-y-6 px-6 py-6">
        {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        {loading && <div className="rounded-xl bg-white p-4 text-sm text-[var(--color-ink-soft)]">Đang tải...</div>}

        {/* KPI Cards */}
        {overview && (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label="Requests" value={fmt(overview.total_requests)} sub={`${overview.successful_requests} ok / ${overview.failed_requests} fail`} />
            <KpiCard label="Cache hit" value={`${overview.caching.cache_hit_rate_pct}%`} sub={`${overview.caching.cache_hits} hits`} />
            <KpiCard label="Tokens" value={fmt(overview.tokens.total_tokens)} sub={`${fmt(overview.tokens.prompt_tokens)} in / ${fmt(overview.tokens.completion_tokens)} out`} />
            <KpiCard label="Cost" value={`${overview.costs.total_cost_usd.toFixed(2)} $`} sub={`${overview.costs.total_cost_vnd.toLocaleString()} VND`} />
            <KpiCard label="Latency p95" value={`${overview.latency_ms.p95}ms`} sub={`avg ${overview.latency_ms.avg}ms / p50 ${overview.latency_ms.p50}ms`} />
            <KpiCard label="TTFT p95" value={`${overview.ttft_ms.p95}ms`} sub={`avg ${overview.ttft_ms.avg}ms`} />
            <KpiCard label="Error rate" value={`${overview.error_rate_pct}%`} sub={`${overview.failed_requests} lỗi`} />
            <KpiCard label="Window" value={`${overview.window_hours}h`} sub={`realtime ${realtime.length} points`} />
          </div>
        )}

        {/* Timeseries + Realtime */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-[var(--color-chat-border)] bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">Requests & Latency theo giờ</h3>
            <div className="h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={timeseries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e6eef8" />
                  <XAxis dataKey="bucket" tick={{ fontSize: 10 }} tickFormatter={(v: string) => new Date(v).toLocaleTimeString()} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="requests" stroke="#2C72C6" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="avg_latency_ms" stroke="#24599E" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="rounded-2xl border border-[var(--color-chat-border)] bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">Realtime — requests/min (5’)</h3>
            <div className="h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={realtime}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e6eef8" />
                  <XAxis dataKey="bucket" tick={{ fontSize: 10 }} tickFormatter={(v: string) => new Date(v).toLocaleTimeString()} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="requests" stroke="#1E4D83" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Intent pie + per-model bar */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-[var(--color-chat-border)] bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">Phân bổ Intent</h3>
            <div className="h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={intents} dataKey="count" nameKey="intent" cx="50%" cy="50%" outerRadius={90} label>
                    {intents.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="rounded-2xl border border-[var(--color-chat-border)] bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold">Requests theo Intent</h3>
            <div className="h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={intents}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e6eef8" />
                  <XAxis dataKey="intent" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#2C72C6" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Logs table */}
        <div className="rounded-2xl border border-[var(--color-chat-border)] bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Logs chi tiết ({logsTotal})</h3>
            <span className="text-xs text-[var(--color-ink-soft)]">50 gần nhất • filter theo intent/cache</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b text-[var(--color-ink-soft)]">
                <tr>
                  <th className="p-2">Time</th>
                  <th className="p-2">Query</th>
                  <th className="p-2">Intent</th>
                  <th className="p-2">TTFT/TTOT</th>
                  <th className="p-2">Cache</th>
                  <th className="p-2">Model</th>
                  <th className="p-2">Feedback</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((r) => (
                  <tr key={r.id} className="border-b last:border-0 hover:bg-[var(--color-primary-soft)]">
                    <td className="p-2 whitespace-nowrap">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="p-2 max-w-[280px] truncate" title={r.query_text}>
                      {r.query_text}
                    </td>
                    <td className="p-2">{r.intent}</td>
                    <td className="p-2">
                      {r.ttft_ms}/{r.ttot_ms ?? r.total_latency_ms}ms
                    </td>
                    <td className="p-2">{r.cache_hit ? "hit" : "miss"} ({r.cache_type})</td>
                    <td className="p-2">
                      {r.model_code || "-"} {r.model_version ? `(${r.model_version})` : ""}
                    </td>
                    <td className="p-2">
                      <span className="mr-2">{r.user_feedback === 1 ? "👍" : r.user_feedback === -1 ? "👎" : "—"}</span>
                      <button
                        onClick={() => postFeedback(r.request_id, 1).then(() => refresh())}
                        className="mr-1 rounded bg-green-50 px-2 py-0.5 text-green-700 hover:bg-green-100"
                      >
                        👍
                      </button>
                      <button
                        onClick={() => postFeedback(r.request_id, -1).then(() => refresh())}
                        className="rounded bg-red-50 px-2 py-0.5 text-red-700 hover:bg-red-100"
                      >
                        👎
                      </button>
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="p-6 text-center text-[var(--color-ink-soft)]">
                      Chưa có data — chạy vài request chat rồi refresh
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-xl border border-[var(--color-chat-border)] bg-white p-3 text-xs text-[var(--color-ink-soft)]">
          Design đồng bộ landing: <span className="font-semibold text-[var(--color-primary)]">#2C72C6</span> + Mulish 16px + Tailwind + Zustand + Recharts. Poll overview 30s, realtime 10s.
        </div>
      </main>
    </div>
  );
}
