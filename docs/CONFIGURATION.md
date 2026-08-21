# Cấu hình môi trường (.env) — Tài liệu Chi Tiết

Toàn bộ biến môi trường dùng trong nhánh `feature/admin`. File gốc: `.env` (gitignored), template: `.env.example`.

---

## 1. LLM & Embedding (một key OpenAI duy nhất)

| Biến | Bắt buộc | Mặc định | Mô tả |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ (hoặc fallback cũ) | — | Key chính. Nếu trống, fallback `OPENROUTER_API_KEY` → `DEEPINFRA_API_KEY` (migration) |
| `OPENAI_BASE_URL` | — | `https://api.openai.com/v1` | Endpoint OpenAI-compatible (đổi được nếu dùng proxy/OpenRouter) |
| `LLM_MODEL` | — | `gpt-4o-mini` | Model chat. Tự động strip prefix `openai/...` |
| `LLM_FALLBACK_MODEL` | — | (từ `DEEPINFRA_FALLBACK_MODEL`) | Model thay thế khi model chính lỗi **trước token đầu** |
| `OPENAI_EMBED_MODEL` | — | `text-embedding-3-small` | Model embedding (strip prefix) |
| `EMBEDDING_DIM` | — | `1536` | Chiều vector embedding |

Token limits (dùng bởi `app/agent/llm.py`):
`LLM_MAX_OUTPUT_TOKENS=1024`, `LLM_TOOL_CALL_MAX_TOKENS=512`, `LLM_USER_INPUT_MAX_TOKENS=4000`, `LLM_INPUT_MAX_TOKENS=8000`.

> Lưu ý: `OPENROUTER_*` / `DEEPINFRA_*` vẫn được đọc làm fallback cho tương thích, nhưng pipeline data + LLM hiện **thuần OpenAI** (`lib/openai_client.py`, `backend/lib/openai_client.py` — trước là `openrouter.py`, còn shim deprecation).

---

## 2. Database

| Biến | Mô tả |
|---|---|
| `POSTGRES_URL` | Canonical (chuỗi `postgresql+asyncpg://...` hoặc `postgresql://...`) |
| `PG_DSN` | Fallback (Neon cũ dùng `PG_DSN=...?sslmode=require`) |
| `QDRANT_URL` | `http://localhost:6333` (local) hoặc URL cloud |
| `QDRANT_API_KEY` | Key Qdrant cloud |
| `QDRANT_COLLECTION` | `vivu_specs` (not used riched) |

---

## 3. Redis (cache + session + rate limit)

| Biến | Mô tả |
|---|---|
| `REDIS_URL` | Có thể là `rediss://default:<token>@<region>.upstash.io:6379` **hoặc** https REST URL Upstash `https://<name>-<id>.upstash.io` + `REDIS_TOKEN` (code tự chuyển sang rediss) |
| `REDIS_TOKEN` / `UPSTASH_REDIS_REST_TOKEN` | Token Upstash (nếu `REDIS_URL` là https REST) |
| `CACHE_ENABLED` | `true` — bật tầng cache Redis |
| `RATE_LIMIT_ENABLED` | `true` — bật rate limit 2 lớp |

Cache tầng (xem `docs/CACHE_SYSTEM.md`): `ans:` 30m, `tool:price` 15m, `tool:specs/colors` 24h, `hs:` 2h, `emb:` 7d, `dedup:` 1h, `rl:` theo cửa sổ.

---

## 4. Rerank / Cohere

| Biến | Mô tả |
|---|---|
| `RERANK_ENABLED` | `true` |
| `RERANK_MODEL` | Mặc định `cohere` |
| `RERANK_TOP_K` | `20` |
| `COHERE_API_KEY` | Key nếu dùng Cohere rerank |

---

## 5. Telemetry & Admin

| Biến | Mô tả |
|---|---|
| `METRICS_ENABLED` | `true` — ghi `request_metrics` |
| `ADMIN_API_KEY` | **Không cần dùng** — admin mở hoàn toàn theo yêu cầu |
| `USD_VND_EXCHANGE_RATE` | `25400.0` — quy đổi cost |
| `APP_VERSION` | `v1.0.0` — ghi vào `prompt_version` / health |

---

## 6. Tracing (tuỳ chọn)

| Biến | Mô tả |
|---|---|
| `PHOENIX_ENABLED` | `false` (mặc định) — bật Phoenix tracing |
| `LANGSMITH_API_KEY` / `LANGCHAIN_TRACING_V2` | LangSmith (optional) |

---

## 7. Ví dụ `.env` tối thiểu chạy demo

```env
# LLM
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small

# DB
PG_DSN=postgresql://user:pass@host:5432/db?sslmode=require
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# Redis (Upstash)
REDIS_URL=rediss://default:<token>@host.upstash.io:6379
REDIS_TOKEN=
CACHE_ENABLED=true
RATE_LIMIT_ENABLED=true

# Telemetry
METRICS_ENABLED=true
USD_VND_EXCHANGE_RATE=25400.0
```