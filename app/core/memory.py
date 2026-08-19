"""
app/core/memory.py — Redis-backed session store + long-term memory.

Chuyển multi-turn session khỏi RAM/client sang Redis, tách biệt:
  - `history`         : sliding window các lượt hội thoại (short-term).
  - `current_context` : hash chứa model_code/version/last_topic — "phao cứu sinh"
                        khi history bị cắt, dùng cho query ellipsis.
  - Long-term memory  : fact/preference keyed by user_id (fallback session_id).

Fail-open: Redis tắt → trả default (`history=[]`, context `{}`), không crash.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

from app.config import settings

logger = logging.getLogger("bds.memory")

SESSION_TTL = timedelta(hours=6)
MAX_TURNS = 10          # sliding window history (số cặp user/assistant)
LTM_TTL = timedelta(days=30)

_client = None
_client_ok = True


def get_redis():
    """Lazy singleton Redis client (decode_responses=True). None nếu không dùng được."""
    global _client, _client_ok
    if _client is not None:
        return _client
    if not _client_ok:
        return None
    try:
        import redis.asyncio as aioredis
        _client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5.0,
            socket_timeout=5.0,
            retry_on_timeout=True,
        )
    except Exception as e:  # pragma: no cover - fail-open
        logger.warning("Redis unavailable (memory disabled): %s", e)
        _client_ok = False
        _client = None
    return _client


def _loads(value: Any) -> Any:
    """decode_responses trả string; json.loads cho giá trị nested nếu có thể."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _history_key(session_id: str) -> str:
    return f"session:{session_id}:history"


def _context_key(session_id: str) -> str:
    return f"session:{session_id}:context"


def _profile_key(user_id: str) -> str:
    return f"user:{user_id}:profile"


# ── Session store (short-term) ────────────────────────────────────────────────

async def load_session(session_id: str) -> dict:
    """Trả {"history": [...], "current_context": {...}}. Default khi Redis tắt.

    History lưu dạng Redis LIST (mỗi element = 1 JSON message) để append atomic.
    Fallback legacy JSON-string format nếu gặp key cũ.
    """
    r = get_redis()
    if not r:
        return {"history": [], "current_context": {}}

    hist_key = _history_key(session_id)
    ctx_key = _context_key(session_id)
    try:
        items, raw_ctx = await asyncio.gather(
            r.lrange(hist_key, 0, -1), r.hgetall(ctx_key),
        )
        history = [json.loads(i) for i in items if i]
    except Exception:
        # Legacy: history là 1 JSON string (format cũ) → fallback đọc string
        try:
            raw = await r.get(hist_key)
            history = json.loads(raw) if raw else []
            raw_ctx = await r.hgetall(ctx_key)
        except Exception:
            history, raw_ctx = [], {}

    current_context: dict = {k: _loads(v) for k, v in (raw_ctx or {}).items()}
    return {"history": history, "current_context": current_context}


async def save_turn(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """Append 2 lượt (user + assistant) atomic bằng RPUSH + LTRIM sliding window.

    Dùng Redis LIST thay vì GET→append→SET (read-modify-write) để tránh mất lượt
    khi 2 request cùng session chạy đồng thời. Không đụng current_context.
    """
    r = get_redis()
    if not r:
        return

    hist_key = _history_key(session_id)
    ctx_key = _context_key(session_id)
    ttl = int(SESSION_TTL.total_seconds())
    try:
        pipe = r.pipeline()
        pipe.rpush(
            hist_key,
            json.dumps({"role": "user", "content": user_msg}, ensure_ascii=False),
            json.dumps({"role": "assistant", "content": assistant_msg}, ensure_ascii=False),
        )
        # Sliding window: giữ MAX_TURNS cặp = MAX_TURNS * 2 message
        pipe.ltrim(hist_key, -(MAX_TURNS * 2), -1)
        pipe.expire(hist_key, ttl)
        pipe.expire(ctx_key, ttl)
        await pipe.execute()
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("save_turn failed (fail-open): %s", e)


async def update_current_context(
    session_id: str,
    model_code: str | None = None,
    version: str | None = None,
    topic: str | None = None,
) -> None:
    """hset field non-null vào session context. Tách khỏi history slider."""
    r = get_redis()
    if not r:
        return

    mapping = {}
    if model_code:
        mapping["model_code"] = model_code
    if version:
        mapping["version"] = version
    if topic:
        mapping["last_topic"] = topic
    if not mapping:
        return

    ctx_key = _context_key(session_id)
    try:
        await r.hset(ctx_key, mapping=mapping)
        await r.expire(ctx_key, int(SESSION_TTL.total_seconds()))
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("update_current_context failed (fail-open): %s", e)


# ── Long-term memory (keyed by user_id) ──────────────────────────────────────

async def load_user_facts(user_id: str) -> dict:
    """Đọc toàn bộ fact từ hash user:{uid}:profile."""
    r = get_redis()
    if not r:
        return {}
    try:
        raw = await r.hgetall(_profile_key(user_id))
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("load_user_facts failed (fail-open): %s", e)
        return {}
    return {k: _loads(v) for k, v in (raw or {}).items()}


async def load_user_profile(user_id: str) -> dict:
    """Alias của load_user_facts — profile user keyed bởi user_id."""
    return await load_user_facts(user_id)


async def save_user_fact(user_id: str, field: str, value: Any) -> None:
    """hset 1 fact + expire LTM_TTL. value nested được json.dumps."""
    r = get_redis()
    if not r:
        return
    stored = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    try:
        key = _profile_key(user_id)
        await r.hset(key, field, stored)
        await r.expire(key, int(LTM_TTL.total_seconds()))
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("save_user_fact failed (fail-open): %s", e)