# Báo cáo Audit Hệ thống Caching — Vivu (VinFast AI Assistant)

> **Ngày:** 2026-08-26
> **Phạm vi:** Toàn bộ repo `D:/FULearning/vin/vivu` — 4 luồng trinh sát song song
> **Người tổng hợp:** quanly (harness Oh My Pi) — 4 agents: CacheCoreLayer, CachePipelineData, CacheRedisMultiTurn, CacheFrontendInfra
> **Số file đã đọc:** ~90+ (app/core, app/agent, app/api, lib, backend/lib, scripts/harness, docs, plans, tests, frontend, infra)
> **Docs gốc tham chiếu:** `docs/CACHE_SYSTEM.md`, `docs/CACHING_DESIGN.md`, `docs/MULTI_TURN_CACHE_REDIS.md`, `CACHING_DESIGN.md`, `plans/redis-memory-cache.md`

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Luồng request end-to-end](#2-luồng-request-end-to-end)
3. [Chi tiết từng tầng cache](#3-chi-tiết-từng-tầng-cache)
4. [Cách lưu trữ (Storage)](#4-cách-lưu-trữ-storage)
5. [Key namespace toàn hệ thống](#5-key-namespace-toàn-hệ-thống)
6. [Data version & Invalidation](#6-data-version--invalidation)
7. [Cấu hình & Feature flags](#7-cấu-hình--feature-flags)
8. [Fail-open & Resilience](#8-fail-open--resilience)
9. [Observability / Metrics / Admin](#9-observability--metrics--admin)
10. [Frontend / Build / Infra caching](#10-frontend--build--infra-caching)
11. [Pipeline caching (offline)](#11-pipeline-caching-offline)
12. [Test coverage map](#12-test-coverage-map)
13. [Gap / Rủi ro / Đề xuất](#13-gap--rủi-ro--đề-xuất)
14. [Phụ lục: File inventory & Cheat-sheet](#14-phụ-lục)

---

## 1. Tổng quan kiến trúc

Vivu dùng **5 tầng cache runtime (Redis) + 1 tầng cache offline (SQLite) + 2 tầng memo in-memory + 1 tầng client**. Không có CDN/Service Worker/React Query.

```mermaid
flowchart TB
    subgraph Client ["Client (Browser)"]
        LS["localStorage - zustand persist"]
        SID["session_id uuid"]
    end

    subgraph Edge ["API Edge - app/api/chat.py"]
        RL["Rate Limit - rl:s and rl:ip"]
        DD["Dedupe - dedup sha1"]
    end

    subgraph Session ["Session Layer - app/core/memory.py"]
        HIST["session history - LIST 10 turns"]
        CTX["session context - HASH 6h"]
        LTM["user profile - HASH 30d"]
    end

    subgraph ToolCache ["Tool Cache - app/core/cache.py"]
        PRICE["price - 15m"]
        SPECS["specs colors options - 24h"]
        LISTM["list_models - 1h"]
        KB["kb - 2h"]
    end

    subgraph Retrieval ["Retrieval - app/core/retrieval.py"]
        EMB["emb - 7d embedding vector"]
        HS["hs - 2h dense sparse rerank"]
        QDRANT[("Qdrant Cloud")]
    end

    subgraph Answer ["Answer Cache - thiet ke chua active"]
        ANS["ans - 30m single-turn only"]
    end

    subgraph Offline ["Offline Pipeline - lib/vector_cache.py"]
        VEC[("SQLite cache.sqlite")]
        RAW["data_v2 raw pdf csv"]
        CANON["data_v2 canonical"]
        RETR["data_v2 retrieval jsonl"]
    end

    Postgres[("Postgres Neon - ingest_version is_current")]

    LS --> RL
    RL --> DD
    DD --> HIST
    HIST --> CTX
    CTX --> LTM
    LTM --> PRICE
    PRICE --> SPECS
    SPECS --> LISTM
    LISTM --> KB
    KB --> EMB
    EMB --> HS
    HS --> QDRANT
    QDRANT --> ANS
    VEC -.-> QDRANT
    RAW -.-> VEC
    CANON -.-> VEC
    RETR -.-> HS
    KB -.-> Postgres
```

**Bảng tóm tắt tầng:**

| # | Tầng | Prefix | TTL | Store | File chính | Trạng thái |
|---|------|--------|-----|-------|------------|------------|
| 1 | Rate Limit (session) | `rl:s:` | 10s window | Redis INCR+EXPIRE | `app/api/chat.py` | ✅ active |
| 2 | Rate Limit (IP) | `rl:ip:` | 60s window | Redis INCR+EXPIRE | `app/api/chat.py` | ✅ active |
| 3 | Dedupe | `dedup:` | 1h | Redis SET NX EX | `app/api/chat.py` | ✅ active |
| 4 | Session history | `session:{sid}:history` | 6h | Redis LIST | `app/core/memory.py` | ✅ active |
| 5 | Session context | `session:{sid}:context` | 6h | Redis HASH | `app/core/memory.py` | ✅ active |
| 6 | LTM profile | `user:{uid}:profile` | 30d | Redis HASH | `app/core/memory.py` | ✅ active (uid=session_id khi chưa auth) |
| 7 | Tool price | `cache:{dv}:price:*` | 15m | Redis JSON | `app/core/cache.py` | ✅ active |
| 8 | Tool specs/colors/options | `cache:{dv}:specs/colors/options` | 24h | Redis JSON | `app/core/cache.py` | ✅ active |
| 9 | Tool list_models | `cache:{dv}:list_models` | 1h | Redis JSON | `app/core/cache.py` | ✅ active |
| 10 | KB (search_kb_cached) | `cache:kb:{dv}:*` | 2h | Redis JSON | `app/core/cache.py` | ✅ active |
| 11 | Hybrid search | `hs:{dv}:*` | 2h | Redis JSON | `app/core/cache.py` + `retrieval.py` | ✅ active |
| 12 | Embedding | `emb:{model}:{sha1}` | 7d | Redis JSON | `app/core/cache.py` + `retrieval.py` | ✅ active |
| 13 | Answer single-turn | `ans:{dv}:*` | 30m | Redis JSON | thiết kế `docs/CACHING_DESIGN.md` | ⏸ chưa implement (hằng số ANS_TTL tồn tại) |
| 14 | System prompt memo | in-memory dict | 5m | Python dict | `app/agent/prompts.py` | ✅ active |
| 15 | Tool schema memo | in-memory dict | 5m | Python dict | `app/agent/schemas.py` | ✅ active |
| 16 | Data version memo | in-memory dict | 60s | Python dict | `app/core/cache.py` | ✅ active |
| 17 | Sparse index memo | in-memory dict | process lifetime | Python dict | `app/core/retrieval.py` | ✅ active |
| 18 | VectorCache offline | `data/.vector_cache/cache.sqlite` | vô hạn (theo embed_model) | SQLite BLOB | `lib/vector_cache.py` | ⚠️ đứt gãy harness mới |
| 19 | RateLimit in-memory | per-IP token bucket | sliding | Python dict + semaphore | `app/core/rate_limit.py` | ✅ active (song song Redis RL) |
| 20 | Frontend localStorage | `vivu_session_id` + `vivu_chat_storage` | forever | browser | `frontend/src/session.ts`, `store/chatStore.ts` | ✅ active |
| 21 | Build artifact | content-hash filename | immutable | Vite + StaticFiles | `frontend/vite.config.ts`, `app/main.py` | ✅ active |

---

## 2. Luồng request end-to-end

### 2.1 Non-stream (`POST /api/chat`)

```
Client POST {message, session_id?, message_id?, history?}
  │
  ├─ 1) gen req_id = req_{uuid8}
  ├─ 2) session_id ??= uuid4()
  ├─ 3) _rate_limit_check(sid, ip)
  │     ├─ get_redis() == None → fail-open passthrough
  │     ├─ rl:s:{sid}:{now//10} INCR+EXPIRE 10 → >10 → 429
  │     └─ rl:ip:{ip}:{now//60} INCR+EXPIRE 60 → >30 → 429
  ├─ 4) _dedup_check(sid, mid)  (nếu có message_id)
  │     ├─ get_redis() == None → True (fail-open)
  │     └─ SET dedup:{sha1(sid|mid)} 1 NX EX 3600 → None = 409 "Tin nhắn trùng lặp."
  ├─ 5) load_session(sid)  ── asyncio.gather ──
  │     ├─ LRANGE session:{sid}:history 0 -1 → json.loads per element
  │     │    └─ fallback: GET (legacy JSON-string key)
  │     └─ HGETALL session:{sid}:context → _loads per value
  │     └─ merge: request.history ?? loaded history
  ├─ 6) AgentLoop.run(message, history, current_context)
  │     └─ LangGraph: classify → call_tools → generate → validate → respond
  │         ├─ classify: dùng current_context cho ellipsis ("còn màu nào khác?")
  │         ├─ call_tools:
  │         │   ├─ branch: utility / cross_model / single_model
  │         │   ├─ _cached_call(get_price_cached etc.) parallel gather
  │         │   │   ├─ data_version() → build key → _get_json → hit/miss
  │         │   │   └─ miss → PG query → _set_json TTL tương ứng
  │         │   └─ search_kb_cached → get_hybrid_cached? → hit return : hybrid_search
  │         │       └─ hybrid_search:
  │         │           ├─ get_hybrid_cached(query,model_id,top_k,skip_rerank) → hit return
  │         │           ├─ parallel: _embed_texts_cached([query]) + _query_to_sparse(query)
  │         │           │   └─ _embed_texts_cached: get_embedding_cached per text → miss → thread_pool(_openrouter_embed_api batch 100) → set_embedding_cached fire-and-forget
  │         │           ├─ dense search per DENSE_COLLECTIONS via QdrantREST.search (executor gather)
  │         │           ├─ sparse search + _resolve_sparse_texts
  │         │           ├─ RRF fusion k=60
  │         │           ├─ rerank (Cohere API hoặc CrossEncoder fallback) via executor
  │         │           └─ shape + set_hybrid_cached fire-and-forget
  │         └─ generate: build_structured_context(tool_results) + history_context(4 turns) → truncate_messages → llm.stream_chat_with_fallback → final_response
  │              [ans: cache CHƯA móc ở đây — PHASE SAU]
  ├─ 7) persist (sau graph):
  │     ├─ save_turn(sid, user_msg, assistant_msg) pipeline: RPUSH 2 + LTRIM -20 + EXPIRE 6h
  │     ├─ update_current_context(sid, model_code, version, topic) HSET non-null + EXPIRE
  │     └─ save_user_fact(uid, field, value) HSET + EXPIRE 30d  (uid = session_id)
  └─ 8) record_metric (telemetry) → log_metric_background
        └─ prompt_tokens estimate len(words)*1.4 + history, completion, t_retrieve/generation, ttft, cache_hit/type, model_code/version, chunks
```

### 2.2 Stream (`POST /api/chat/stream`)

Tương tự nhưng:

- Trả `StreamingResponse(text/event-stream)` với `data: {type:session}` mở đầu.
- `async for event in agent.run_stream(...)` yield `status/answer/sources/done/tool_call/cache/decision`.
- Track `ttft` (first token), `accumulated_text`, `decision/intent/tools_used/cache`.
- `finally: asyncio.create_task(_persist())` — không await để đóng SSE nhanh.

### 2.3 Answer cache khi active (thiết kế)

> **Hiện tại `ANS_TTL=1800` tồn tại trong `app/core/cache.py:44` nhưng không có `make_answer_key/get/set` trong `agent_loop.py`. Test `test_ans_cache.py`/`test_cache_impl.py` expect hit 50% nhanh hơn sẽ fail cho tới khi implement.**

Luồng dự kiến (theo `docs/CACHING_DESIGN.md §4.1` + `docs/CACHE_SYSTEM.md`):

```
if history == [] && session_id && intent not in {greeting,clarify,out_of_scope}:
    key = ans:{dv}:{prompt_hash}:{llm_model}:{sha1(entities|norm_query)}
    if GET key hit:
        SSE replay: status → answer → sources → done (không tool_call)
    else:
        run graph → SET key ex 30m
else:
    miss (multi-turn → summary nondeterministic)
```

### 2.4 Pipeline ingestion (offline, 5 phase)

```
run_pipeline.py → harness/pipeline.py:main()
  Phase1 Configurator (ConfiguratorExtractor: edition/price/colors/options)
  Phase2 Brochures (batch_runner → orchestrator 9 PDF: Inspect→Plan→Extract→Normalize→Crop→Validate→Assemble)
  Phase3 Web (WebTextExtractor: data_v2/raw/web_policies + web_deposit)
  Phase4 Consolidate (QdrantSink.consolidate_all_chunks dedup chunk.id + PostgresSink.consolidate_all_specs dedup seen_*)
  Phase5 Ingest (PostgresSink.ingest_to_postgres is_current=false + QdrantSink.ingest_to_qdrant embed batch 64 upsert 100)
  Promote: version_manager.swap_aliases (Qdrant alias) + set_current PG is_current flip
```

---

## 3. Chi tiết từng tầng cache

### 3.1 Tầng trung tâm — `app/core/cache.py` (7 TTL + data_version + SCAN)

**File:** `app/core/cache.py` (372 dòng)
**Import core:** `from app.core.memory import get_redis`, `from app.config import settings`

**TTL phân tầng (dòng 36-44):**

```python
SPECS_TTL = 24*3600      # 86400
COLORS_TTL = 24*3600
OPTIONS_TTL = 24*3600
LIST_MODELS_TTL = 1*3600 # 3600
KB_TTL = 2*3600           # 7200
TOOL_PRICE_TTL = 15*60    # 900  — ngắn nhất vì giá biến động
EMBEDDING_TTL = 7*24*3600 # 604800 — deterministic
HYBRID_TTL = 2*3600       # 7200
ANS_TTL = 30*60           # 1800 — chưa dùng
CACHE_TTL_BY_TOPIC = {
  "thông_số": 24h, "kích_thước": 24h, "an_toàn": 24h,
  "giá": 15m, "khuyến_mãi": 15m, "list_models": 1h
}
_SPEC_CATEGORY_TTL = {"dimension": 24h}
```

Lý do volatility: giá/khuyến_mãi 15m < list_models 1h < kb/hs 2h < specs/colors 24h < embedding 7d.

**Data version (dòng 69-93):**

```python
_dv_cache: str = "unknown"
_dv_cache_time: float = 0.0
_DV_TTL = 60

async def data_version() -> str:
    # SELECT version FROM ingest_version WHERE is_current LIMIT 1
    # via app.core.db.get_pool().fetchval
    # memo 60s, except → return _dv_cache (cũ) hoặc "unknown"
```

- Promote v2→v3 lan toả ≤60s, key mới `cache:v3:...` tự miss, key cũ mồ côi chết theo TTL.
- `invalidate_all()` reset `_dv_cache_time=0` để key mới sinh ngay.
- Fail-open: PG unreachable → trả `"unknown"` → miss cache (thà chậm hơn stale).

**Normalization (dòng 97-111):**

```python
def _norm(v): return "all" if not v else v.strip().lower().replace(" ","")
def _norm_query(q): NFC → lower → re.sub([^\\w\\s]," ") → collapse whitespace → strip
def _sha1(text): return sha1(text.encode()).hexdigest()[:16]
# KB dùng sha256[:16]
```

- `_norm` bỏ toàn bộ space → `VF 8` và `vf8` cùng key.
- `_norm_query` bỏ punctuation → `"VF8 giá?"` == `"vf8 gia"`.

**Key builders (dòng 114-148):**

```python
_specs_key(dv, model, version, category) = f"cache:{dv}:specs:{_norm(model)}:{_norm(version)}:{_norm(category)}"
_colors_key(dv, model, version)          = f"cache:{dv}:colors:{_norm(model)}:{_norm(version)}"
_options_key(dv, model, version)         = f"cache:{dv}:options:{_norm(model)}:{_norm(version)}"
_list_models_key(dv)                     = f"cache:{dv}:list_models"
# price inline trong get_price_cached:
price_key                                = f"cache:{dv}:price:{_norm(model)}:{_norm(version)}"
_kb_key(dv, query, model_id)            = f"cache:kb:{dv}:{_norm(model_id)}:{sha256(_norm_query(query))[:16]}"
_emb_key(text)                           = f"emb:{settings.openai_embed_model}:{_sha1(text)}"
_hs_key(dv, query, model_id, top_k, skip_rerank) = f"hs:{dv}:{_sha1(_norm_query(query))}:{_norm(model_id)}:{top_k}:{int(skip_rerank)}"
```

**Redis ops fail-open (dòng 151-202):**

```python
async def _get_json(key):  r=get_redis(); if not r: return None; try: raw=r.get(key); return json.loads(raw) except: return None
async def _set_json(key,value,ttl): if not settings.cache_enabled: return; if not r: return; r.set(key, json.dumps(value,ensure_ascii=False), ex=ttl)
async def _delete(key): r.delete(key)
async def _delete_by_pattern(pattern): async for k in r.scan_iter(match=pattern, count=500): pipeline.delete(k)
```

- `count=500` tránh block, không dùng `KEYS`.
- `settings.cache_enabled` gate toàn cục.

**Cached wrappers — trả `(data, hit_bool)` hoặc `dict`:**

| Function | TTL | Gọi `_get_json` trước PG/hybrid? |
|----------|-----|-----------------------------------|
| `get_price_cached(model,version)` | 15m | yes |
| `get_specs_cached(model,version,category)` | 24h / dimension 24h | yes |
| `get_colors_cached(model,version)` | 24h | yes |
| `get_options_cached(model,version)` | 24h | yes |
| `list_models_cached()` | 1h | yes |
| `search_kb_cached(query,model_id)` | 2h | yes → miss gọi `hybrid_search(top_k=5)` rồi shape + SET |
| `get_embedding_cached(text)` | 7d | yes |
| `set_embedding_cached(text,vec)` | 7d | — |
| `get_hybrid_cached(query,model_id,top_k,skip_rerank)` | 2h | yes (trong retrieval.py trước Qdrant) |
| `set_hybrid_cached(...)` | 2h | — |

Tất cả đều `await data_version()` trước khi build key (trừ `emb:`).

**Invalidation:**

```python
async def invalidate_entity(cache_key): await _delete(cache_key)
async def invalidate_model(model_code):  # SCAN 3 prefix
    for prefix in ["specs","colors","options"]:
        await _delete_by_pattern(f"cache:*:{prefix}:{_norm(model_code)}:*")
async def invalidate_all():  # SCAN 3 namespace + reset memo
    await _delete_by_pattern("cache:*")
    await _delete_by_pattern("hs:*")
    await _delete_by_pattern("cache:kb:*")
    _dv_cache_time = 0
```

Hook bởi `scripts/cache_admin.py` và `version_manager` (docs).

**Thread safety:** Không lock; `_dv_cache` race benign; Redis ops atomic per-command.

---

### 3.2 Session + LTM — `app/core/memory.py`

**File:** `app/core/memory.py` (203 dòng)
**Constants:** `SESSION_TTL=timedelta(hours=6)`, `MAX_TURNS=10` (=20 messages), `LTM_TTL=timedelta(days=30)`

**Singleton Redis:**

```python
_client = None; _client_ok = True
def get_redis():
    if _client is not None: return _client
    try:
        _client = redis.asyncio.Redis.from_url(settings.redis_url, decode_responses=True,
            socket_connect_timeout=5, socket_timeout=5, retry_on_timeout=True)
    except: _client_ok=False; return None
```

- `settings.redis_url` đã được `app/config.py` chuyển `https://` Upstash → `rediss://`.
- Fail-open: import fail → `_client=None`, mọi caller → miss/default.

**Keys:**

| Key | Type | Value |
|-----|------|-------|
| `session:{sid}:history` | LIST | mỗi element = `json.dumps({role,content})` |
| `session:{sid}:context` | HASH | `{model_code, version, last_topic}` (field non-null) |
| `user:{uid}:profile` | HASH | arbitrary facts, value = `json.dumps` nếu non-string |

**API:**

```python
async def load_session(sid) -> {"history": [...], "current_context": {...}}:
    history, ctx = await asyncio.gather(
        r.lrange(_history_key(sid), 0, -1),   # → json.loads per element
        r.hgetall(_context_key(sid))          # → _loads per value
    )
    # fallback legacy: nếu key cũ là JSON-string → r.get + json.loads

async def save_turn(sid, user_msg, assistant_msg):
    pipe = r.pipeline()
    pipe.rpush(_history_key(sid), json.dumps({role:"user",content:user_msg}), json.dumps({role:"assistant",content:assistant_msg}))
    pipe.ltrim(_history_key(sid), -MAX_TURNS*2, -1)  # sliding window 20
    pipe.expire(_history_key(sid), SESSION_TTL)
    pipe.expire(_context_key(sid), SESSION_TTL)
    await pipe.execute()

async def update_current_context(sid, model_code, version, topic):
    # chỉ HSET field non-null để giữ field cũ
    if model_code: hset(context_key, "model_code", model_code)
    ...

async def load_user_facts(uid): return {k: _loads(v) for k,v in (await r.hgetall(_profile_key(uid))).items()}
async def save_user_fact(uid, field, value): r.hset(profile_key, field, json.dumps(value) if not str else value); r.expire(..., LTM_TTL)
```

- `MAX_TURNS=10` → LTRIM `-20` giữ 10 cặp gần nhất, chống mất turn đồng thời nhờ pipeline atomic per-command.
- `update_current_context` chỉ update từ entity thật (classifier), không từ query text.
- `user_id` khi chưa có auth → `session_id` (chat.py `uid = session_id`).

**Wired trong `app/api/chat.py`:**

- `load_session(sid)` trước `AgentLoop.run` (merge với `request.history`).
- `save_turn + update_current_context + save_user_fact` sau graph (extract `model_code/version` từ tool result, `topic` từ decision).

---

### 3.3 Retrieval — `app/core/retrieval.py` (591 dòng)

**Collections:** `DENSE_COLLECTIONS = env QDRANT_DENSE_COLLECTIONS else [vivu_product_info, vivu_policy, vivu_maintenance]`, `SPARSE_COLLECTION=sparse`

**Sparse index memo (dòng 60-160):**

- `_get_current_version_from_db()` psycopg2 sync `SELECT version WHERE is_current`.
- `_find_latest_sparse_index()` ưu tiên `data_v2/retrieval/sparse_index.json` → DB version path `data/clean/{ver}/sparse_index.json` → scan max version.
- `_load_sparse_index()` cache global `_sparse_index`, log src.
- `_query_to_sparse()` BM25: `tf Counter(tokenize query)`, `idf/k1=1.5/b=0.75/avgdl` từ index → `weight = idf*f*(k1+1)/(f+k1*(1-b+b*1/avgdl))`.

**Embedding (dòng 20-256):**

- `_get_embed_client()` singleton `OpenAI(api_key=settings.openai_api_key, base_url, max_retries 3 timeout 60)`.
- `_openrouter_embed_api(texts)` batch 100 `client.embeddings.create(model=openai_embed_model)`.
- `_embed_texts_cached(texts)` async: `get_embedding_cached` per text, uncached → `run_in_executor(_thread_pool 4)` → `create_task(set_embedding_cached)` fire-and-forget, return ordered results.

**QdrantREST (dòng 259-360):**

- `Session` pool 10, `api-key` header, `search(collection, vector, model_id, limit)` POST `/collections/{col}/points/search` filter `must model_id`, fallback bỏ filter nếu "Index required".
- `search_sparse` với `vector:{name:sparse, indices, values}`.
- `retrieve(collection, ids)` batch fetch.

**Reranker (dòng 362-411):**

- `CohereReranker("rerank-multilingual-v3.0")` POST `https://api.cohere.ai/v1/rerank`, fallback `CrossEncoder(settings.rerank_model)`.

**Fusion (dòng 414-433):**

- `_rrf_score=1/(60+rank)`, `_rrf_fusion` sum per id.

**`hybrid_search(query, model_id, top_k=5)` (dòng 498-591):**

```
0) get_hybrid_cached(...) → hit return
1) parallel: embed_task=_embed_texts_cached([query]) + sparse_task=run_in_executor(_query_to_sparse)
2) dense search parallel per collection via _dense_search executor gather, flatten
3) sparse search + _resolve_sparse_texts (fetch missing text từ dense via retrieve group by collection)
4) RRF fusion
5) rerank if enabled via executor, chỉ apply nếu any score>0
6) top_k shape {text,model_id,edition_id,text_type,source_type,source_url,page,score}
7) create_task(set_hybrid_cached(..., results)) fire-and-forget
```

- Dense/sparse/rerank đều qua `_thread_pool(4)` để không block event loop.
- `top_k` và `skip_rerank` nằm trong key `hs:` nên chỉnh tham số tự miss.

---

### 3.4 Tool execution — `app/agent/nodes/call_tools.py`

- `call_tools_node(state)` đọc `entities/category/query/model_code/version/model_codes`, `cache_hits:set`.
- Branch: `utility` → `_call_utility_tools` (static links, regex showroom/sạc), `cross_model` nếu `len(model_codes)>=2` hoặc `_distinct_models>=2` → `_call_cross_model_tools`, else `_call_model_tools`.
- `_cached_call(name, cache_type, func, *args, cache_hits)` → `data,hit=await func(*args)`, nếu hit add `cache_type` → return `{tool,result,success,cache_hit}`.
- `_call_model_tools` gather parallel: `get_price/colors/specs/options_cached` + `search_knowledge_base`.
- `_call_cross_model_tools`: per-model 4 cached calls + KB, fleet-wide 8 models *3 calls.
- Metrics: `CALL_TOOLS done X results in Yms cache_hits=[...]` → `graph_state.cache_hit/cache_type` → SSE `type:cache`.

---

### 3.5 Rate limit + Dedupe — `app/api/chat.py` + `app/core/rate_limit.py`

**`app/api/chat.py` (dòng 64-108):**

```python
_RATE_LIMIT_MSG = "Bạn gửi hơi nhanh, chờ vài giây rồi thử lại."
_DEDUP_MSG = "Tin nhắn trùng lặp."

async def _rate_limit_check(sid, ip):
    if not settings.rate_limit_enabled: return None
    r=get_redis(); if not r: return None  # fail-open
    now=int(time.time())
    k1=f"rl:s:{sid}:{now//10}"; c1=await r.incr(k1); if c1==1: await r.expire(k1,10); if c1>10: return _RATE_LIMIT_MSG
    k2=f"rl:ip:{ip}:{now//60}"; c2=await r.incr(k2); if c2==1: await r.expire(k2,60); if c2>30: return _RATE_LIMIT_MSG
    return None  # window cố định 10s/60s, không Lua

async def _dedup_check(sid, mid):
    if not mid: return True
    r=get_redis(); if not r: return True
    key=f"dedup:{sha1(f'{sid}|{mid}'.encode()).hexdigest()}"
    ok=await r.set(key,"1",nx=True,ex=3600)  # atomic NX
    return ok is not None  # True=mới, False=trùng→409
```

- `POST /api/chat` và `/api/chat/stream` đều check rate 429 và dedupe 409 trước khi vào graph.
- Frontend chưa gửi `message_id` (FRONTEND_PLAN ghi phase Redis) → dedupe chỉ active khi client gửi.
- Fail-open: Redis down → `return True/None` cho qua.

**`app/core/rate_limit.py` (in-memory layer bổ sung):**

- `_TokenBucket(tokens,last_refill,capacity,refill_rate)` `consume(now)` refill, `retry_after()`.
- `RateLimitMiddleware(BaseHTTPMiddleware)` per-IP bucket (capacity 60, refill ~1/s) → 429, `BackpressureMiddleware` semaphore concurrent (~100) → 503.
- `setup_rate_limiting(app)` add both. Song song với Redis RL ở chat.py.

---

### 3.6 In-memory memo (5m/60s)

**`app/agent/prompts.py` + `schemas.py`:**

```python
_prompt_cache, _prompt_cache_time, _CACHE_TTL=300
async def get_system_prompt():
    if time.time()-_prompt_cache_time < 300: return _prompt_cache
    row=await pool.fetchrow("SELECT prompt FROM prompt_registry WHERE is_active")
    _prompt_cache = format(SYSTEM_PROMPT, model_list); _prompt_cache_time=now
    # except: _prompt_cache_time = now-240  # TTL rút 60s
def get_prompt_hash(): return sha256(SYSTEM_PROMPT).hexdigest()[:12]
```

Tương tự `build_tool_schemas()` 300s. Invalidate bởi `PromptManager.invalidate_cache`.

**`app/core/cache.py` data_version memo 60s, `app/core/retrieval.py` sparse memo lifetime.**

---

### 3.7 Answer cache — thiết kế chưa active

Hằng số `ANS_TTL=1800` tồn tại. Theo `docs/CACHING_DESIGN.md §4.1` và `docs/CACHE_SYSTEM.md §1`:

- Điều kiện: `history==[] && session_id && intent not in {greeting,clarify,out_of_scope}`
- Key: `ans:{data_version}:{prompt_hash}:{llm_model}:{sha1(entities|norm_query)}` (prompt_hash 12 chars, llm_model, entities sorted).
- Value: `{response, sources, decision}`.
- TTL 30m, chỉ single-turn (multi-turn summary nondeterministic).
- SSE replay shape: `status → answer → sources → done` (không tool_call).
- Hook: đầu `AgentLoop.run_stream`, miss chạy graph rồi SET.

**Hiện trạng:** `app/agent/agent_loop.py` không có code này → test `test_ans_cache.py`/`test_cache_impl.py` expect hit sẽ fail.

---

### 3.8 Agent wiring liên quan

- `app/agent/graph.py`: `StateGraph(AgentState)` nodes `classify→call_tools→generate→validate→respond`.
- `app/agent/graph_state.py`: `AgentState TypedDict` có `cache_hit:bool`, `cache_type:str`, `t_retrieve_*`, `t_generate_*`.
- `app/agent/llm.py`: singleton `AsyncOpenAI`, `INPUT_MAX_TOKENS 8000`, `OUTPUT 1024`, `truncate_messages` giữ system+user cuối, `stream_chat_with_fallback` chain `[llm_model, fallback_model]`.
- `app/agent/history.py`: `WINDOW_TURNS=7`, `_MAX_MSG_CHARS user 4000 assistant 16000`, `MAX_HISTORY_TOKENS 30000`, `sanitize_history` filter role/merge dedup/drop incomplete.

---

## 4. Cách lưu trữ (Storage)

| Store | Vị trí | Format | Size ước tính | TTL/Eviction |
|-------|--------|--------|---------------|--------------|
| **Redis JSON** | Upstash Singapore (prod) / `redis:7-alpine --appendonly` (local) | `json.dumps(value, ensure_ascii=False)` per key `SET ex=ttl` | tool result ~1-5KB, hybrid ~10-50KB, embedding vector 1536 floats JSON ~15KB | TTL expiry, không LRU app-side |
| **Redis LIST** | `session:{sid}:history` | mỗi element `json.dumps({role,content})`, RPUSH+LTRIM | 20 msgs * ~500B = 10KB/session | EXPIRE 6h + LTRIM sliding |
| **Redis HASH** | `session:{sid}:context` | HSET field non-null `model_code/version/last_topic` | <1KB | EXPIRE 6h |
| **Redis HASH** | `user:{uid}:profile` | HSET json.dumps nếu non-string | <5KB | EXPIRE 30d |
| **Redis INCR** | `rl:s:{sid}:{window}` / `rl:ip:{ip}:{window}` | integer counter | 16B | EXPIRE 10s/60s |
| **Redis SET NX** | `dedup:{sha1}` | `"1"` | 16B | EXPIRE 1h |
| **SQLite BLOB** | `data/.vector_cache/cache.sqlite` gitignored | `array('f').tobytes()` 1536 floats ≈6KB/row, table `hash PK, collection, embed_model, dim, vector, created_at` index collection | 0.5-2GB tuỳ version | vô hạn, key theo embed_model, `INSERT OR REPLACE` |
| **In-memory dict** | Python process | `dict[str, Any]` + timestamp | <1MB | TTL 60s/300s/process lifetime |
| **Filesystem** | `data_v2/retrieval/*.jsonl`, `data_v2/structured/*.csv`, `data_v2/canonical/*.json` | JSONL/CSV git-tracked | 691 chunks master, sparse_index ~MB | theo version bump |
| **Browser** | `localStorage` | `vivu_session_id` uuid + `vivu_chat_storage` Zustand persist `{sessionId, messages[]}` | <100KB | forever (clearChat) |
| **Build** | `app/static/assets/index-{hash}.js` | Vite content-hash | ~500KB JS+CSS | immutable, ETag Starlette |

**Serialization chi tiết:**

- Redis: `decode_responses=True` → string, `_get_json` → `json.loads`, `_set_json` → `json.dumps(ensure_ascii=False)`. Không dùng `pickle`/`msgpack`.
- SQLite: `array('f')` 4 bytes/float → 6144 bytes/1536 dim, không nén thêm.
- Browser: `JSON.stringify` StoredMsg `id/role/content`.

---

## 5. Key namespace toàn hệ thống

| Namespace | Key format (chính xác code) | Ví dụ | TTL | File sinh |
|-----------|------------------------------|-------|-----|-----------|
| Tool specs | `cache:{dv}:specs:{norm(model)}:{norm(version)}:{norm(category)}` | `cache:v3:specs:vf8:eco:dimension` | 24h | `cache.py:_specs_key` |
| Tool colors | `cache:{dv}:colors:{norm(model)}:{norm(version)}` | `cache:v3:colors:vf8:plus` | 24h | `cache.py:_colors_key` |
| Tool options | `cache:{dv}:options:{norm(model)}:{norm(version)}` | `cache:v3:options:vf8:all` | 24h | `cache.py:_options_key` |
| Tool price | `cache:{dv}:price:{norm(model)}:{norm(version)}` | `cache:v3:price:vf8:eco` | 15m | `cache.py:get_price_cached` inline |
| List models | `cache:{dv}:list_models` | `cache:v3:list_models` | 1h | `cache.py:_list_models_key` |
| KB cache | `cache:kb:{dv}:{norm(model_id)}:{sha256(_norm_query)[:16]}` | `cache:kb:v3:vf8:a1b2c3d4e5f6a7b8` | 2h | `cache.py:_kb_key` |
| Embedding | `emb:{openai_embed_model}:{sha1(text)[:16]}` | `emb:text-embedding-3-small:9f8e7d6c5b4a3f2e` | 7d | `cache.py:_emb_key` |
| Hybrid | `hs:{dv}:{sha1(_norm_query)[:16]}:{norm(model_id)}:{top_k}:{int(skip_rerank)}` | `hs:v3:abc123def456:vf8:5:0` | 2h | `cache.py:_hs_key` |
| Answer (design) | `ans:{dv}:{prompt_hash}:{llm_model}:{sha1(entities\|norm_query)[:16]}` | `ans:v3:a1b2c3d4e5f6:deepseek-v3:9f8e7d6c5b4a3f2e` | 30m | `CACHING_DESIGN.md` |
| Dedupe | `dedup:{sha1(f"{sid}\|{mid}")}` | `dedup:abc123...` | 1h | `chat.py:_dedup_check` |
| Rate session | `rl:s:{sid}:{now//10}` | `rl:s:uuid-123:171400000` | 10s | `chat.py:_rate_limit_check` |
| Rate IP | `rl:ip:{ip}:{now//60}` | `rl:ip:127.0.0.1:28566666` | 60s | `chat.py:_rate_limit_check` |
| Session history | `session:{sid}:history` | `session:abc-123:history` | 6h | `memory.py:_history_key` |
| Session context | `session:{sid}:context` | `session:abc-123:context` | 6h | `memory.py:_context_key` |
| LTM profile | `user:{uid}:profile` | `user:abc-123:profile` | 30d | `memory.py:_profile_key` |

**Normalization rule chung:**

```python
_norm(v):        strip → lower → replace(" ","") → "all" if empty
_norm_query(q):  NFC normalize → lower → re.sub([^\\w\\s]," ") → collapse whitespace → strip
_sha1(text):     sha1(utf-8)[:16]
_kb digest:      sha256(_norm_query)[:16]
```

Quy tắc entity: `model_code` từ `classifier._detect_model` deterministic, sort khi multi-model.

---

## 6. Data version & Invalidation

### 6.1 Nguồn truth

```sql
SELECT version FROM ingest_version WHERE is_current LIMIT 1
-- table: ingest_version(version, is_current bool unique where true, prev_version, pg_rows_upserted, vector_chunks_added, created_at)
-- các bảng child: edition.version, price_list.version, car_specs.ingest_version, car_colors/options.ingest_version
```

- `app/core/cache.py:data_version()` memo 60s qua `app.core.db.get_pool().fetchval`.
- `app/core/retrieval.py:_get_current_version_from_db()` psycopg2 sync fallback.
- `app/agent/decision.py:_get_data_snapshot_id()` đọc is_current + created_at cho telemetry.
- `scripts/harness/config.py` + `scripts/config.py` định nghĩa version hardcode, `docs/VERSIONING.md`.

### 6.2 Lan toả promote

```
Promote v3:
  1) Qdrant: swap_aliases() UpdateCollectionAliases DeleteAlias+CreateAlias {collection}__v3 → alias
  2) PG: set_current(v3) flip is_current (đúng 1 row true)
  3) ≤60s: _dv_cache expiry → key mới cache:v3:... auto miss → key v2 mồ côi → TTL expiry
```

Không cần restart app. `invalidate_all()` reset `_dv_cache_time=0` để sinh key mới ngay.

### 6.3 Invalidation thủ công

**`app/core/cache.py`:**

```python
invalidate_entity(key)      # DEL 1 key
invalidate_model(model)     # SCAN cache:*:{specs|colors|options}:{model}:*  (3 pattern, count 500)
invalidate_all()            # SCAN cache:* + hs:* + cache:kb:* + reset memo
```

**`scripts/cache_admin.py` (CLI):**

```bash
python scripts/cache_admin.py stats                # SCAN vivu:* đếm per prefix cache:/hs:/emb:/ans:/session:/user:/rl:/dedup:
python scripts/cache_admin.py clear                # SCAN + UNLINK toàn bộ
python scripts/cache_admin.py clear --prefix ans:  # chỉ ans:
python scripts/cache_admin.py version              # SELECT is_current
# dùng SCAN count 500, UNLINK non-blocking (không KEYS/FLUSHDB)
```

**`scripts/version_manager.py`:**

- `swap_aliases()`, `set_current()`, `migrate_v1` copy unversioned → `__v1`, `_backfill_cache()` Qdrant → SQLite.
- Hook `invalidate_all()` sau promote (docs, belt & suspenders).

### 6.4 Pipeline invalidation (offline)

- Collection vật lý `{col}__{version}` + alias, DELETE child-first (price→edition→specs/colors/options) rồi INSERT parent-first.
- Qdrant stale cleanup khi `not recreate`: `scroll existing ids` → `stale_ids = existing - new` → DELETE batch 100.
- `seen_chunk_ids`, `seen_ed`, `seen_prices`, `seen_specs`, `seen_colors` dedup trước insert (unique constraint).
- `data_v2/canonical/*.json` + `artifacts/*/pages|crops/` gitignored ~250MB, `recreate` drop+rebuild.

---

## 7. Cấu hình & Feature flags

**`app/config.py` Settings (đọc `.env` + `os.environ`, env ưu tiên):**

| Env | Default | Mô tả |
|-----|---------|-------|
| `REDIS_URL` | `redis://localhost:6379/0` | Upstash `https://...` + `REDIS_TOKEN` → tự chuyển `rediss://default:{token}@{host}:6379`, thiếu token → localhost |
| `REDIS_TOKEN` / `UPSTASH_REDIS_REST_TOKEN` | `""` | token cho https conversion |
| `CACHE_ENABLED` | `true` | gate `_set_json` → false thì vẫn GET nhưng không SET |
| `RATE_LIMIT_ENABLED` | `true` | gate `_rate_limit_check` |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `DEEPINFRA_API_KEY` | `""` | unified key (alias giữ tương thích) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | |
| `LLM_MODEL` | `gpt-5.6-luna` | strip prefix `openai/` |
| `OPENAI_EMBED_MODEL` / `OPENROUTER_EMBED_MODEL` / `EMBEDDING_MODEL` | `text-embedding-3-small` | |
| `EMBEDDING_DIM` | `1536` | |
| `POSTGRES_URL` / `PG_DSN` | `postgresql+asyncpg://vivu:vivu@localhost:5432/vivu` | |
| `QDRANT_URL` / `QDRANT_API_KEY` / `QDRANT_COLLECTION` | `http://localhost:6333` | |
| `QDRANT_DENSE_COLLECTIONS` | `vivu_product_info,vivu_policy,vivu_maintenance` | |
| `RERANK_ENABLED` / `RERANK_MODEL` / `COHERE_API_KEY` | `true` / `cohere` | |
| `METRICS_ENABLED` / `ADMIN_API_KEY` | `true` | |
| `LLM_FALLBACK_MODEL` | `""` | chain trong llm.py |
| `LLM_MAX_OUTPUT_TOKENS` etc. | `1024/512/4000/8000` | |

**Infra compose:**

- `docker-compose.yml`: `redis:7-alpine --appendonly yes` expose 6379 + volume `redis_data`.
- `docker-compose.prod.yml`: không chạy redis local, dùng Upstash cloud (NEON+Qdrant Cloud+Upstash).
- `docker-compose.local.yml`: bỏ redis (chỉ qdrant+postgres) — dev không cache.
- `Dockerfile`: `pip install --no-cache-dir` + `COPY app/ + data_v2/retrieval/sparse_index.json`.

---

## 8. Fail-open & Resilience

| Failure | Behavior | Code |
|---------|----------|------|
| `redis.asyncio` import fail | `get_redis() → None`, mọi `_get_json → None` (miss), `_set_json` no-op, session `load_session → {history:[],context:{}}` | `memory.py:33-54`, `cache.py:154-175` |
| Redis down mid-request | `except Exception: return None/0`, log `debug "cache get/set failed (fail-open)"`, request vẫn chạy (chậm hơn) | `cache.py:151-202`, `memory.py:82-203` |
| Redis down rate/dedupe | `_rate_limit_check → None` (cho qua), `_dedup_check → True` (cho qua) | `chat.py:70-108` |
| PG unreachable `data_version()` | return `_dv_cache` cũ hoặc `"unknown"` → miss cache, thà chậm hơn stale | `cache.py:75-93` |
| `CACHE_ENABLED=false` | `_set_json` early return, `_get_json` vẫn thử (đọc stale) → effectively read-only | `cache.py:167` |
| Upstash free 10K cmd/ngày cạn | docs ước ~10 cmd/req → ~1000 req/ngày, cạn thì miss pass-through | `CACHING_DESIGN.md §1` |
| `decode_responses` JSON fail | `_loads` try json.loads → fallback raw string | `memory.py:57-64` |
| Pipeline Qdrant/PG fail | `is_current=false` safe mode, promote best-effort (Qdrant trước PG), `recover` command | `harness/pipeline.py`, `version_manager.py` |
| Thread pool | `_thread_pool 4` (retrieval) + embed workers 8 (`openai_client.py`) | `retrieval.py:495`, `lib/openai_client.py` |

**Không có dead-cooldown 30s trong code hiện tại** (docs ghi nhưng code chỉ `try/except` per-op, không flag `_client_ok` cooldown).

**Eviction:** Redis TTL expiry duy nhất, không LRU app-side; `SCAN + UNLINK` cho manual clear.

**Thread safety:** Redis `INCR`, `SET NX`, `pipeline RPUSH/LTRIM/EXPIRE`, `SCAN count 500` atomic per-command; Python memo `_dv_cache` race benign.

---

## 9. Observability / Metrics / Admin

**`app/core/telemetry.py`:**

- Table `request_metrics(request_id, session_id, query_text, intent, decision, model_used, prompt_version, prompt_tokens, completion_tokens, ttft_ms, ttot_ms, total_latency, latency_retrieval/generation, cache_hit, cache_type, tools_used, status_code, model_code, model_version, retrieval_status, chunks, reasoning_tokens, cost_usd/vnd, user_feedback)`.
- `MODEL_PRICING` per 1M tokens, `calculate_cost`, `record_metric` insert, `log_metric_background(create_task)` fail-open.
- Aggregates: `get_metrics_overview/timeseries/intents/logs/realtime` với filter `cache_hit`.

**`app/agent/graph_state.py` → `app/api/chat.py`:**

- `AgentState.cache_hit:bool`, `cache_type:str`, `t_retrieve_*`, `t_generate_*` → `AgentResult` → `decision_log` → `record_metric`.
- `call_tools.py` track `cache_hits:set` → `state.cache_hit/cache_type` → SSE `type:cache` event.

**`app/api/metrics.py` + `app/api/health.py`:**

- `GET /api/metrics/overview/timeseries/intents/logs/realtime` (admin, `?cache_hit` filter).
- `GET /api/health` (PG pool stats).

**`scripts/cache_admin.py`:**

- `stats` SCAN count per prefix `[cache:, hs:, emb:, ans:, session:, user:, rl:, dedup:]`.
- `clear --prefix ans:` SCAN+UNLINK.
- `version` SELECT is_current.

**Logging:**

```python
logger.debug("cache get/set failed (fail-open): %s", e)
logger.info("CALL_TOOLS done %s results in %sms cache_hits=[...]")
```

**Cost estimate (docs):** `llm_extra_kwargs("luna") → reasoning_effort none` giảm TTFT.

---

## 10. Frontend / Build / Infra caching

### 10.1 Client-side (2 cơ chế song song, nhưng chỉ 1 active)

**Legacy `frontend/src/session.ts` (hook path cũ):**

```ts
SID_KEY='vivu_session_id'  // uuid
HIST_KEY='vivu_history'    // StoredMsg[] {id,role,content}
getSessionId(), getHistory(), pushMessage(), removeMessageById(), getWindow() slice(-14)=7 turns, clearSession()
// dùng bởi hooks/useChat.ts state machine idle→sending→streaming→done|error, AbortController, contentRef flush
```

**Hiện tại `frontend/src/store/chatStore.ts` (widget path — đang dùng trong App.tsx):**

```ts
zustand + persist middleware, name='vivu_chat_storage', partialize {sessionId, messages}
sessionId = crypto.randomUUID(), messages init WELCOME_MESSAGE
clearChat() reset, send flow HISTORY_LIMIT=6 (frontend/src/config.ts), chatStream + fallback chatOnce
```

**Không có:** sessionStorage, IndexedDB, Cookie cache, Service Worker, Workbox, React Query/TanStack Query/SWR/staleTime/queryClient.

### 10.2 HTTP headers / Middleware

- `app/main.py`: `CORSMiddleware(allow_origins=["*"])` + `StaticFiles(directory=app/static/assets)` mount `/assets` + SPA fallback `FileResponse`.
- Không có middleware tự set `Cache-Control/ETag/CDN/SWR`; `FileResponse` Starlette tự ETag theo file nhưng không `Cache-Control: immutable`.
- `/api/chat/stream` `StreamingResponse(media_type="text/event-stream")` không set `Cache-Control: no-cache`.
- `app/core/rate_limit.py` 2 middleware: `RateLimitMiddleware` (token bucket) + `BackpressureMiddleware` (semaphore ~100 → 503).

### 10.3 Build cache

- `frontend/vite.config.ts`: `react()` + `tailwindcss()`, alias `@` → `./src`, proxy `/api → VITE_API_TARGET||localhost:8000`, không `cacheDir/manualChunks/serviceWorker`.
- `frontend/package.json`: `vite ^5.4.11`, không `react-query/swr/workbox`.
- Output `app/static/assets/index-{hash}.js/css` content-hash cache-busting immutable, `index.html` reference crossorigin.
- `Dockerfile`: layer cache `COPY requirements` trước `pip install`.
- `.github/workflows/ci.yml`: `setup-python cache:pip`, không Vite/Docker cache, concurrency cancel-in-progress.

### 10.4 Infra

- `docker-compose.yml` volume `redis_data` là cache duy nhất.
- `langgraph.json` không có cache config.

**Kết luận:** Frontend/HTTP/CDN không có tầng cache first-party ngoài localStorage + Vite hash.

---

## 11. Pipeline caching (offline)

### 11.1 VectorCache SQLite — `lib/vector_cache.py` (86 dòng, cũng ở `backend/lib/vector_cache.py`)

```python
CACHE_PATH = data/.vector_cache/cache.sqlite  # gitignored
_SCHEMA: hash TEXT PK, collection, embed_model, dim, vector BLOB, created_at; index collection

def content_hash(text, structured, embed_model):
    return sha1(f"{embed_model}\x1f{text}\x1f{json.dumps(structured,sort_keys)}")

class VectorCache:
    get(h): SELECT vector → array('f').frombytes → list  (hits/misses counter)
    put(h, collection, embed_model, vec): array('f',vec).tobytes() → INSERT OR REPLACE
```

- Incremental embed: chunk không đổi → hit → 0 API call; re-run cùng version `embedded=0 cached=2212` (5s, 0 token); đổi 1 chunk `embedded=1`.
- `version_manager.py::_backfill_cache()` migrate v1 Qdrant vectors → put cache.
- **Gap:** Harness mới `scripts/harness/sinks/qdrant.py:ingest_to_qdrant` gọi `embed_client.embeddings.create(batch=64)` trực tiếp, **không qua VectorCache** → re-run cùng version tốn token. Pipeline cũ vẫn dùng cache.

### 11.2 Không có

- **HTTP fetch cache:** `scripts/crawl.py:fetch()` retry 3 lần, HEADERS Chrome, **không disk/memory ETag/If-Modified-Since/fetch-skip** → crawl tải lại full PDF mỗi lần.
- **Sparse BM25:** rebuild CPU ~1s, không cache.
- **Pipeline artifact TTL:** không, chỉ version bump + manual clear.

### 11.3 Pipeline flow (5 phase, `scripts/harness/pipeline.py`)

```
Phase1 Configurator (edition/price/colors/options) → Phase2 Brochures (batch_runner orchestrator 9 PDF) 
→ Phase3 Web (WebTextExtractor) → Phase4 Consolidate (QdrantSink.consolidate_all_chunks seen_chunk_ids dedup + PostgresSink.consolidate_all_specs seen_* dedup) 
→ Phase5 Ingest (PG is_current=false + Qdrant batch 64 upsert 100, sparse vocab/df/idf)
--resume via phase_status__<version>.json, --recreate drop+rebuild, --skip-* preview
```

Output track Git: `data_v2/structured/*.csv/json`, `data_v2/retrieval/*.jsonl`, `sparse_index.json`; gitignored: `data_v2/canonical/*.json`, `artifacts/*/pages|crops/` ~250MB.

---

## 12. Test coverage map

| Test file | Cover gì (liên quan cache) | Kỳ vọng |
|-----------|-----------------------------|---------|
| `tests/test_cache_memory.py` (17 tests) | session roundtrip/sliding_window/concurrent_save/context_non_null, LTM facts, tool miss→hit/version isolation/invalidate_model+all, embedding/hybrid miss-set-hit + key theo query+model+top_k+rerank, data_version memo, rate limit dedupe, classify context fallback + history-wins, unicode NFC, empty session | Redis mock hoặc real, tất cả fail-open |
| `test_redis_cache.py` (root, bản đầy đủ) | session isolation, MAX_TURNS+1 boundary, concurrent LIST RPUSH, LTM isolation, tool version_isolation + data_version_autoinvalidate, embedding roundtrip, hybrid key components, rate_limit 10/10s window boundary, dedupe same_msg_id, classify ellipsis/topic fallback, fresh_model_query re-clarify, an_toàn/safety, data_version returns+memoised, norm consistency | — |
| `tests/test_multi_turn.py` | offline stub `llm_classify_fallback`, turn-by-turn với history, assert decision/reason_code/model resolve/version/topic | cover recency, chuyển VF6↔VF8, ellipsis |
| `test_dedupe_tool_cache.py` | `set_nx_json` True→False→True, `_check_dedupe` False→True, tool cache hit/miss | `cache.enabled`, SET NX atomic |
| `test_cache_impl.py` | `make_answer_key` deterministic, `AgentLoop.run` miss 6-10s → hit 0.05s 99% tiết kiệm, multi-turn không cache | expect `ans:` active → hiện fail |
| `test_ans_cache.py` | `make_answer_key/_is_cacheable/flushdb ans:*` + `AgentLoop.run` hit → nhanh 50% | hiện fail (chưa implement) |
| `tests/test_e2e_flow.py` | LLM+PG+Qdrant thật: turn1 VF8 màu → answer, turn2 repeat → cache_hit=colors, turn3 ellipsis → current_context | — |
| `eval/smoke_test.csv` + `benchmark/` | 691 chunks golden, metrics latency | không test cache trực tiếp |

---

## 13. Gap / Rủi ro / Đề xuất

### 13.1 Đã chốt vs chưa xong

| Mục | Trạng thái | Chi tiết |
|-----|------------|----------|
| Upstash provider Singapore ~60ms, free 10K cmd/ngày (~1000 req/ngày) | ✅ chốt | `CACHING_DESIGN.md §1`, `app/config.py` https→rediss conversion |
| Exact-key cache A (tool/hs/emb/price) | ✅ xong | `app/core/cache.py` + `retrieval.py` |
| Answer cache ans: single-turn | ⏸ hằng số tồn tại, logic chưa | `ANS_TTL=1800` có nhưng `agent_loop.py` chưa móc, test sẽ fail |
| Semantic cache B | ⏸ phase sau | guard cứng entities+intent+keywords+dv+prompt_hash+llm_model rồi cos_sim ≥0.97, Qdrant `vivu_cache` collection riêng |
| Frontend message_id → dedupe | ⚠️ backend sẵn, frontend chưa gửi | `api.ts` chưa sinh uuid per message |
| VectorCache harness mới | ⚠️ đứt gãy | `lib/vector_cache.py` offline OK nhưng `harness/sinks/qdrant.py` không dùng → re-embed tốn token |

### 13.2 Rủi ro cụ thể

1. **Dead-cooldown 30s ghi docs nhưng không code:** docs nói "Redis down → dead-cooldown 30s" nhưng `memory.py` chỉ `try/except` per-op, không flag cooldown → mỗi request vẫn thử tạo Redis client. Rủi ro nhỏ (timeout 5s).
2. **2 lớp rate limit song song không đồng bộ:** `app/core/rate_limit.py` in-memory token bucket (60/1s + semaphore 100) và `app/api/chat.py` Redis INCR (10/10s + 30/60s) chạy cùng lúc, threshold khác nhau, có thể 429 lẫn lộn. Nên chọn 1 hoặc align.
3. **Salt `int(skip_rerank)` trong hs: key:** bool → int đúng nhưng docs ghi `hs:{dv}:{sha1}:{model}:{top_k}` không có rerank flag, dễ hiểu nhầm khi debug.
4. **No HTTP fetch cache:** `scripts/crawl.py` tải lại 9 PDF full mỗi lần, không ETag → lãng phí bandwidth.
5. **Upstash free limit 10K cmd/ngày:** nếu traffic >1000 req/ngày sẽ throttle; docs gợi ý tắt tool:* trước rồi hs:.
6. **LTM keyed by session_id (chưa auth):** `user:{uid}` với `uid=session_id` → mỗi tab là 1 user khác, không persist cross-device.
7. **Vite build không immutable header:** `FileResponse` không `Cache-Control: immutable` cho assets hash → browser vẫn revalidate.
8. **SSE không `no-cache`:** `StreamingResponse` không set `Cache-Control: no-store` → proxy có thể buffer.

### 13.3 Đề xuất (không thay đổi scope hiện tại, để xử lý từng phần 1 như yêu cầu)

- **P1:** Móc `ans:` single-turn vào `agent_loop.py::run_stream` (đã có hằng số, chỉ thêm `get/set` + SSE replay + `_is_cacheable`).
- **P1:** Wire `VectorCache` vào `harness/sinks/qdrant.py:ingest_to_qdrant` (check `get` trước `embed_api`, `put` sau).
- **P2:** Frontend `api/chat.ts` sinh `message_id: crypto.randomUUID()` per send để dedupe active.
- **P2:** `cache_admin.py` hook vào `version_manager promote` (belt & suspenders đã ghi docs nhưng chưa auto).
- **P3:** Align 2 lớp rate limit hoặc bỏ `RateLimitMiddleware` nếu đã có Redis RL.
- **P3:** Thêm `Cache-Control: immutable` cho `/assets/*` và `no-store` cho `/api/chat/stream`.

---

## 14. Phụ lục

### 14.1 File inventory đã đọc (90+)

**Core / API / Agent (30):**
`app/config.py`, `app/main.py`, `app/tracing.py`, `app/core/cache.py`, `app/core/memory.py`, `app/core/retrieval.py`, `app/core/session_store.py`, `app/core/rate_limit.py`, `app/core/db.py`, `app/core/telemetry.py`, `app/core/prompt_manager.py`, `app/api/chat.py`, `app/api/health.py`, `app/api/metrics.py`, `app/agent/graph.py`, `app/agent/graph_state.py`, `app/agent/agent_loop.py`, `app/agent/tools.py`, `app/agent/llm.py`, `app/agent/prompts.py`, `app/agent/schemas.py`, `app/agent/classifier.py`, `app/agent/context_builder.py`, `app/agent/history.py`, `app/agent/decision.py`, `app/agent/nodes/call_tools.py`, `app/agent/nodes/generate.py`, `app/agent/nodes/classify.py`, `app/agent/nodes/respond.py`, `app/agent/nodes/validate.py`

**Lib / Backend (6):**
`lib/vector_cache.py`, `lib/openai_client.py`, `lib/openrouter.py`, `backend/lib/vector_cache.py`, `backend/lib/openai_client.py`

**Scripts / Pipeline (18):**
`scripts/run_pipeline.py`, `scripts/crawl.py`, `scripts/version_manager.py`, `scripts/schemas.py`, `scripts/config.py`, `scripts/cache_admin.py`, `scripts/harness/pipeline.py`, `scripts/harness/config.py`, `scripts/harness/schemas.py`, `scripts/harness/orchestrator.py`, `scripts/harness/batch_runner.py`, `scripts/harness/sinks/qdrant.py`, `scripts/harness/sinks/postgres.py`, `scripts/harness/chunker/semantic.py`, `scripts/harness/extractors/vision.py`, `scripts/harness/extractors/pymupdf.py`, `scripts/harness/extractors/configurator.py`, `scripts/harness/extractors/web_text.py`

**Docs / Plans (8):**
`docs/CACHE_SYSTEM.md`, `docs/CACHING_DESIGN.md`, `docs/MULTI_TURN_CACHE_REDIS.md`, `docs/PIPELINE_FLOW.md`, `docs/DATA_PIPELINE.md`, `docs/DATA_SCHEMA_SPEC.md`, `docs/VERSIONING.md`, `plans/redis-memory-cache.md`, `plans/multi_attribute_graph_solutions.md`, `CACHING_DESIGN.md`, `CACHE_SYSTEM.md`

**Tests (7):**
`tests/test_redis_cache.py`, `tests/test_cache_memory.py`, `tests/test_multi_turn.py`, `test_redis_cache.py`, `test_cache_impl.py`, `test_ans_cache.py`, `test_dedupe_tool_cache.py`

**Frontend / Infra (12):**
`frontend/src/session.ts`, `frontend/src/store/chatStore.ts`, `frontend/src/hooks/useChat.ts`, `frontend/src/api.ts`, `frontend/src/api/chat.ts`, `frontend/src/config.ts`, `frontend/vite.config.ts`, `frontend/package.json`, `app/static/index.html`, `docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.local.yml`, `Dockerfile`, `.github/workflows/ci.yml`, `langgraph.json`

**Data (5):**
`data_v2/retrieval/all_models_chunks.jsonl`, `data_v2/retrieval/sparse_index.json`, `data_v2/structured/all_models_specs.json`, `data/.vector_cache/cache.sqlite` (gitignored, check existence)

### 14.2 Grep keywords đã quét

`redis`, `REDIS_URL`, `cache`, `TTL`, `CACHE_TTL`, `emb:`, `hs:`, `ans:`, `dedup:`, `rl:`, `InMemoryCache`, `LRU`, `vector_cache`, `content_hash`, `Cache-Control`, `ETag`, `CDN`, `service worker`, `SWR`, `React Query`, `staleTime`

### 14.3 Cheat-sheet lệnh

```bash
# Stats & clear
python scripts/cache_admin.py stats
python scripts/cache_admin.py clear --prefix ans:
python scripts/cache_admin.py clear --prefix hs:
python scripts/cache_admin.py clear

# Version
python scripts/cache_admin.py version
psql $POSTGRES_URL -c "SELECT version,is_current FROM ingest_version"

# Pipeline
python scripts/harness/pipeline.py --help
python scripts/harness/pipeline.py --resume
python scripts/harness/pipeline.py --recreate

# Test cache
pytest tests/test_cache_memory.py -v
pytest test_redis_cache.py -v
pytest tests/test_multi_turn.py -v

# Redis shell
redis-cli -u $REDIS_URL SCAN 0 MATCH "cache:*" COUNT 100
redis-cli -u $REDIS_URL --scan --pattern "hs:*" | xargs redis-cli -u $REDIS_URL UNLINK
```

### 14.4 Tài liệu đã tổng hợp

- `docs/CACHING_DESIGN.md` — bản chốt Upstash, TTL, key, wiring, phase sau semantic
- `docs/CACHE_SYSTEM.md` — kiến trúc 5 tầng, điều kiện ans:, ví dụ key/value
- `docs/MULTI_TURN_CACHE_REDIS.md` — luồng multi-turn, session/history/context, LTM
- `plans/redis-memory-cache.md` — entity-keyed tool cache, không cache price cũ (đã fix 15m)
- `docs/PIPELINE_FLOW.md` / `docs/DATA_PIPELINE.md` — 5 phase vs 6-step cũ

---

> **Kết thúc báo cáo.** File này là single source sau khi 4 agents đọc full code. Để xử lý từng phần 1 như yêu cầu, hãy chọn 1 mục trong §13.3 (P1 → P3) và giao tiếp theo.
