# Vivu — Tài liệu kỹ thuật

Chỉ mục tài liệu toàn hệ thống (nhánh `feature/admin`).

## Vận hành / Dev

- [Cấu hình môi trường (.env)](CONFIGURATION.md) — mọi biến env, LLM thuần OpenAI, Redis, DB, telemetry.
- [Admin Dashboard](ADMIN_DASHBOARD.md) — backend `request_metrics` + 6 endpoints mở không key + frontend `/admin` (React/Zustand/Recharts), đồng bộ landing `#2C72C6` + Mulish.
- [True Streaming](STREAMING.md) — stream từng token thật (generate + agent_loop queue + frontend store), không block SSE khi persist.

## Retriever / Cache

- [Cache System](CACHE_SYSTEM.md) — tầng cache Redis/Upstash, TTL phân tầng (giá 15m, specs 24h, hs 2h, emb 7d, ans 30m), fail-open, data_version.
- [Caching Design](CACHING_DESIGN.md) — bản chốt thiết kế cache (key, hook vào code, rate limit, dedupe).
- [Multi-turn Cache Redis](MULTI_TURN_CACHE_REDIS.md) — cache đa lượt + session/memory.

## Metrics & Telemetry

- [Metrics Telemetry API](METRICS_TELEMETRY_API.md) — chi tiết các endpoint `/api/admin/metrics/*`, công thức chi phí, latency, cache hit + mục Sprint 1 (cột mới, feedback, realtime, auth open).

## Pipeline & Data

- [Data Pipeline](DATA_PIPELINE.md) — end-to-end (clean → split → parse_specs → ingest → postgres).
- [Data Schema Spec](DATA_SCHEMA_SPEC.md) — bảng DB `car_specs/edition/price_list/car_colors/car_options/request_metrics`.
- [Data Quality Improvements](DATA_QUALITY_IMPROVEMENTS.md) — cải thiện chất lượng data.
- [Pipeline Flow](PIPELINE_FLOW.md) — luồng chi tiết.

## Agent / Graph

- [Architecture](architecture.md) — kiến trúc tổng thể.
- [Agent](agent.md) — hướng dẫn agent.
- [Intent Planning](INTENT_PLANNING.md), [Memory Plan](MEMORY_PLAN.md), [Latency](LATENCY.md), [Specs](specs/) — các plan + đặc tả.

## Kế hoạch chờ triển khai

- [Admin Dashboard Metrics plan](../plans/ADMIN-DASHBOARD-METRICS.md) — plan gốc.
- Email Alert CRITICAL (xem [Admin Dashboard §7](ADMIN_DASHBOARD.md#7-kế-hoạch--email-alert-khi-sự-cố-lớn-chưa-thực-hiện)) — chưa code.