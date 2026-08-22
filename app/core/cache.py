"""
app/core/cache.py — Tool-result cache + embedding/search cache + data_version.

Cache key bao gồm data_version (đọc LIVE từ PG `ingest_version.is_current`)
→ promote v2→v3 ≤60s mọi key tự động đổi, key cũ mồ côi chết theo TTL.

Fail-open: Redis tắt → miss cache, vẫn query DB/Qdrant bình thường.

Các tầng cache:
  - tool:*   — entity-keyed specs/colors/options/list_models (đã có từ trước)
  - emb:     — embedding vector cache (7 ngày, deterministic)
  - hs:      — hybrid_search full-pipeline cache (2 giờ)
  - kb:      — knowledge base search cache (2 giờ)
  - ans:     — answer cache single-turn (30 phút, PHASE SAU)

Các hàm `*_cached` trả tuple `(data, cache_hit)`.
`get_price` cache 15 phút (theo docs), `get_active_promotions` không cache (link tĩnh).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from typing import Any

from app.config import settings
from app.core.memory import get_redis

logger = logging.getLogger("bds.cache")

# ── TTL phân tầng ─────────────────────────────────────────────────────────────
SPECS_TTL = 24 * 3600
COLORS_TTL = 24 * 3600
OPTIONS_TTL = 24 * 3600
LIST_MODELS_TTL = 1 * 3600
KB_TTL = 2 * 3600
TOOL_PRICE_TTL = 15 * 60  # 15 phút cho giá — theo docs
EMBEDDING_TTL = 7 * 24 * 3600  # 7 ngày — embedding deterministic
HYBRID_TTL = 2 * 3600  # 2 giờ — dense+sparse+rerank pipeline
ANS_TTL = 30 * 60  # 30 phút — answer single-turn (PHASE SAU)

# TTL phân tầng theo topic (volatility axis) — theo docs/CACHE_SYSTEM.md & CACHING_DESIGN.md
# Docs chuẩn: price/khuyến_mãi 15 phút, specs/colors 24h, list_models 1h, ans 30m, hs 2h, emb 7d
CACHE_TTL_BY_TOPIC = {
    "thông_số_kỹ_thuật": 24 * 3600,
    "kích_thước": 24 * 3600,
    "an_toàn": 24 * 3600,
    "nội_thất": 24 * 3600,
    "ngoại_thất": 24 * 3600,
    "pin_và_sạc": 24 * 3600,
    "phạm_vi_di_chuyển": 24 * 3600,
    "màu_sắc": 24 * 3600,
    "option": 24 * 3600,
    "giá": 15 * 60,  # 15 phút theo docs — trước đây None
    "khuyến_mãi": 15 * 60,
    "list_models": LIST_MODELS_TTL,
}


# spec_category → TTL đặc biệt (kích_thước bền hơn thông số).
_SPEC_CATEGORY_TTL = {
    "dimension": CACHE_TTL_BY_TOPIC["kích_thước"],
}

# ── Data version (chống stale) ───────────────────────────────────────────────
_dv_cache: str = "unknown"
_dv_cache_time: float = 0.0
_DV_TTL = 60  # giây — promote lan toả ≤60s, không cần restart


async def data_version() -> str:
    """SELECT version FROM ingest_version WHERE is_current LIMIT 1.
    Cache in-memory 60s. Fallback: "unknown" (PG unreachable → miss cache)."""
    global _dv_cache, _dv_cache_time
    now = time.time()
    if now - _dv_cache_time < _DV_TTL:
        return _dv_cache
    try:
        from app.core.db import get_pool

        pool = await get_pool()
        ver = await pool.fetchval("SELECT version FROM ingest_version WHERE is_current LIMIT 1")
        if ver:
            _dv_cache = ver
            _dv_cache_time = now
            return ver
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("data_version query failed: %s", e)
    return _dv_cache  # trả "unknown" hoặc version cũ


# ── Normalization helpers ─────────────────────────────────────────────────────
def _norm(value: str | None) -> str:
    if not value:
        return "all"
    return value.strip().lower().replace(" ", "")


def _norm_query(query: str) -> str:
    """Chuẩn hoá query cho cache key: NFC → lowercase → gộp whitespace → bỏ punctuation."""
    q = unicodedata.normalize("NFC", query or "").lower()
    q = re.sub(r"[^\w\s]", " ", q, flags=re.UNICODE)
    return re.sub(r"\s+", " ", q).strip()


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ── Cache key builders (dv = data_version, awaited trước khi build key) ──────
def _specs_key(dv: str, model_code: str, version: str | None, category: str | None) -> str:
    return f"cache:{dv}:specs:{_norm(model_code)}:{_norm(version)}:{_norm(category)}"


def _colors_key(dv: str, model_code: str, version: str | None) -> str:
    return f"cache:{dv}:colors:{_norm(model_code)}:{_norm(version)}"


def _options_key(dv: str, model_code: str, version: str | None) -> str:
    return f"cache:{dv}:options:{_norm(model_code)}:{_norm(version)}"


def _list_models_key(dv: str) -> str:
    return f"cache:{dv}:list_models"


def _specs_ttl(category: str | None) -> int:
    return _SPEC_CATEGORY_TTL.get(category, SPECS_TTL)


def _kb_key(dv: str, query: str, model_id: str | None, collections: list[str] | None = None) -> str:
    digest = hashlib.sha256(_norm_query(query).encode("utf-8")).hexdigest()[:16]
    cols = _sha1("|".join(sorted(collections))) if collections else "all"
    return f"cache:kb:{dv}:{_norm(model_id)}:{digest}:{cols}"


def _emb_key(text: str) -> str:
    # Unified key — dùng openai_embed_model (alias openrouter_embed_model vẫn trỏ cùng giá trị)
    return f"emb:{settings.openai_embed_model}:{_sha1(text)}"


def _hs_key(
    dv: str, query: str, model_id: str | None, top_k: int, skip_rerank: bool, collections: list[str] | None = None
) -> str:
    qh = _sha1(_norm_query(query))
    mid = _norm(model_id)
    cols = _sha1("|".join(sorted(collections))) if collections else "all"
    return f"hs:{dv}:{qh}:{mid}:{top_k}:{int(skip_rerank)}:{cols}"


# ── Redis get/set/delete (fail-open) ─────────────────────────────────────────


async def _get_json(key: str) -> Any | None:
    r = get_redis()
    if not r:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("cache get failed (fail-open): %s", e)
        return None


async def _set_json(key: str, value: Any, ttl: int) -> None:
    if not getattr(settings, "cache_enabled", True):
        return
    r = get_redis()
    if not r:
        return
    try:
        await r.set(key, json.dumps(value, ensure_ascii=False), ex=int(ttl))
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("cache set failed (fail-open): %s", e)


async def _delete(key: str) -> None:
    r = get_redis()
    if not r:
        return
    try:
        await r.delete(key)
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("cache delete failed (fail-open): %s", e)


async def _delete_by_pattern(pattern: str) -> int:
    """Xóa các key khớp pattern bằng SCAN (không KEYS — tránh block)."""
    r = get_redis()
    if not r:
        return 0
    deleted = 0
    try:
        keys: list[str] = []
        async for k in r.scan_iter(match=pattern, count=500):
            keys.append(k)
        if keys:
            deleted = await r.delete(*keys)
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("cache scan-delete failed (fail-open): %s", e)
    return int(deleted or 0)


# ── Embedding cache (emb:) ───────────────────────────────────────────────────


async def get_embedding_cached(text: str) -> list[float] | None:
    """Lấy cached embedding vector. None nếu miss."""
    key = _emb_key(text)
    r = get_redis()
    if not r:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def set_embedding_cached(text: str, embedding: list[float]) -> None:
    key = _emb_key(text)
    await _set_json(key, embedding, EMBEDDING_TTL)


# ── Hybrid search cache (hs:) ────────────────────────────────────────────────


async def get_hybrid_cached(
    query: str, model_id: str | None, top_k: int, skip_rerank: bool, collections: list[str] | None = None
) -> list[dict] | None:
    """Lấy cached hybrid_search kết quả. None nếu miss."""
    dv = await data_version()
    key = _hs_key(dv, query, model_id, top_k, skip_rerank, collections)
    return await _get_json(key)


async def set_hybrid_cached(
    query: str,
    model_id: str | None,
    top_k: int,
    skip_rerank: bool,
    results: list[dict],
    collections: list[str] | None = None,
) -> None:
    dv = await data_version()
    key = _hs_key(dv, query, model_id, top_k, skip_rerank, collections)
    await _set_json(key, results, HYBRID_TTL)


# ── Entity-keyed cached tools ─────────────────────────────────────────────────


async def get_price_cached(model_code: str, version: str | None = None):
    """Cache get_price 15 phút — theo docs/CACHE_SYSTEM.md (tool:price)."""
    dv = await data_version()
    # key riêng cho price: cache:{dv}:price:{model}:{version}
    key = f"cache:{dv}:price:{_norm(model_code)}:{_norm(version)}"
    cached = await _get_json(key)
    if cached is not None:
        return cached, True
    from app.agent.tools import get_price

    data = await get_price(model_code, version)
    await _set_json(key, data, TOOL_PRICE_TTL)
    return data, False


async def get_specs_cached(model_code: str, version: str | None = None, category: str | None = None):
    dv = await data_version()
    key = _specs_key(dv, model_code, version, category)
    cached = await _get_json(key)
    if cached is not None:
        return cached, True

    from app.agent.tools import get_specs

    data = await get_specs(model_code, version, category)
    await _set_json(key, data, _specs_ttl(category))
    return data, False


async def get_colors_cached(model_code: str, version: str | None = None):
    dv = await data_version()
    key = _colors_key(dv, model_code, version)
    cached = await _get_json(key)
    if cached is not None:
        return cached, True

    from app.agent.tools import get_colors

    data = await get_colors(model_code, version)
    await _set_json(key, data, COLORS_TTL)
    return data, False


async def get_options_cached(model_code: str, version: str | None = None):
    dv = await data_version()
    key = _options_key(dv, model_code, version)
    cached = await _get_json(key)
    if cached is not None:
        return cached, True

    from app.agent.tools import get_options

    data = await get_options(model_code, version)
    await _set_json(key, data, OPTIONS_TTL)
    return data, False


async def list_models_cached():
    dv = await data_version()
    lm_key = _list_models_key(dv)
    cached = await _get_json(lm_key)
    if cached is not None:
        return cached, True

    from app.agent.tools import list_available_models

    data = await list_available_models()
    await _set_json(lm_key, data, LIST_MODELS_TTL)
    return data, False


async def search_kb_cached(query: str, model_id: str | None = None, collections: list[str] | None = None, skip_rerank: bool = False) -> dict:
    """KB search cache (TTL 2h). `model_id` đã được chuẩn hóa `_model_id` ở tools."""
    dv = await data_version()
    key = _kb_key(dv, query, model_id, collections)
    cached = await _get_json(key)
    if cached is not None:
        return cached

    from app.core.retrieval import hybrid_search

    results = await hybrid_search(query, model_id=model_id, top_k=5, collections=collections, skip_rerank=skip_rerank)
    data = {
        "query": query,
        "results": [
            {
                "text": r["text"],
                "model_id": r["model_id"],
                "text_type": r["text_type"],
                "source_type": r["source_type"],
                "source_url": r["source_url"],
                "score": round(r["score"], 3),
            }
            for r in results
        ],
    }
    await _set_json(key, data, KB_TTL)
    return data


# ── Invalidation ──────────────────────────────────────────────────────────────


async def invalidate_entity(cache_key: str) -> None:
    """Xóa 1 key cache cụ thể."""
    await _delete(cache_key)


async def invalidate_model(model_code: str) -> int:
    """Xóa toàn bộ cache specs/colors/options của một model (SCAN prefix)."""
    norm = _norm(model_code)
    total = 0
    for prefix in ("specs:", "colors:", "options:"):
        total += await _delete_by_pattern(f"cache:*:{prefix}{norm}:*")
    return total


async def invalidate_all() -> int:
    """Xóa cache specs/colors/options + list_models + hs + kb (dùng khi đổi version active)."""
    total = 0
    for prefix in ("cache:", "hs:", "cache:kb:"):
        total += await _delete_by_pattern(f"{prefix}*")
    # Reset data_version memo để key mới sinh ngay sau promote
    global _dv_cache_time
    _dv_cache_time = 0.0
    return total
