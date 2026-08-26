# Báo cáo Fix Bug — Nhóm Vô hạn + High-Accuracy

> **Ngày:** 2026-08-26
> **Đề xuất gốc:** `docs/BUGFIX_PROPOSAL_VO_HAN.md`
> **Audit gốc:** `docs/CACHE_AUDIT_REPORT.md` (mermaid đã fix subgraph space + <br/>)
> **Phạm vi:** 6 bug vô hạn B1-B6 + 4 file high-accuracy B4/B5 (context_builder, call_tools, generate, validate)
> **Tổng files đổi:** 15 + 2 docs mới
> **Review:** `thamdinh` PASS 0 P0

---

## 1. Tổng kết

| ID | Bug | Trạng thái | Files | Verify |
|----|-----|------------|-------|--------|
| **B1 P0** | VectorCache SQLite vô hạn | ✅ DONE | `lib/vector_cache.py`, `backend/lib/vector_cache.py`, `scripts/harness/sinks/qdrant.py`, `scripts/cache_admin.py` | `prune max_rows 10` giữ 10 mới nhất, `prune age 30` xóa 3 cũ, `vector-prune/vector-stats` CLI pass, `py_compile` pass |
| **B2 P0** | LogStore list vô hạn RAM | ✅ DONE | `app/agent/decision.py` | `6000 adds → len 5000 FIFO`, `get_by_run 5000`, `export_jsonl 5000`, `env LOG_STORE_MAXLEN=7` → maxlen 7, `py_compile` pass |
| **B3 P0** | Frontend persist messages vô hạn → QuotaExceeded | ✅ DONE | `frontend/src/store/chatStore.ts` | `partialize slice(-50)`, `migrate v2`, `vivuStorage` catch QuotaExceeded prune 20, `tsc --noEmit` + `vite build 763kB` pass |
| **B4 P1** | _METRICS list vô hạn | ✅ DONE | `lib/openai_client.py`, `backend/lib/openai_client.py` | `deque maxlen 2000`, `3000 records → len 2000`, `reset_metrics` pass |
| **B5 P1** | Sparse index memo stale vô hạn | ✅ DONE | `app/core/retrieval.py`, `app/core/cache.py` | `TTL 60s` hit/miss, `error TTL 10s`, `invalidate_sparse_cache` clear 5 vars, hook `invalidate_all` fail-open, `py_compile` pass |
| **B6 P2** | request_metrics PG vô hạn | ✅ DONE | `app/core/telemetry.py`, `scripts/cache_admin.py` | `prune_old_metrics(days)` int sanitize + `timedelta $1::interval`, `metrics-prune --days 90` CLI pass, `metrics-stats` total 935 pass |
| **B4+** | High-accuracy high | ✅ DONE (re-apply) | `app/agent/context_builder.py`, `app/agent/nodes/call_tools.py`, `app/agent/nodes/generate.py`, `app/agent/nodes/validate.py`, `app/agent/decision.py` (LLM_ERROR) | `PartialStreamError` giữ partial, `llm_error` refuse, `HIGH_ACCURACY_KEYS` subset skip Qdrant 5-case, `validate grounding` chỉ khi `kb_used` 4 paths, `py_compile` pass |

---

## 2. Chi tiết từng fix

### B1 — VectorCache prune

**Vấn đề:** `hash PK` + `INSERT OR REPLACE datetime('now')` không `DELETE`, không TTL, ~6KB/row × 6K rows/version ≈36MB/version → GB sau vài tháng.

**Fix:**
```python
def prune(self, max_age_days=30, max_rows=50000) -> dict:
    cur.execute("DELETE ... WHERE created_at < datetime('now', ?)", (f"-{max_age_days} days",))
    aged = cur.rowcount
    cur.execute("SELECT COUNT(*) ...")
    if total > max_rows: DELETE oldest LIMIT total-max_rows ORDER BY created_at ASC
    commit; if aged+trimmed>0: VACUUM
    return {"aged": aged, "trimmed": trimmed, "total": final_total}
def stats_extended(): COUNT(*), SUM(LENGTH(vector)), hits/misses
```
- `backend/lib/vector_cache.py` sync y hệt
- `scripts/harness/sinks/qdrant.py:366-375` hook sau `ingest_to_qdrant`: `try: vc=VectorCache(); res=vc.prune(); print; close except: fail-open`
- `scripts/cache_admin.py`: `vector-prune --age 30 --max-rows 50000` + `vector-stats`

**Verify:** `max_rows 10 → trimmed 10, rows 10`, `age 30 → aged 3, rows 2` (test tmp SQLite).

### B2 — LogStore deque

**Vấn đề:** `self._logs: list.append` mỗi request, `get_all` copy toàn bộ, không cap → OOM prod.

**Fix:**
```python
from collections import deque
def _resolve_log_store_maxlen() -> int:
    try: v = getattr(settings, "log_store_maxlen", None) -> int
    except: pass
    env_val = os.getenv("LOG_STORE_MAXLEN") -> int
    return 5000
LOG_STORE_MAXLEN = _resolve_log_store_maxlen()
class LogStore:
    def __init__(self, maxlen=None):
        self._logs: deque[dict] = deque(maxlen=resolved)
    def get_all(self): return list(self._logs)
    def __len__(self): return len(self._logs)
```
Giữ API `add/get_by_run/export_jsonl/clear` y hệt.

### B3 — Frontend persist cap

**Vấn đề:** `persist partialize {messages}` lưu toàn bộ forever → vượt 5MB quota → `QuotaExceededError`.

**Fix:**
```ts
import { createJSONStorage } from "zustand/middleware"
const vivuStorage = {
  getItem: (k) => localStorage.getItem(k),
  setItem: (k, v) => { try { localStorage.setItem(k,v) } catch (e) { if (e.name==="QuotaExceededError") { const p=JSON.parse(v); p.state.messages=p.state.messages.slice(-20); try{localStorage.setItem(k,JSON.stringify(p))}catch{localStorage.removeItem(k)} } } },
  removeItem: (k) => localStorage.removeItem(k),
}
persist({
  name: "vivu_chat_storage", version: 2,
  storage: createJSONStorage(() => vivuStorage as Storage),
  partialize: (s) => ({ sessionId: s.sessionId, messages: s.messages.slice(-50) }),
  migrate: (persisted, version) => { if (version<2) persisted.messages = persisted.messages?.slice(-50) ?? []; return persisted },
  onRehydrateStorage: () => (state, error) => { if(error) console.warn(...) }
})
```

### B4 — _METRICS deque

```python
from collections import deque
_METRICS: deque[dict] = deque(maxlen=2000)
def get_metrics(): return list(_METRICS)
def reset_metrics(): _METRICS.clear()
```

### B5 — Sparse TTL

```python
_pg_version_time: float = 0.0
_pg_version_checked_at: float = 0.0
_TTL = 60; _RETRIEVAL_ERROR_TTL = 10
def _get_current_version_from_db():
    if time.time() - _pg_version_checked_at < 60 and _pg_current_version: return _pg_current_version
    # psycopg2 query, sync time, close conn
    _pg_version_checked_at = time.time()
def invalidate_sparse_cache():
    _sparse_index=None; _pg_current_version=None; _pg_version_checked_at=0; _pg_version_checked=False
# app/core/cache.py invalidate_all() -> try invalidate_sparse_cache()
```

### B6 — Telemetry retention

```python
async def prune_old_metrics(days=90) -> int:
    days_int = int(days) if 0 <= int(days) else 0
    await ensure_telemetry_schema()
    status = await pool.execute("DELETE FROM request_metrics WHERE created_at < now() - $1::interval", timedelta(days=days_int))
    return int(status.split()[-1])
async def get_metrics_retention_info(): SELECT COUNT(*), MIN/MAX(created_at)
```

CLI `metrics-prune --days 90` + `metrics-stats`.

### High-accuracy (re-apply)

- `decision.py`: `ReasonCode.LLM_ERROR`, `_REASON_MAP["llm_error"]`, `REFUSAL_MESSAGES["llm_error"]` — 3 dòng additive, giữ deque
- `context_builder.py`: `_FEATURE_KEYWORD_MAP` thêm `price_vnd/promo_price_vnd`, `colors`, `options`
- `call_tools.py`: `is_high_accuracy = model_code and target_keys ⊆ HIGH_ACCURACY_KEYS` → skip `search_knowledge_base`
- `generate.py`: `except PartialStreamError` giữ partial, `except Exception` → `refuse llm_error`
- `validate.py`: `kb_used = any(tool==search_knowledge_base)` → chỉ `_check_grounding` khi `kb_used && final_response`

---

## 3. Verify tổng hợp

```
VectorCache: before 20 rows -> prune max_rows 10 -> 10 rows, age 30 -> aged 3 PASS
LogStore: 6000 adds -> len 5000 FIFO q2..q6, export 5000, clear 0 PASS
Frontend: tsc --noEmit PASS, vite build 763kB PASS, 100 -> 50 slice PASS
_METRICS: 3000 -> len 2000 PASS
Sparse: within TTL hit v2, after 70s attempt DB, invalidate clears PASS
cache_admin --help: 7 subcommands (stats/clear/version/metrics-prune/metrics-stats/vector-prune/vector-stats) PASS
py_compile 15 files PASS
Review: PASS 0 P0
```

---

## 4. Commit

- Branch: `main` (hoặc current)
- Diff: 15 files + 2 docs mới (`BUGFIX_PROPOSAL_VO_HAN.md`, `BUGFIX_REPORT_VO_HAN.md`)
- Lệnh push: `git push origin HEAD`

---

## 5. Rủi ro còn lại & next step

- B1 `VACUUM` tốn lock ngắn trên SQLite — đã fail-open, ok cho dev.
- B2 `deque maxlen` mất log cũ nếu không export — đã giữ `export_jsonl`.
- B3 cap 50 có thể tăng lên 100 nếu UX yêu cầu.
- B6 retention 90d chưa có cron tự động — đề xuất `pg_cron` hoặc `cache_admin metrics-prune` trong CI.

> Sẵn sàng merge.
