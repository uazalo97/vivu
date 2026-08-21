# Vivu — Hướng dẫn chạy & phát triển

> Trợ lý tư vấn xe VinFast: RAG (Qdrant + PostgreSQL) + LLM + multi-turn memory + cache Redis + Admin Dashboard.

---

## 1. Yêu cầu

| Thành phần | Yêu cầu | Ghi chú |
|---|---|---|
| Python | 3.11+ | |
| LLM | OpenAI API key | hoặc endpoint OpenAI-compatible khác (TokenRouter/Groq/OpenRouter) |
| PostgreSQL | Neon Cloud (hoặc local) | specs / colors / options / price / telemetry |
| Qdrant | Cloud (hoặc local) | vector store (product_info / policy / maintenance) |
| Redis | Upstash (hoặc local) | session store + tool-result cache (fail-open, không bắt buộc) |
| Rerank | Cohere API key | optional — fallback CrossEncoder nếu thiếu |

---

## 2. Clone & Install

```bash
git clone https://github.com/uazalo97/vivu.git
cd vivu
git checkout <branch>   # main / multi-turn-cache-redis / feature/*
pip install -r requirements.txt
```

---

## 3. Cấu hình `.env`

Copy từ mẫu rồi điền giá trị thật:

```bash
cp .env.example .env
```

Các biến chính (xem đầy đủ placeholder trong `.env.example`):

```env
# ── LLM + Embedding (single OpenAI key) ─────────────
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small
LLM_FALLBACK_MODEL=          # (optional) fallback khi model chính lỗi

# ── PostgreSQL (Neon) ─────────────────────────────
POSTGRES_URL=postgresql+asyncpg://user:pass@host:5432/dbname?sslmode=require
PG_DSN=postgresql://user:pass@host:5432/dbname?sslmode=require

# ── Redis (Upstash serverless — session + cache) ──
REDIS_URL=rediss://default:<token>@<host>.upstash.io:6379

# ── Qdrant ─────────────────────────────────────────
QDRANT_URL=https://<cluster>.qdrant.io
QDRANT_API_KEY=<key>
QDRANT_COLLECTION=vivu_specs

# ── Rerank (Cohere) ────────────────────────────────
RERANK_ENABLED=true
RERANK_MODEL=rerank-multilingual-v3.0
COHERE_API_KEY=<cohere-key>

# ── Cache & Rate limit ────────────────────────────
CACHE_ENABLED=true
RATE_LIMIT_ENABLED=true
```

> ⚠️ **Không commit `.env`** — file đã được gitignore. Không dán key thật vào `.env.example`.

---

## 4. Chạy

### 4.1 Backend (API + static)

```bash
uvicorn app.main:app --reload --port 8000
```

- Backend: http://localhost:8000
- Chat UI: http://localhost:8000 (serve từ `app/static/`, build sẵn)

### 4.2 Admin Dashboard

`/admin` — theo dõi chỉ số vận hành (KPI, biểu đồ request/latency, realtime, phân bổ intent, bảng logs + feedback 👍/👎).

### 4.3 Frontend (React — sửa/builder lại)

Source code nằm ở `frontend/` (Vite + React + recharts + zustand):

```bash
cd frontend
npm install
npm run build      # output → app/static/
# hoặc:
npm run dev        # dev server hot-reload
```

> `app/static/` là bản build đã đóng gói; `frontend/` là source để phát triển.

---

## 5. Kiến trúc

```
vivu/
├── .env / .env.example
├── requirements.txt
├── pyproject.toml                    # ruff config (line-length 120, select E/F)
├── .github/workflows/ci.yml          # CI (lint + test offline)
│
├── app/
│   ├── main.py                       # FastAPI, mount routers + static
│   ├── config.py                     # Settings (load .env, unify OPENAI key)
│   ├── tracing.py                    # Phoenix tracing instrumentation
│   ├── agent/
│   │   ├── agent_loop.py             # run / run_stream (graph orchestration)
│   │   ├── graph.py / edges.py       # LangGraph (classify→call_tools→generate→validate→respond)
│   │   ├── graph_state.py            # AgentState (history, current_context, cache_hit…)
│   │   ├── classifier.py             # regex: MODEL_RE, VERSION_ALIASES, normalize_model
│   │   ├── llm.py                    # LLM client + stream_chat_with_fallback
│   │   ├── history.py / intent.py    # multi-turn history + intent (hybrid rule/LLM)
│   │   ├── decision.py               # DecisionLog schema + reason codes + assess_evidence
│   │   ├── tools.py                  # data tools (get_specs/get_price/get_colors/…)
│   │   ├── prompts.py / context_builder.py
│   │   ├── semantic_prefilter.py     # embedding similarity (optional)
│   │   └── nodes/                    # classify, call_tools, generate, validate, respond, …
│   ├── api/
│   │   ├── chat.py                   # /api/chat, /api/chat/stream, /api/logs
│   │   ├── metrics.py                # /api/admin/metrics/* (overview/timeseries/intents/logs/feedback/realtime)
│   │   ├── health.py                 # /healthz, /ready, /api/health
│   │   └── admin_prompts.py          # /api/admin/prompts/*
│   ├── core/
│   │   ├── retrieval.py              # hybrid search (dense + sparse + RRF + rerank)
│   │   ├── cache.py                  # tool cache + embedding/hybrid cache + data_version + invalidation
│   │   ├── memory.py                 # session store + long-term memory (Redis, fail-open)
│   │   ├── session_store.py          # session backing (feature/admin)
│   │   ├── rate_limit.py             # rate limit helpers
│   │   ├── telemetry.py              # request_metrics (+ migrate cột idempotent)
│   │   ├── db.py / prompt_manager.py
│   └── static/                       # Frontend build (React) — serve bởi backend
│
├── frontend/                         # React source (Admin Dashboard + Chat UI)
│   └── src/{pages/admin,components,store,api}
│
├── scripts/
│   ├── run_pipeline.py               # data pipeline orchestrator
│   ├── ingest/postgres_ingest.py     # ingest → PostgreSQL (specs/colors/options/price)
│   ├── ingest/vector_ingest.py       # ingest → Qdrant
│   ├── ingest/sparse_ingest.py       # sparse index (BM25)
│   ├── version_manager.py            # promote/rollback data version
│   ├── cache_admin.py                # QL cache Redis (stats/clear/version)
│   └── eval/ …                       # eval runner, smoke, benchmark
│
├── eval/
│   ├── smoke_test.csv                # smoke cases (golden expected decision)
│   └── benchmark/ …                  # golden set + benchmark runner
│
├── data/
│   ├── clean/v2/                     # data hiện tại (versioned)
│   │   ├── postgres/{specs,colors,options,edition,price_list}.csv
│   │   ├── vector/{vivu_product_info,vivu_policy,vivu_maintenance}.jsonl
│   │   └── sparse_index.json
│   ├── model_data/                   # spec CSV per model (vf2…vf9)
│   └── raw_pdf/                      # brochure PDF text
│
└── docs/                             # GUIDE, CACHING_DESIGN, DATA_PIPELINE, ADMIN_DASHBOARD…
```

---

## 6. API endpoints

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/chat` | Chat (sync, trả full response) |
| POST | `/api/chat/stream` | Chat streaming (SSE) |
| GET | `/api/logs` | Logs session hiện tại |
| GET | `/api/logs/export` | Export logs JSONL |
| GET | `/api/admin/metrics/overview` | KPI tổng quan |
| GET | `/api/admin/metrics/timeseries` | Request/latency/cost theo giờ |
| GET | `/api/admin/metrics/intents` | Phân bổ intent |
| GET | `/api/admin/metrics/logs` | Request logs chi tiết |
| POST | `/api/admin/metrics/feedback` | Ghi 👍/👎 (rating 1/-1) |
| GET | `/api/admin/metrics/realtime` | Requests/phút gần đây |
| GET | `/healthz` / `/ready` / `/api/health` | Health probe |
| GET | `/api/admin/prompts/*` | Prompt management |

---

## 7. Cache & Memory (Redis)

| Tầng | Key | TTL | Ý nghĩa |
|---|---|---|---|
| Session history | `session:{sid}:history` | 6h | multi-turn (LIST, RPUSH+LTRIM) |
| Session context | `session:{sid}:context` | 6h | model/version/topic (fallback ellipsis) |
| Long-term memory | `user:{uid}:profile` | 30d | fact/preference theo user |
| Tool cache | `cache:{dv}:{specs,colors,options,models}` | 6–24h | key theo entity |
| Embedding | `emb:{model}:{sha1}` | 7d | deterministic |
| Hybrid search | `hs:{dv}:…:{collections}` | 2h | full pipeline |
| KB search | `cache:kb:{dv}:…` | 2h | search_knowledge_base |
| Dedupe | `dedup:{sha1}` | 1h | chống trùng message_id |
| Rate limit | `rl:s:{sid}` / `rl:ip:{ip}` | 10s/60s | chống spam |

Nguyên tắc:
- **Fail-open**: Redis tắt → trả default (history rỗng, miss cache), không crash.
- **`data_version()`** đọc `ingest_version.is_current` (memo 60s) → promote v2→v3 tự đổi cache key.
- **Không cache giá/khuyến mãi** (volatile) — luôn query trực tiếp.
- QL cache tay: `python scripts/cache_admin.py {stats|clear|version}`.

---

## 8. Data pipeline (tóm tắt)

```bash
python scripts/run_pipeline.py                # crawl → clean → ingest end-to-end
python scripts/ingest/postgres_ingest.py      # ingest specs/colors/options/price → PG
python scripts/ingest/vector_ingest.py        # ingest chunks → Qdrant
python scripts/version_manager.py status      # xem version đang active
python scripts/version_manager.py promote --version <version>   # kích hoạt data version mới
```

- Promote/rollback tự invalidate cache (Redis) + đổi `data_version`.
- Dữ liệu active theo `ingest_version.is_current` trong PostgreSQL.

---

## 9. Eval

```bash
# Smoke test (golden decision trong eval/smoke_test.csv)
python scripts/eval/smoke_test.py

# Eval full qua API
python scripts/eval_runner.py --input eval/smoke_test.csv --output eval/eval_report.jsonl

# Benchmark
python eval/benchmark/run_benchmark.py
```

---

## 10. Lint, Test & CI

```bash
# Lint + format (ruff)
python -m ruff check app/ scripts/ tests/
python -m ruff format --check app/ scripts/ tests/

# Tests (chạy như script — không cần Docker/DB cho group classify)
python tests/test_classify.py
python tests/test_classify_intro.py
python tests/test_version_leak.py
python tests/test_redis_cache.py     # cần Redis/PG (integration)
python tests/test_cache_memory.py    # cần Redis/PG (integration)
```

CI (`.github/workflows/ci.yml`) chạy tự động khi push `main`, `chore/ci`, `feature/*`, `fix/*`, `multi-turn-cache-redis`:
- `lint` job: `ruff check .` + `ruff format --check`
- `test` job: classify/intro/version-leak tests + smoke import (offline, không cần DB)

---

## 11. Test queries tham khảo

| Query | Decision | Route |
|---|---|---|
| `VF 2 có mấy chỗ ngồi?` | answer | nội_thất → get_specs |
| `VF 8 đi được bao nhiêu km?` | clarify (missing_version) | phạm_vi_di_chuyển (version-dependent) |
| `giới thiệu về vf2` | answer | tổng_quan (giá + spec then chốt + màu) |
| `so sánh vf5 vf7 và vf8` | answer | so_sánh (cross-model) |
| `so sánh vf8 eco và plus` | answer | phiên_bản (version-pair) |
| `VF 9 có camera 360 không?` | answer | an_toàn (safety + adas) |
| `còn màu nào khác?` (follow-up) | answer | màu_sắc (qua current_context) |

---

## 12. Lỗi thường gặp

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `400 Unrecognized request arguments: reasoning_effort` | gửi param reasoning cho model OpenAI không phải reasoning | đã xử lý ở `llm.py`/`llm_extra_kwargs` — kiểm tra model name |
| Redis `Connection refused` | `REDIS_URL` sai / Redis không chạy | app vẫn chạy (fail-open), check `.env` `REDIS_URL` |
| `Connection refused` PostgreSQL | sai `POSTGRES_URL`/`PG_DSN` | check `.env` |
| `Connection refused` Qdrant | sai `QDRANT_URL`/`QDRANT_API_KEY` | check `.env` |
| `403 Forbidden` OpenAI | sai `OPENAI_API_KEY` | check `.env` |
| `ModuleNotFoundError: ragas` | chưa cài | `pip install ragas datasets` |
| `normalize_model not found` (cũ) | import thiếu | đã thêm `normalize_model` vào `app/agent/classifier.py` |
| Phoenix không cần | tracing mặc định tắt | set `PHOENIX_ENABLED=true` nếu muốn |

---

## 13. Tracing (optional)

```env
PHOENIX_ENABLED=true
```

```bash
python -m phoenix.server.main serve   # UI tại http://localhost:6006
```

Phoenix capture: OpenAI call (LLM + embedding), latency, token usage, input/output.