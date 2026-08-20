"""
app/core/telemetry.py — Telemetry, Token Cost & Latency Tracking Engine.

Theo dõi chỉ số vận hành của chatbot:
- TTFT (Time-to-First-Token) & Total Latency
- Prompt & Completion Tokens
- Chi phí LLM theo model (USD & VND)
- Tỷ lệ Cache Hit/Miss
- Phân bổ Intent & Tool calls
"""

import asyncio
import json
import logging
import time  # noqa: F401
import uuid
from typing import Any

from app.config import settings
from app.core.db import get_pool, run_with_db_retry

logger = logging.getLogger("bds.telemetry")

# Bảng giá USD trên 1 triệu tokens (1M tokens)
MODEL_PRICING = {
    # OpenAI
    "gpt-4o-mini": {"input_per_m": 0.15, "output_per_m": 0.60},
    "openai/gpt-4o-mini": {"input_per_m": 0.15, "output_per_m": 0.60},
    "gpt-4o": {"input_per_m": 2.50, "output_per_m": 10.00},
    "openai/gpt-4o": {"input_per_m": 2.50, "output_per_m": 10.00},
    # DeepInfra / DeepSeek
    "deepseek-ai/deepseek-v4-flash": {"input_per_m": 0.14, "output_per_m": 0.28},
    "deepseek-ai/deepseek-v3": {"input_per_m": 0.27, "output_per_m": 1.10},
    "deepseek-ai/deepseek-r1": {"input_per_m": 0.55, "output_per_m": 2.19},
    "deepseek/deepseek-chat": {"input_per_m": 0.14, "output_per_m": 0.28},
    # Claude
    "anthropic/claude-haiku-4-5": {"input_per_m": 0.80, "output_per_m": 4.00},
    "claude-3-5-haiku-20241022": {"input_per_m": 0.80, "output_per_m": 4.00},
    "claude-3-5-sonnet-20241022": {"input_per_m": 3.00, "output_per_m": 15.00},
    # Gemini
    "google/gemini-2.0-flash": {"input_per_m": 0.10, "output_per_m": 0.40},
    "google/gemini-2.5-flash": {"input_per_m": 0.15, "output_per_m": 0.60},
    # Fallback
    "default": {"input_per_m": 0.20, "output_per_m": 0.50},
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> tuple[float, float]:
    """Tính toán chi phí (cost_usd, cost_vnd) dựa trên tokens và pricing model."""
    m = (model or "").lower().strip()
    pricing = MODEL_PRICING.get("default")
    for key, val in MODEL_PRICING.items():
        if key in m:
            pricing = val
            break

    input_cost = (prompt_tokens / 1_000_000.0) * pricing["input_per_m"]
    output_cost = (completion_tokens / 1_000_000.0) * pricing["output_per_m"]
    total_usd = input_cost + output_cost
    usd_rate = getattr(settings, "usd_vnd_rate", 25400.0)
    total_vnd = total_usd * usd_rate
    return round(total_usd, 6), round(total_vnd, 2)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS request_metrics (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    session_id          UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    query_text          TEXT,
    intent              TEXT,
    decision            TEXT,
    model_used          TEXT,
    prompt_version      TEXT DEFAULT 'v1.0.0',
    prompt_tokens       INT DEFAULT 0,
    completion_tokens   INT DEFAULT 0,
    total_tokens        INT DEFAULT 0,
    cost_usd            NUMERIC(10, 6) DEFAULT 0.0,
    cost_vnd            NUMERIC(12, 2) DEFAULT 0.0,
    ttft_ms             INT DEFAULT 0,
    ttot_ms             INT DEFAULT 0,
    total_latency_ms    INT DEFAULT 0,
    latency_retrieval_ms INT DEFAULT 0,
    latency_generation_ms INT DEFAULT 0,
    cache_hit           BOOLEAN DEFAULT false,
    cache_type          TEXT DEFAULT 'none',
    tools_used          JSONB DEFAULT '[]'::jsonb,
    status_code         INT DEFAULT 200,
    error_message       TEXT,
    model_code          TEXT,
    model_version       TEXT,
    retrieval_status    TEXT,
    chunks_retrieved    INT DEFAULT 0,
    reasoning_tokens    INT DEFAULT 0,
    user_feedback       SMALLINT,
    feedback_comment    TEXT
);

CREATE INDEX IF NOT EXISTS idx_req_metrics_created ON request_metrics(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_req_metrics_intent ON request_metrics(intent);
CREATE INDEX IF NOT EXISTS idx_req_metrics_cache ON request_metrics(cache_hit);
CREATE INDEX IF NOT EXISTS idx_req_metrics_session ON request_metrics(session_id);
CREATE INDEX IF NOT EXISTS idx_req_metrics_model_code ON request_metrics(model_code);
CREATE INDEX IF NOT EXISTS idx_req_metrics_decision ON request_metrics(decision);
"""

_schema_ready = False
_ensure_lock = asyncio.Lock()


async def ensure_telemetry_schema() -> None:
    """Tạo bảng telemetry nếu chưa tồn tại + tự migrate cột mới (idempotent)."""
    global _schema_ready
    if _schema_ready:
        return
    async with _ensure_lock:
        if _schema_ready:
            return

        async def _create():
            pool = await get_pool()
            async with pool.acquire() as conn:
                for stmt in _SCHEMA_SQL.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        await conn.execute(stmt)
                # Backfill cột mới cho DB cũ (idempotent) — chạy ngay sau CREATE
                for stmt in [
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS ttot_ms INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS latency_retrieval_ms INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS latency_generation_ms INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS model_code TEXT",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS model_version TEXT",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS retrieval_status TEXT",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS chunks_retrieved INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS reasoning_tokens INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS user_feedback SMALLINT",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS feedback_comment TEXT",
                    "CREATE INDEX IF NOT EXISTS idx_req_metrics_model_code ON request_metrics(model_code)",
                    "CREATE INDEX IF NOT EXISTS idx_req_metrics_decision ON request_metrics(decision)",
                ]:
                    try:
                        await conn.execute(stmt)
                    except Exception as e:
                        logger.debug("migrate %s: %s", stmt, e)

        await run_with_db_retry(_create, label="ensure request_metrics schema")
        _schema_ready = True


async def record_metric(
    *,
    request_id: str,
    session_id: str | None = None,
    query_text: str = "",
    intent: str = "general",
    decision: str = "answer",
    model_used: str = "",
    prompt_version: str = "v1.0.0",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    ttft_ms: int = 0,
    ttot_ms: int = 0,
    total_latency_ms: int = 0,
    latency_retrieval_ms: int = 0,
    latency_generation_ms: int = 0,
    cache_hit: bool = False,
    cache_type: str = "none",
    tools_used: list[str] | None = None,
    status_code: int = 200,
    error_message: str | None = None,
    model_code: str | None = None,
    model_version: str | None = None,
    retrieval_status: str | None = None,
    chunks_retrieved: int = 0,
    reasoning_tokens: int = 0,
) -> None:
    """Ghi nhận metric của một request vào PostgreSQL (non-blocking)."""
    if not getattr(settings, "metrics_enabled", True):
        return

    sess_uuid = None
    if session_id:
        try:
            sess_uuid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            sess_uuid = None

    total_tokens = prompt_tokens + completion_tokens
    cost_usd, cost_vnd = calculate_cost(model_used, prompt_tokens, completion_tokens)
    tools_json = json.dumps(tools_used or [], ensure_ascii=False)

    # Đảm bảo cột mới tồn tại trước khi INSERT (idempotent, chạy mỗi lần để fix DB cũ)
    async def _ensure_new_columns():
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                for stmt in [
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS ttot_ms INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS latency_retrieval_ms INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS latency_generation_ms INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS model_code TEXT",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS model_version TEXT",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS retrieval_status TEXT",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS chunks_retrieved INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS reasoning_tokens INT DEFAULT 0",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS user_feedback SMALLINT",
                    "ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS feedback_comment TEXT",
                    "CREATE INDEX IF NOT EXISTS idx_req_metrics_model_code ON request_metrics(model_code)",
                    "CREATE INDEX IF NOT EXISTS idx_req_metrics_decision ON request_metrics(decision)",
                ]:
                    try:
                        await conn.execute(stmt)
                    except Exception as e:
                        logger.debug("migrate %s: %s", stmt, e)
        except Exception as e:
            logger.debug("ensure columns failed: %s", e)

    try:
        await ensure_telemetry_schema()
        await _ensure_new_columns()

        async def _insert():
            pool = await get_pool()
            await pool.execute(
                """
                INSERT INTO request_metrics (
                    request_id, session_id, query_text, intent, decision,
                    model_used, prompt_version, prompt_tokens, completion_tokens, total_tokens,
                    cost_usd, cost_vnd, ttft_ms, ttot_ms, total_latency_ms,
                    latency_retrieval_ms, latency_generation_ms,
                    cache_hit, cache_type, tools_used, status_code, error_message,
                    model_code, model_version, retrieval_status, chunks_retrieved, reasoning_tokens
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15,
                    $16, $17,
                    $18, $19, $20::jsonb, $21, $22,
                    $23, $24, $25, $26, $27
                )
                """,
                request_id,
                sess_uuid,
                query_text[:500] if query_text else "",
                intent,
                decision,
                model_used or settings.llm_model,
                prompt_version or "v1.0.0",
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cost_usd,
                cost_vnd,
                ttft_ms,
                ttot_ms,
                total_latency_ms,
                latency_retrieval_ms,
                latency_generation_ms,
                cache_hit,
                cache_type,
                tools_json,
                status_code,
                error_message,
                model_code,
                model_version,
                retrieval_status,
                chunks_retrieved,
                reasoning_tokens,
            )

        try:
            await run_with_db_retry(_insert, label="record_metric")
        except Exception as e:
            # Nếu thiếu cột (DB cũ chưa migrate kịp) → chạy migrate rồi retry 1 lần
            if "does not exist" in str(e) and "column" in str(e):
                logger.warning("record_metric missing column, migrating and retry: %s", e)
                await _ensure_new_columns()
                await run_with_db_retry(_insert, label="record_metric retry")
            else:
                raise
    except Exception as exc:
        logger.warning("Failed to record metric (continuing): %s", exc)


def log_metric_background(task_coro):
    """Tiện ích fire-and-forget chạy background task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(task_coro)
    except Exception as e:
        logger.warning("Error scheduling background metric task: %s", e)


# ── Analytics & Aggregation Queries for Admin API ────────────────────────────


async def get_metrics_overview(hours: int = 24) -> dict[str, Any]:
    """Lấy số liệu KPI tổng quan trong N giờ qua."""
    await ensure_telemetry_schema()

    query = """
    SELECT
        COUNT(*) AS total_requests,
        COALESCE(SUM(total_tokens), 0) AS total_tokens,
        COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
        COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
        COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd,
        COALESCE(SUM(cost_vnd), 0.0) AS total_cost_vnd,
        COALESCE(AVG(total_latency_ms), 0) AS avg_latency_ms,
        COALESCE(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_latency_ms), 0) AS p50_latency_ms,
        COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_latency_ms), 0) AS p95_latency_ms,
        COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_latency_ms), 0) AS p99_latency_ms,
        COALESCE(AVG(NULLIF(ttft_ms, 0)), 0) AS avg_ttft_ms,
        COALESCE(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY NULLIF(ttft_ms, 0)), 0) AS p50_ttft_ms,
        COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY NULLIF(ttft_ms, 0)), 0) AS p95_ttft_ms,
        COALESCE(COUNT(*) FILTER (WHERE cache_hit = true), 0) AS cache_hits,
        COALESCE(COUNT(*) FILTER (WHERE status_code >= 400), 0) AS total_errors
    FROM request_metrics
    WHERE created_at >= now() - ($1 || ' hours')::interval
    """

    async def _fetch():
        pool = await get_pool()
        return await pool.fetchrow(query, str(hours))

    row = await run_with_db_retry(_fetch, label="get_metrics_overview")
    if not row:
        return {}

    total = row["total_requests"] or 0
    errors = row["total_errors"] or 0
    successful = max(0, total - errors)
    cache_hits = row["cache_hits"] or 0
    hit_rate = round((cache_hits / total * 100.0), 2) if total > 0 else 0.0
    err_rate = round((errors / total * 100.0), 2) if total > 0 else 0.0

    return {
        "status": "success",
        "window_hours": hours,
        "total_requests": total,
        "successful_requests": successful,
        "failed_requests": errors,
        "error_rate_pct": err_rate,
        "tokens": {
            "prompt_tokens": int(row["total_prompt_tokens"]),
            "completion_tokens": int(row["total_completion_tokens"]),
            "total_tokens": int(row["total_tokens"]),
        },
        "costs": {
            "total_cost_usd": round(float(row["total_cost_usd"]), 4),
            "total_cost_vnd": round(float(row["total_cost_vnd"]), 2),
        },
        "latency_ms": {
            "avg": round(float(row["avg_latency_ms"])),
            "p50": round(float(row["p50_latency_ms"])),
            "p95": round(float(row["p95_latency_ms"])),
            "p99": round(float(row["p99_latency_ms"])),
        },
        "ttft_ms": {
            "avg": round(float(row["avg_ttft_ms"])),
            "p50": round(float(row["p50_ttft_ms"])),
            "p95": round(float(row["p95_ttft_ms"])),
        },
        "caching": {
            "cache_hits": cache_hits,
            "cache_hit_rate_pct": hit_rate,
        },
    }


async def get_metrics_timeseries(hours: int = 24) -> dict[str, Any]:
    """Lấy dữ liệu chuỗi thời gian phân đoạn theo giờ."""
    await ensure_telemetry_schema()

    query = """
    SELECT
        date_trunc('hour', created_at) AS bucket,
        COUNT(*) AS requests,
        COALESCE(AVG(total_latency_ms), 0) AS avg_latency_ms,
        COALESCE(AVG(NULLIF(ttft_ms, 0)), 0) AS avg_ttft_ms,
        COALESCE(SUM(total_tokens), 0) AS total_tokens,
        COALESCE(SUM(cost_vnd), 0.0) AS cost_vnd,
        COALESCE(COUNT(*) FILTER (WHERE cache_hit = true), 0) AS cache_hits
    FROM request_metrics
    WHERE created_at >= now() - ($1 || ' hours')::interval
    GROUP BY bucket
    ORDER BY bucket ASC
    """

    async def _fetch():
        pool = await get_pool()
        return await pool.fetch(query, str(hours))

    rows = await run_with_db_retry(_fetch, label="get_metrics_timeseries")
    points = [
        {
            "bucket": r["bucket"].isoformat() if r["bucket"] else "",
            "requests": r["requests"],
            "avg_latency_ms": round(float(r["avg_latency_ms"])),
            "avg_ttft_ms": round(float(r["avg_ttft_ms"])),
            "total_tokens": int(r["total_tokens"]),
            "cost_vnd": round(float(r["cost_vnd"]), 2),
            "cache_hits": r["cache_hits"],
        }
        for r in rows
    ]
    return {"status": "success", "points": points}


async def get_metrics_intents(hours: int = 168) -> dict[str, Any]:
    """Phân bổ các loại câu hỏi (intent) và tỷ lệ phần trăm."""
    await ensure_telemetry_schema()

    query = """
    SELECT
        COALESCE(NULLIF(intent, ''), 'general') AS intent,
        COUNT(*) AS count
    FROM request_metrics
    WHERE created_at >= now() - ($1 || ' hours')::interval
    GROUP BY intent
    ORDER BY count DESC
    """

    async def _fetch():
        pool = await get_pool()
        return await pool.fetch(query, str(hours))

    rows = await run_with_db_retry(_fetch, label="get_metrics_intents")
    total_intent_count = sum(r["count"] for r in rows) if rows else 0

    intents = [
        {
            "intent": r["intent"],
            "count": r["count"],
            "percentage": round((r["count"] / total_intent_count * 100.0), 2) if total_intent_count > 0 else 0.0,
        }
        for r in rows
    ]
    return {"status": "success", "intents": intents}


async def get_metrics_logs(
    limit: int = 50,
    offset: int = 0,
    intent: str | None = None,
    cache_only: bool = False,
) -> dict[str, Any]:
    """Truy vấn danh sách request logs phục vụ debug và audit."""
    await ensure_telemetry_schema()
    conditions = ["1=1"]
    params = []
    p_idx = 1

    if intent:
        conditions.append(f"intent = ${p_idx}")
        params.append(intent)
        p_idx += 1

    if cache_only:
        conditions.append("cache_hit = true")

    where_clause = " AND ".join(conditions)

    count_query = f"SELECT COUNT(*) FROM request_metrics WHERE {where_clause}"

    query = f"""
    SELECT
        id, request_id, session_id, created_at, query_text, intent, decision,
        model_used, COALESCE(prompt_version, 'v1.0.0') as prompt_version,
        prompt_tokens, completion_tokens, total_tokens,
        cost_usd, cost_vnd, ttft_ms, ttot_ms, total_latency_ms,
        latency_retrieval_ms, latency_generation_ms,
        cache_hit, cache_type,
        tools_used, status_code, error_message,
        model_code, model_version, retrieval_status, chunks_retrieved, reasoning_tokens,
        user_feedback, feedback_comment
    FROM request_metrics
    WHERE {where_clause}
    ORDER BY created_at DESC
    LIMIT ${p_idx} OFFSET ${p_idx + 1}
    """
    fetch_params = list(params)
    fetch_params.extend([limit, offset])

    async def _fetch():
        pool = await get_pool()
        tot = await pool.fetchval(count_query, *params)
        rws = await pool.fetch(query, *fetch_params)
        return tot, rws

    total_count, rows = await run_with_db_retry(_fetch, label="get_metrics_logs")

    logs = []
    for r in rows:
        tools = r["tools_used"]
        if isinstance(tools, str):
            try:
                tools = json.loads(tools)
            except Exception:
                tools = []
        logs.append(
            {
                "id": r["id"],
                "request_id": r["request_id"],
                "session_id": str(r["session_id"]) if r["session_id"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                "query_text": r["query_text"],
                "intent": r["intent"],
                "decision": r["decision"],
                "model_used": r["model_used"],
                "prompt_version": r["prompt_version"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "total_tokens": r["total_tokens"],
                "cost_usd": float(r["cost_usd"]),
                "cost_vnd": float(r["cost_vnd"]),
                "ttft_ms": r["ttft_ms"],
                "ttot_ms": r["ttot_ms"] if "ttot_ms" in r else 0,
                "total_latency_ms": r["total_latency_ms"],
                "latency_retrieval_ms": r["latency_retrieval_ms"] if "latency_retrieval_ms" in r else 0,
                "latency_generation_ms": r["latency_generation_ms"] if "latency_generation_ms" in r else 0,
                "cache_hit": r["cache_hit"],
                "cache_type": r["cache_type"],
                "tools_used": tools,
                "status_code": r["status_code"],
                "error_message": r["error_message"],
                "model_code": r["model_code"] if "model_code" in r else None,
                "model_version": r["model_version"] if "model_version" in r else None,
                "retrieval_status": r["retrieval_status"] if "retrieval_status" in r else None,
                "chunks_retrieved": r["chunks_retrieved"] if "chunks_retrieved" in r else 0,
                "reasoning_tokens": r["reasoning_tokens"] if "reasoning_tokens" in r else 0,
                "user_feedback": r["user_feedback"] if "user_feedback" in r else None,
                "feedback_comment": r["feedback_comment"] if "feedback_comment" in r else None,
            }
        )

    return {"total": total_count, "limit": limit, "offset": offset, "logs": logs}


async def record_feedback(request_id: str, rating: int, comment: str | None = None) -> bool:
    """Ghi feedback 👍/👎 cho request. rating 1/-1, comment optional."""
    await ensure_telemetry_schema()
    try:

        async def _update():
            pool = await get_pool()
            await pool.execute(
                "UPDATE request_metrics SET user_feedback=$1, feedback_comment=$2 WHERE request_id=$3",
                rating,
                comment,
                request_id,
            )

        await run_with_db_retry(_update, label="record_feedback")
        return True
    except Exception as exc:
        logger.warning("Failed to record feedback: %s", exc)
        return False


async def get_metrics_realtime(window_min: int = 5) -> dict[str, Any]:
    """Realtime nhẹ: requests/min, avg latency, cache hit, errors trong vài phút gần nhất."""
    await ensure_telemetry_schema()
    query = """
    SELECT
        date_trunc('minute', created_at) AS bucket,
        COUNT(*) AS requests,
        COALESCE(AVG(total_latency_ms), 0) AS avg_latency_ms,
        COALESCE(AVG(NULLIF(ttft_ms, 0)), 0) AS avg_ttft_ms,
        COALESCE(COUNT(*) FILTER (WHERE cache_hit = true), 0) AS cache_hits,
        COALESCE(COUNT(*) FILTER (WHERE status_code >= 400), 0) AS errors
    FROM request_metrics
    WHERE created_at >= now() - ($1 || ' minutes')::interval
    GROUP BY bucket
    ORDER BY bucket ASC
    """

    async def _fetch():
        pool = await get_pool()
        return await pool.fetch(query, str(window_min))

    rows = await run_with_db_retry(_fetch, label="get_metrics_realtime")
    points = [
        {
            "bucket": r["bucket"].isoformat() if r["bucket"] else "",
            "requests": r["requests"],
            "avg_latency_ms": round(float(r["avg_latency_ms"])),
            "avg_ttft_ms": round(float(r["avg_ttft_ms"])),
            "cache_hits": r["cache_hits"],
            "errors": r["errors"],
        }
        for r in rows
    ]
    return {"status": "success", "window_min": window_min, "points": points}
