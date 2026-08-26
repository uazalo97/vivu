# Đề xuất Fix Bug — Nhóm "Vô hạn" (Unbounded Growth / TTL vô hạn)

> **Ngày:** 2026-08-26
> **Nguồn:** `docs/CACHE_AUDIT_REPORT.md` + rà soát code trực tiếp 2026-08-26
> **Phạm vi:** chỉ các bug "vô hạn" — TTL vô hạn hoặc cấu trúc append mãi không giới hạn, dẫn tới OOM / disk full / stale vĩnh viễn
> **Không đụng:** `app/core/rate_limit.py` đã có `_cleanup_stale` 5 phút / 10 phút idle — không tính là bug

---

## Tóm tắt ưu tiên

| ID | Bug | File | Tăng trưởng | Hậu quả | Ưu tiên |
|----|-----|------|-------------|---------|---------|
| **B1** | **VectorCache SQLite vô hạn** | `lib/vector_cache.py:28-86`, `backend/lib/vector_cache.py` | ~6KB/row × số chunk unique qua mọi version + embed_model, không TTL, không prune | `data/.vector_cache/cache.sqlite` phình GB, `INSERT OR REPLACE` giữ mãi vector cũ của model đã bỏ, disk full trên dev/CI | **P0** |
| **B2** | **LogStore in-memory vô hạn** | `app/agent/decision.py:265-306` `log_store = LogStore()` | `self._logs.append` mỗi request, chỉ `clear()` thủ công | prod chạy 24/7 → `list[dict]` tăng mãi → OOM, `GET /api/logs` trả cả lịch sử → latency + JSON lớn | **P0** |
| **B3** | **Frontend localStorage vô hạn** | `frontend/src/store/chatStore.ts:215-221` `persist name=vivu_chat_storage` | `partialize {sessionId, messages}` lưu **toàn bộ** `messages[]` forever, không cap | chat dài → vượt quota 5MB → `setItem` throw → Zustand persist fail → mất history / UI trắng, không tự hồi phục | **P0** |
| **B4** | **_METRICS pipeline vô hạn** | `lib/openai_client.py:55` `_METRICS: list[dict] = []` | `record_metric` append mỗi `embed_texts / chat_completion` | `scripts/harness` chạy batch lớn hoặc import từ app → list tăng mãi, `get_metrics()` copy toàn bộ | **P1** |
| **B5** | **Sparse index memo stale vô hạn** | `app/core/retrieval.py:66-160` `_sparse_index`, `_pg_current_version`, `_pg_version_checked=True` | cache lifetime = process lifetime, không check lại DB sau promote | promote v3 nhưng process cũ vẫn `_sparse_index=v2` forever → BM25 sai, không tự hết cho tới restart | **P1** |
| **B6** | **request_metrics PG vô hạn** | `app/core/telemetry.py:67-108` `request_metrics` | INSERT mỗi request, không retention, không partition | bảng phình vô hạn → `get_metrics_*` chậm, index `created_at DESC` không đủ khi 10M rows | **P2** |

> 3 bug P0 (B1,B2,B3) là phải fix trước khi chạy prod dài ngày. B4-B6 fix kèm hoặc ngay sau.

---

## B1 — VectorCache SQLite vô hạn

### Hiện trạng

```python
# lib/vector_cache.py:28-38
_SCHEMA = """
CREATE TABLE vector_cache (
    hash TEXT PRIMARY KEY,
    collection TEXT,
    embed_model TEXT,
    dim INT,
    vector BLOB,
    created_at TEXT
);
CREATE INDEX idx_vc_collection ON vector_cache(collection);
"""
# get: SELECT vector WHERE hash=?
# put: INSERT OR REPLACE ... datetime('now')
# Không TTL, không DELETE, không VACUUM, không max_rows, không max_age
```

- Key = `sha1(embed_model + "\x1f" + text + "\x1f" + json(structured))` → content y hệt dù sang version khác vẫn hit, nhưng khi đổi `embed_model` (ví dụ `text-embedding-3-small` → `3-large`) thì key cũ vẫn nằm mãi.
- Mỗi row ~6KB (1536 float `array('f')`). 1 version ~2212 chunks × 3 collections ≈ 6K rows ≈ 36MB. 10 version + 2 model = 72K rows ≈ 432MB.
- `backend/lib/vector_cache.py` duplicate y hệt — drift risk.
- Harness mới `scripts/harness/sinks/qdrant.py:ingest_to_qdrant` **không dùng** VectorCache → càng không prune, file chỉ tăng.

### Tác hại

- Dev/CI disk full sau vài tháng chạy pipeline.
- Vector của model cũ không bao giờ dùng nhưng vẫn đọc khi `SELECT` → lãng phí.
- Không có `VACUUM` → `DELETE` cũng không trả disk lại.

### Phương án

| Phương án | Cách | Ưu | Nhược |
|-----------|------|----|-------|
| **A — prune theo age + size (chốt)** | Thêm `prune(max_age_days=30, max_rows=50000)` + gọi trong `pipeline.py` sau `ingest_to_qdrant`, + `VACUUM` | đơn giản, giữ hit cho version gần, xóa model cũ | cần chọn ngưỡng |
| B — TTL cột + cron | `DELETE WHERE created_at < now -30d` via `cache_admin.py` cron | tương tự A nhưng đòi cron | thêm infra |
| C — LRU via `last_access` | thêm `last_access` update mỗi `get` | chính xác LRU nhưng write amplification | phức tạp |

### Đề xuất chọn: A

**Code mẫu (lib/vector_cache.py):**

```python
def prune(self, max_age_days: int = 30, max_rows: int = 50000) -> dict:
    cur = self._conn.cursor()
    # 1) xóa theo age
    cur.execute("DELETE FROM vector_cache WHERE created_at < datetime('now', ?)", (f"-{max_age_days} days",))
    aged = cur.rowcount
    # 2) xóa theo size (giữ mới nhất)
    cur.execute("SELECT COUNT(*) FROM vector_cache")
    total = cur.fetchone()[0]
    trimmed = 0
    if total > max_rows:
        cur.execute("""
            DELETE FROM vector_cache WHERE hash IN (
                SELECT hash FROM vector_cache ORDER BY created_at ASC LIMIT ?
            )
        """, (total - max_rows,))
        trimmed = cur.rowcount
    self._conn.commit()
    # 3) thu hồi disk
    if aged + trimmed > 0:
        self._conn.execute("VACUUM")
    return {"aged": aged, "trimmed": trimmed, "total": total - aged - trimmed}

def stats_extended(self) -> dict:
    cur = self._conn.execute("SELECT COUNT(*), SUM(LENGTH(vector)) FROM vector_cache")
    cnt, sz = cur.fetchone()
    return {"rows": cnt, "bytes": sz or 0, "hits": self.hits, "misses": self.misses}
```

**Hook:**

```python
# scripts/harness/sinks/qdrant.py sau ingest_to_qdrant
from lib.vector_cache import VectorCache
vc = VectorCache(); res = vc.prune(); logger.info("VectorCache prune %s", res); vc.close()

# scripts/cache_admin.py thêm
python scripts/cache_admin.py vector-prune --age 30 --max-rows 50000
```

**Test:** `test_vector_cache_prune` tạo 100 rows với `created_at` cũ → `prune(max_age_days=0)` phải xóa hết, `prune(max_rows=10)` giữ 10 mới nhất.

---

## B2 — LogStore in-memory vô hạn

### Hiện trạng

```python
# app/agent/decision.py:265-306
class LogStore:
    def __init__(self): self._logs: list[dict] = []
    def add(self, log: DecisionLog): self._logs.append(log.to_dict())  # không cap
    def get_all(self): return list(self._logs)
    def clear(self): self._logs.clear()  # chỉ gọi thủ công

log_store = LogStore()  # singleton process
```

- `make_decision_log` gọi mỗi request trong `app/api/chat.py`.
- `GET /api/logs` và `/api/logs/export` trả toàn bộ list — càng chạy càng lớn.
- Không `maxlen`, không rotation file, không TTL.

### Tác hại

- Prod 1000 req/ngày × 2KB/log ≈ 2MB/ngày → 60MB/tháng, 720MB/năm trong RAM → OOM.
- `/api/logs?run_id=...` scan `list[dict]` O(n).

### Phương án

| Phương án | Cách | Ưu | Nhược |
|-----------|------|----|-------|
| **A — deque maxlen FIFO (chốt)** | `collections.deque(maxlen=5000)` + `clear()` khi `start_run` hoặc exceed | O(1), giữ 5000 gần nhất đủ debug, mất cũ tự rơi | mất log cũ nếu không export |
| B — rotate ra file | `export_jsonl` mỗi 1000 logs | giữ đủ lịch sử | thêm I/O |
| C — bỏ LogStore, chỉ PG | ghi `request_metrics` đã đủ | đơn giản | mất debug nhanh |

### Đề xuất chọn: A + B nhẹ

```python
from collections import deque

class LogStore:
    def __init__(self, maxlen: int = 5000):
        self._logs: deque[dict] = deque(maxlen=maxlen)
        self._maxlen = maxlen
    def add(self, log: DecisionLog):
        if len(self._logs) == self._maxlen:
            # optional: export trước khi rơi
            pass
        self._logs.append(log.to_dict())
    def get_all(self): return list(self._logs)
    # get_by_run vẫn O(n) nhưng n≤5000
```

Giữ nguyên `export_jsonl` để `GET /api/logs/export?run_id=...` có thể dump.

**Config:** `LOG_STORE_MAXLEN=5000` env.

---

## B3 — Frontend localStorage vô hạn

### Hiện trạng

```ts
// frontend/src/store/chatStore.ts:215-221
persist({
  name: "vivu_chat_storage",
  partialize: (state) => ({ sessionId: state.sessionId, messages: state.messages }),
})
// messages: ChatMessage[] {id, role, content, sources?, clarify?, error?, status?}
// Không cap, không TTL, không migration, lưu forever
```

- `HISTORY_LIMIT=6` chỉ áp khi gửi request, không áp khi persist.
- User chat 200 turn × avg 1KB = 200KB, kèm sources → dễ 1-2MB. Nhiều tab → mỗi tab 1 key duplicate.
- `localStorage` quota ~5MB/domain → `setItem` throw `QuotaExceededError` → Zustand `persist` fail silently hoặc throw → mất store.
- `frontend/src/session.ts` legacy `vivu_history` slice(-14)=7 turns có cap, nhưng store ახალი không có.

### Tác hại

- Sau vài tuần dùng, user bị lỗi “Cannot save to localStorage” → history biến mất, sessionId reset → mất context.

### Phương án

| Phương án | Cách | Ưu |
|-----------|------|----|
| **A — cap + migrate (chốt)** | `messages.slice(-50)` khi persist, + `version:2` migrate cắt cũ, + `try/catch QuotaExceeded` fallback `clearChat()` | đơn giản, giữ 50 gần nhất ≈ 50KB |
| B — IndexedDB | chuyển sang `idb-keyval` | quota lớn hơn nhưng phức tạp |
| C — chỉ lưu sessionId, messages để RAM | mất persist qua reload | không UX |

### Đề xuất chọn: A

```ts
export const useChatStore = create<ChatState>()(
  persist((set, get) => ({ ... }), {
    name: "vivu_chat_storage",
    version: 2,
    partialize: (state) => ({
      sessionId: state.sessionId,
      messages: state.messages.slice(-50), // cap 50
    }),
    migrate: (persisted: any, version) => {
      if (version === 0) persisted.messages = persisted.messages?.slice(-50) ?? [];
      return persisted;
    },
    // optional: handle QuotaExceeded
    onRehydrateStorage: () => (state, error) => {
      if (error) console.warn("Rehydrate failed", error);
    },
  })
);
```

Thêm `try { localStorage.setItem } catch { localStorage.removeItem("vivu_chat_storage") }` trong custom storage nếu cần.

---

## B4 — _METRICS pipeline vô hạn

### Hiện trạng

```python
# lib/openai_client.py:55
_METRICS: list[dict] = []
def record_metric(op, model, start, usage, ...): _METRICS.append({...})
def get_metrics(): return list(_METRICS)  # copy toàn bộ
def summarize_metrics(): groupby _METRICS
# Không cap, không clear tự động. reset_metrics() tồn tại nhưng không ai gọi.
```

- `embed_texts(workers=8)` mỗi batch ghi 1 metric → pipeline 6K chunks /64 ≈ 94 metrics/run.
- Nếu `lib.openai_client` được import trong `app` (harness share), prod sẽ append mỗi request.

### Fix

```python
from collections import deque
_METRICS: deque[dict] = deque(maxlen=2000)
def get_metrics(): return list(_METRICS)
def reset_metrics(): _METRICS.clear()
```

Giữ 2000 gần nhất đủ `summarize_metrics`, không OOM.

---

## B5 — Sparse index memo stale vô hạn

### Hiện trạng

```python
# app/core/retrieval.py:66-74
_pg_current_version: str | None = None
_pg_version_checked = True  # sau lần đầu
# _load_sparse_index() cache _sparse_index forever, chỉ reload khi process restart
```

- Sau `version_manager promote v3`, `_pg_version_checked=True` nên `_get_current_version_from_db()` return ngay `_pg_current_version=v2` → không check DB nữa → `_sparse_index` vẫn v2 forever.

### Fix — TTL 60s giống `data_version()`

```python
_pg_version_checked_at: float = 0
_TTL = 60

def _get_current_version_from_db() -> str | None:
    global _pg_current_version, _pg_version_checked, _pg_version_checked_at
    if time.time() - _pg_version_checked_at < _TTL and _pg_current_version is not None:
        return _pg_current_version
    # ... query DB ...
    _pg_version_checked_at = time.time()
    return _pg_current_version

def invalidate_sparse_cache():
    global _sparse_index, _pg_current_version, _pg_version_checked_at
    _sparse_index = None; _pg_current_version = None; _pg_version_checked_at = 0
```

Gọi `invalidate_sparse_cache()` trong `invalidate_all()` và sau promote.

---

## B6 — request_metrics PG vô hạn

### Hiện trạng

- `telemetry.py` tạo bảng nhưng không có retention. Prod 1000 req/ngày → 365K rows/năm, query `get_metrics_overview(hours=24)` vẫn nhanh nhờ index, nhưng `get_metrics_logs(limit=100)` full scan nếu không filter `created_at`.

### Fix — retention 30-90 ngày

```sql
-- migration
CREATE OR REPLACE FUNCTION cleanup_old_metrics() RETURNS void AS $$
  DELETE FROM request_metrics WHERE created_at < now() - interval '90 days';
$$ LANGUAGE sql;

-- cron: pg_cron hoặc app startup
-- hoặc trong ensure_telemetry_schema mỗi 24h:
-- await pool.execute("DELETE FROM request_metrics WHERE created_at < now() - interval '90 days'")
```

Thêm `scripts/cache_admin.py metrics-prune --days 90`.

Hoặc partition theo tháng (P2, để sau).

---

## Lộ trình đề xuất

| Phase | Bug | Effort | Rủi ro nếu không fix |
|-------|-----|--------|----------------------|
| **Phase 1 — ngay (P0)** | B2 LogStore deque 5000, B3 frontend slice 50 + migrate | 0.5 ngày, không migration DB | OOM sau 1-2 tháng prod |
| **Phase 1 — ngay (P0)** | B1 VectorCache prune + VACUUM | 0.5 ngày | disk full CI/dev |
| **Phase 2 — tuần sau (P1)** | B4 _METRICS deque 2000, B5 sparse TTL 60s | 0.5 ngày | stale BM25 sau promote |
| **Phase 3 — sau (P2)** | B6 PG retention 90d | 0.5 ngày, cần cron | chậm query sau 1 năm |

Thứ tự implement gợi ý:

1. B2 (dễ nhất, 10 dòng)
2. B3 (frontend, 15 dòng)
3. B1 (lib + hook pipeline)
4. B5 (retrieval, 10 dòng)
5. B4 (lib, 3 dòng)
6. B6 (SQL + script)

---

## Tiêu chí nghiệm thu

- B1: `VectorCache().prune(max_age_days=0)` xóa hết, `prune(max_rows=10)` giữ đúng 10, `VACUUM` giảm file size, pipeline log `prune {aged, trimmed}`.
- B2: gửi 6000 request giả → `len(log_store.get_all()) ≤ 5000`, `GET /api/logs` latency <100ms.
- B3: `store.messages` 100 items → `localStorage["vivu_chat_storage"]` chỉ 50, reload vẫn 50, không `QuotaExceeded`.
- B4: `record_metric` 3000 lần → `len(get_metrics()) ≤ 2000`.
- B5: promote v2→v3 trong 60s → `_load_sparse_index()` trả version mới không cần restart.
- B6: `DELETE ... <90d` xóa, `get_metrics_overview` không scan toàn bảng.

---

## Phụ lục — File đụng chạm

- `lib/vector_cache.py`, `backend/lib/vector_cache.py`, `scripts/harness/sinks/qdrant.py`, `scripts/cache_admin.py`
- `app/agent/decision.py`, `app/api/chat.py` (log_store usage)
- `frontend/src/store/chatStore.ts`
- `lib/openai_client.py`, `backend/lib/openai_client.py`
- `app/core/retrieval.py`, `app/core/cache.py` (invalidate hook)
- `app/core/telemetry.py`, `migrations/xxx_retention.sql`

> Chờ bạn chốt phương án (A cho tất cả đã đề xuất) để thi công từng phần 1 như yêu cầu trước.
