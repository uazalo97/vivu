# Multi-turn Memory + Redis Cache

> Trạng thái: **HOÀN THÀNH** — multi-turn memory + tool cache + long-term memory + Upstash cloud.
> Các tầng cache bổ sung theo `CACHING_DESIGN.md` / `CACHE_SYSTEM.md`.

## 1. Tổng quan

Triển khai xong 3 mục tiêu từ plan `plans/redis-memory-cache.md`, mở rộng theo `CACHING_DESIGN.md` (Upstash Redis):

| Mục tiêu | Trạng thái |
|---|---|
| Multi-turn memory (session từ RAM/client → Redis) | ✅ |
| Tool-result cache (entity-keyed + TTL phân tầng) | ✅ |
| Long-term memory (fact/preference theo user) | ✅ |
| Upstash Redis cloud (`rediss://` TLS) | ✅ |
| Embedding + Hybrid search + KB cache | ✅ |
| Rate limit + Dedupe | ✅ |

---

## 2. Kiến trúc cache

| Tầng | Key | TTL | Module |
|---|---|---|---|
| Session history | `session:{sid}:history` (Redis LIST) | 6h | `app/core/memory.py` |
| Session context | `session:{sid}:context` (hash) | 6h | `app/core/memory.py` |
| Long-term memory | `user:{uid}:profile` (hash) | 30d | `app/core/memory.py` |
| Tool cache | `cache:{dv}:specs/colors/options:{model}:...` | 6h–24h | `app/core/cache.py` |
| Embedding | `emb:{embed_model}:{sha1(text)}` | 7d | `app/core/retrieval.py` |
| Hybrid search | `hs:{dv}:{sha1(q)}:{model}:{top_k}:{rerank}` | 2h | `app/core/retrieval.py` |
| KB search | `cache:kb:{dv}:{model}:{sha1(q)}` | 2h | `app/core/cache.py` |
| Dedupe | `dedup:{sha1(session|message_id)}` | 1h | `app/api/chat.py` |
| Rate limit | `rl:s:{sid}:{window}` / `rl:ip:{ip}:{window}` | 10s/60s | `app/api/chat.py` |

**Nguyên tắc bất biến:**

- **Fail-open**: Redis down → trả default (`history=[]`, miss cache), không crash.
- **`data_version()`** đọc LIVE `ingest_version.is_current` (memo 60s) → promote v2→v3 ≤60s mọi key tự đổi, không cần restart. Trả `"unknown"` khi PG unreachable → miss cache, không phục vụ stale.
- **Key theo entity** (model/version/category), không key theo raw text — tránh cache bẩn khi paraphrase.
- **Không cache** giá/khuyến mãi (data volatile) — luôn query trực tiếp.
- **TTL phân tầng**: càng gần tiền → TTL càng ngắn (giá: không cache, specs 6h, dimension 24h, list_models 1h, emb 7d, hs/kb 2h).

---

## 3. Luồng multi-turn

```
Client POST /api/chat {message, session_id?, message_id?}
   │  dedupe (SET NX) → rate limit (INCR+EXPIRE) → sinh session_id nếu thiếu
   ▼
load_session(session_id) → {history (LIST), current_context (hash)}
   ▼
classify ← current_context fallback cho ellipsis ("còn màu nào khác?")
   │        intro/broad query → answer "tổng_quan" (giá + spec then chốt + màu + phiên bản)
   ▼
call_tools → *_cached (specs/colors/options/list_models/kb)
   │         giá/khuyến mãi query trực tiếp (không cache)
   ▼
generate → validate → respond (AgentResult + sources + cache_hit)
   ▼
save_turn (RPUSH + LTRIM atomic) + update_current_context + save_user_fact
```

- **`session_id`**: Optional, sinh `uuid4` nếu thiếu, trả về client qua `ChatResponse.session_id` / event `{"type":"session"}`.
- **`current_context`** (hash: `model_code`, `version`, `last_topic`) — "phao cứu sinh" khi history bị cắt, update từ entity thật (không từ query text).
- **Long-term memory**: `save_user_fact(user_id, ...)` keyed by user_id (chưa có auth → fallback `user_id = session_id`).

---

## 4. Bug đã tìm & fix (khi trace + test full flow)

| # | Bug | Mức | Fix |
|---|---|---|---|
| 1 | `app/api/chat.py` gán lại `req_id/t0/session_id` sau rate-limit/dedupe | CRITICAL | Xóa block trùng ở cả 2 endpoint |
| 2 | Tool cache key thiếu `data_version` → promote không tự invalidate | HIGH | Thêm `{dv}` vào key |
| 3 | `hs:` key lộ raw text | MED | Dùng thuần `sha1` |
| 4 | Stream `intent` telemetry luôn "general" | MED | `intent = category` từ classify event |
| 5 | `save_turn` read-modify-write mất lượt (10 turn → 8 msg) | HIGH | Chuyển sang Redis LIST `RPUSH` + `LTRIM` |
| 6 | `_openrouter_embed` async hóa làm gãy `_rerank_texts` (sync) | HIGH | Giữ sync + thêm async `_embed_texts_cached` riêng |
| 7 | Cold-start `data_version="unknown"` → cache miss vĩnh viễn | HIGH | `await data_version()` trước khi build key (bỏ `_dv_prefix` sync) |
| 8 | `assess_evidence` branch `get_colors/get_options` không set `has_direct` → ellipsis bị refuse | HIGH | Set `has_direct=True` + xóa branch get_colors thứ 2 (dead code) |
| 9 | `get_colors` citation `source_url=""` → thiếu link click | MED | Lấy `result.get("source_url")` + đồng schema dict với các tool khác |

---

## 5. Test

**17/17 unit tests** (`tests/test_cache_memory.py`):

- Session: roundtrip, sliding-window (MAX_TURNS), update context non-null, concurrent save (không mất lượt), LTM facts.
- Tool cache: miss→hit, version/model isolation, invalidate_model/all.
- Embedding + hybrid cache: miss/set/hit, key theo query+model+top_k+rerank.
- data_version, rate limit (10/10s + 30/60s), dedupe, classify context fallback + history-wins, unicode normalization, empty session.

**E2E flow** (`tests/test_e2e_flow.py`, hạ tầng thật LLM + PG + Qdrant):

- Turn 1 `"VF 8 có mấy màu?"` → answer
- Turn 2 repeat → `cache_hit=True, cache_type=colors`
- Turn 3 `"còn màu nào khác?"` → answer (qua current_context) + citation clickable

**Intro/overview**: `"giới thiệu về vf2"` → answer đầy đủ (giá, công suất, pin, kích thước, màu) thay vì clarify.

**Smoke contract**: cập nhật `TF-CL-03-T1` → `answer`/`sufficient_direct_evidence` (CSV parse đúng 25 rows).

---

## 6. Files

**Mới**: `app/core/memory.py`, `app/core/cache.py`, `scripts/cache_admin.py`, `tests/test_cache_memory.py`, `tests/test_e2e_flow.py`, `tests/test_classify_intro.py`

**Sửa**: `app/config.py`, `app/core/retrieval.py`, `app/api/chat.py`, `app/agent/agent_loop.py`, `app/agent/graph_state.py`, `app/agent/nodes/{classify,call_tools,respond}.py`, `app/agent/decision.py`, `app/agent/tools.py`, `scripts/ingest/postgres_ingest.py`, `eval/smoke_test.csv`, `.env.example`, `docker-compose.yml`, `requirements.txt`

---

## 7. Invalidation

- `set_current(version)` / rollback (promote) → `invalidate_all()` (SCAN + delete, reset data_version memo).
- `upsert_specs` full-refresh → `invalidate_all()` (specs lookup không version).
- Manual: `python scripts/cache_admin.py {stats|clear|version}` (SCAN, không `KEYS`).

---

## 8. Giới hạn (có chủ đích) & next steps

- **`ans:` answer cache** (single-turn, 30p, SSE replay) — **PHASE SAU**, chưa implement.
- **Semantic cache** (B) — PHASE SAU (guard cứng entities/intent + Qdrant collection riêng).
- **Fixed-window rate limit** (chưa token-bucket Lua) — đủ dev/demo.
- **Dedupe không có ans cache** → trùng luôn 409; frontend nên sinh `message_id` mới cho retry chính đáng (`app/static/index.html` chưa gửi `message_id`).
- `save_turn` dùng pipeline (RPUSH+LTRIM) — atomic từng lệnh; thứ tự có thể lệch nhẹ khi 2 request cùng session đồng thời (không mất lượt).

---

**Cập nhật**: 2026-08-19