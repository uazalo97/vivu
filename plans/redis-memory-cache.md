# Plan: Redis Session Store + Tool-Result Cache + Long-term Memory

## Mục tiêu

1. **Multi-turn memory** — chuyển session từ RAM/client sang Redis (tách `history` vs `current_context`).
2. **Tool-result cache** — cache theo entity đã resolve, TTL phân tầng, invalidation chủ động cho dữ liệu volatile.
3. **Long-term memory** — lưu fact/preference theo user (redis agent memory pattern).

---

## 1. Prerequisites

| Việc | File | Ghi chú |
|---|---|---|
| Thêm dependency | `requirements.txt` | `redis>=5.0` |
| Thêm redis service | `docker-compose.yml` | image `redis:7-alpine`, port 6379, volume `redis_data`, appendonly `yes` |
| Thêm config | `app/config.py` | `self.redis_url = _env.get("REDIS_URL", "redis://localhost:6379/0")` |
| Thêm env | `.env` + `.env.example` | `REDIS_URL=redis://localhost:6379/0` |

---

## 2. Module mới `app/core/memory.py` — Session Store + Long-term Memory

Dùng `redis.asyncio`, `decode_responses=True`, fail-open (Redis tắt → trả default, không crash).

```python
SESSION_TTL = timedelta(hours=6)
MAX_TURNS = 10          # sliding window history
LTM_TTL = timedelta(days=30)
```

### 2.1 Session store (short-term)

- **`load_session(session_id)`** → `{"history": [...], "current_context": {...}}`
  - history: `session:{sid}:history` (JSON list)
  - context: `session:{sid}:context` (hash: `model_code`, `version`, `last_topic`)
- **`save_turn(session_id, user_msg, assistant_msg)`** → append 2 lượt, cắt `MAX_TURNS`, ghi `ex=TTL`. KHÔNG đụng `current_context`.
- **`update_current_context(session_id, model_code, version, topic)`** → chỉ `hset` field non-null. "Phao cứu sinh" khi history bị cắt.

### 2.2 Long-term memory (keyed by user_id)

- **`load_user_profile(user_id)`** → hash `user:{uid}:profile` (budget, family_size, preferred_model, preferred_version...)
- **`save_user_fact(user_id, field, value)`** → `hset` + `expire` LTM_TTL
- **`load_user_facts(user_id)`** → hash read
- `user_id` chưa có auth → fallback `user_id = session_id` (đổi key prefix khi có auth sau này).

---

## 3. Module mới `app/core/cache.py` — Tool-result cache

Fail-open: Redis tắt → bỏ qua cache, vẫn query bình thường.

### 3.1 Key theo entity (KHÔNG raw text)

```
cache:specs:{model_code}:{version|all}:{category|all}
cache:colors:{model_code}:{version|all}
cache:options:{model_code}:{version|all}
cache:list_models
```

### 3.2 TTL phân tầng (volatility axis)

```python
CACHE_TTL_BY_TOPIC = {
    "thông_số_kỹ_thuật": 6h, "kích_thước": 24h, "an_toàn": 6h,
    "nội_thất": 6h, "ngoại_thất": 6h, "pin_và_sạc": 6h,
    "phạm_vi_di_chuyển": 6h, "màu_sắc": 6h, "option": 6h,
    "giá": None, "khuyến_mãi": None,   # KHÔNG cache — invalidation chủ động
    "list_models": 1h,
}
```

### 3.3 API

- `get_specs_cached(model_code, version, category)`
- `get_colors_cached(model_code, version)`
- `get_options_cached(model_code, version)`
- `list_models_cached()`
- `invalidate_entity(cache_key)` — delete 1 key
- `invalidate_model(model_code)` — scan prefix `cache:{specs|colors|options}:{model_code}:*` (dùng `SCAN`, không `KEYS`)

**Không cache `get_price` và `get_active_promotions`** — luôn query trực tiếp.

### 3.4 KB search cache (thận trọng)

`search_kb_cached(query, model_id)` — key theo hash chuẩn hóa nhẹ (lowercase, bỏ dấu câu), TTL 2h. Hit-rate thấp nhưng có ích cho câu hỏi lặp nguyên văn.

---

## 4. Integration

### 4.1 `app/api/chat.py`

- `session_id` Optional → nếu thiếu, sinh `uuid4` (trả cho client qua response). Lưu ý telemetry `record_metric` nhận session_id dạng UUID — phải hợp lệ format.
- Trước agent: `session = await load_session(session_id)`; ghép `history = session["history"]`.
- Sau khi có kết quả: `save_turn(session_id, user_msg, assistant_msg)` + `update_current_context(...)` từ `result.classify_result.entities` + `decision_log.topic`.
- Điền `cache_hit`/`cache_type` vào telemetry khi tool hit cache.

### 4.2 `app/agent/agent_loop.py`

- `run(query, history)` / `run_stream(...)` nhận thêm `current_context` → `state["current_context"]`.

### 4.3 `app/agent/graph_state.py`

- Thêm `current_context: dict[str, Any]` + `cache_hit: bool`.

### 4.4 `app/agent/nodes/classify.py`

- `classify_node` đọc `state["current_context"]`, dùng làm fallback cho `_extract_history_context` (model/version/last_topic) khi query ellipsis ("còn màu nào khác?").

### 4.5 `app/agent/nodes/call_tools.py`

- `_call_model_tools`: thay `get_specs`/`get_colors`/`get_options` bằng bản `*_cached`; `list_available_models` → `list_models_cached`.
- `get_price`/`get_active_promotions` GIỮ NGUYÊN (không cache).
- Ghi `cache_hit=True` vào tool_results entry khi hit cache.

### 4.6 `app/agent/tools.py`

- `search_knowledge_base` → bọc `search_kb_cached` (giữ signature).

### 4.7 `scripts/ingest/postgres_ingest.py` — invalidation

- `set_current(version)` + rollback → gọi `invalidate_all()` (đổi version active → cache specs/colors/options cũ lỗi thời).
- `upsert_price_list` → giá không cache, bỏ qua; thêm hook tổng quát `invalidate_model(mid)` cho spec thay đổi nếu cần.

---

## 5. Luồng 1 request (sau khi hoàn thành)

```
Client POST /api/chat {message, session_id?}
   │  (sinh session_id nếu thiếu)
   ▼
load_session(session_id) → {history, current_context}
   ▼
classify ← dùng current_context nếu query ellipsis
   ▼
call_tools → *_cached (entity-keyed; giá/khuyến mãi query trực tiếp)
   ▼
generate (LLM synth) → validate → respond
   ▼
save_turn + update_current_context + save_user_fact (long-term)
```

---

## 6. Backward-compat & an toàn

- **Fail-open**: Redis down → `load/save/cache` trả default (`history=[]`, miss cache) → chạy như cũ.
- **Không cache giá/khuyến mãi** → không bao giờ trả giá cũ do cache.
- **TTL phân tầng + invalidation chủ động** → specs (ít đổi) TTL dài; xóa ngay khi `set_current`/rollback.
- **Long-term memory** tách khỏi session (user-keyed), không mất khi session TTL hết hạn.

---

## 7. Thứ tự thực hiện

1. [ ] Thêm `redis>=5.0` + cài
2. [ ] docker-compose redis + REDIS_URL env/config
3. [ ] `app/core/memory.py`
4. [ ] `app/core/cache.py`
5. [ ] Wiring `chat.py`
6. [ ] Wiring `graph_state` + `classify`
7. [ ] Wiring `call_tools` + cache_hit
8. [ ] Wiring `postgres_ingest` invalidation
9. [ ] Test: scale 2 instance, TTL, invalidation giá, Redis-down fallback

## 8. Rủi ro

- `redis.asyncio` + `decode_responses=True` → hash field là string, cần `json.loads` cho nested.
- Scan prefix dùng `SCAN` (không `KEYS`) tránh block.
- `current_context` phải update từ entity thật (không từ query text) tránh lệch context.
- Không cache response LLM (tránh nhân bản bug như HUD case).