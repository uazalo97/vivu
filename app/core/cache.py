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


def _kb_key(dv: str, query: str, model_id: str | None) -> str:
    digest = hashlib.sha256(_norm_query(query).encode("utf-8")).hexdigest()[:16]
    return f"cache:kb:{dv}:{_norm(model_id)}:{digest}"


def _emb_key(text: str) -> str:
    # Unified key — dùng openai_embed_model (alias openrouter_embed_model vẫn trỏ cùng giá trị)
    return f"emb:{settings.openai_embed_model}:{_sha1(text)}"


def _hs_key(dv: str, query: str, model_id: str | None, top_k: int, skip_rerank: bool) -> str:
    qh = _sha1(_norm_query(query))
    mid = _norm(model_id)
    return f"hs:{dv}:{qh}:{mid}:{top_k}:{int(skip_rerank)}"
# ── Answer cache (ans:) — L1 exact-match single-turn ─────────────────────────
# Chỉ cache khi single-turn (history == []), session_id non-empty,
# intent ∉ {greeting,clarify,out_of_scope,chitchat}. Fail-open.
_ANS_NON_CACHEABLE_INTENTS = {"greeting", "clarify", "out_of_scope", "chitchat"}


def _is_cacheable(
    history: list | None,
    session_id: str | None,
    intent: str | None = None,
) -> bool:
    """L1 gate: history==[] (falsy) + session_id truthy + intent not in blocklist.

    - history: chỉ cache khi falsy hoặc rỗng (single-turn). multi-turn → False
    - session_id: phải non-empty
    - intent: None → cho qua (agent_loop sẽ classify sau); lower() so với blocklist
    - CACHE_ENABLED=false → False (không cache)
    """
    if not getattr(settings, "cache_enabled", True):
        return False
    if history:
        return False
    if not session_id:
        return False
    if intent is not None:
        try:
            iv = str(intent).strip().lower()
        except Exception:
            iv = ""
        if iv in _ANS_NON_CACHEABLE_INTENTS:
            return False
    return True


async def make_answer_key(
    query: str | None = None,
    model_code: str | None = None,
    version: str | None = None,
    intent: str | None = None,
    entities: dict | None = None,
    **kwargs,
) -> str:
    """Build deterministic L1 ans key: ``ans:{dv}:{prompt_hash}:{llm}:{sha1(entities|norm_query)}``.

    Hỗ trợ nhiều kiểu gọi để tương thích legacy test và spec:
    - ``await make_answer_key(query, model_code, version)``
    - ``await make_answer_key(query="...", entities={"model": "VF 8", ...})``
    - ``await make_answer_key(entities={...}, query="...")``
    - ``await make_answer_key(query, entities)`` (entities là dict vị trí thứ 2)

    - ``dv``: await data_version() memo 60s LIVE
    - ``prompt_hash``: local import ``get_prompt_hash()`` 12-char (tránh import cycle)
    - ``llm``: settings.llm_model (đã strip prefix trong config)
    - ``sha``: _sha1(entities_str|norm_query)[:16] với entities_str = norm(model_code)|norm(version)
      (kèm intent nếu có để phân biệt intent khác nhau)
    """
    # --- Resolve flexible args / aliases ---
    # query có thể bị truyền như dict ở vị trí đầu (swap)
    if isinstance(query, dict) and entities is None:
        entities = query
        query = kwargs.pop("query", kwargs.pop("q", "")) or ""

    if query is None:
        query = kwargs.pop("query", None)
        if query is None:
            query = kwargs.pop("q", None)
        if query is None:
            query = ""

    if not isinstance(query, str):
        query = str(query) if query is not None else ""

    # model_code là dict → thực chất là entities positional
    if isinstance(model_code, dict) and entities is None:
        entities = model_code
        model_code = None

    if entities is None:
        entities = kwargs.pop("entities", None)
        if entities is None:
            entities = kwargs.pop("entity", None)

    # kwargs aliases cho model_code / version / intent
    if model_code is None:
        model_code = kwargs.pop("model_code", None)
        if model_code is None:
            model_code = kwargs.pop("model", None)
            if model_code is None:
                model_code = kwargs.pop("model_id", None)
                if model_code is None:
                    model_code = kwargs.pop("modelCode", None)
    if version is None:
        version = kwargs.pop("version", None)
        if version is None:
            version = kwargs.pop("ver", None)
    if intent is None:
        intent = kwargs.pop("intent", None)

    # Trích từ entities dict nếu còn thiếu
    if isinstance(entities, dict):
        if model_code is None:
            model_code = entities.get("model_code")
            if model_code is None:
                model_code = entities.get("model")
                if model_code is None:
                    model_code = entities.get("model_id")
        if version is None:
            version = entities.get("version")
        if intent is None:
            intent = entities.get("intent")

    # Fallback deterministic via classifier nếu vẫn thiếu model/version
    if (model_code is None or version is None) and query:
        try:
            from app.agent.classifier import get_classifier

            cls = get_classifier()
            try:
                cr = cls.classify(query)
                if cr is not None and getattr(cr, "entities", None):
                    ents = cr.entities or {}
                    if model_code is None:
                        mc = ents.get("model_code")
                        if mc:
                            model_code = mc
                    if version is None:
                        vc = ents.get("version")
                        if vc:
                            version = vc
                elif model_code is None:
                    try:
                        detected, _raw = cls._detect_model(query)  # type: ignore[attr-defined]
                        if detected:
                            model_code = detected
                    except Exception:
                        pass
            except Exception:
                if model_code is None:
                    try:
                        detected, _raw = cls._detect_model(query)  # type: ignore[attr-defined]
                        if detected:
                            model_code = detected
                    except Exception:
                        pass
        except Exception:
            pass

    norm_q = _norm_query(query or "")
    entities_str = f"{_norm(model_code)}|{_norm(version)}"
    if intent is not None and str(intent).strip() != "":
        hash_input = f"{entities_str}|{_norm(intent)}|{norm_q}"
    else:
        hash_input = f"{entities_str}|{norm_q}"
    sha = _sha1(hash_input)

    dv = await data_version()

    # prompt_hash via local import (tránh cycle), sync 12-char
    prompt_hash = "unknown"
    try:
        from app.agent.prompts import get_prompt_hash  # local import

        ph = get_prompt_hash()
        import inspect

        if inspect.isawaitable(ph):
            ph = await ph  # type: ignore[func-returns-value]
        if isinstance(ph, str) and ph:
            prompt_hash = ph
        elif ph is not None:
            prompt_hash = str(ph)
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("get_prompt_hash failed (fail-open): %s", e)
        prompt_hash = "unknown"

    llm_model = getattr(settings, "llm_model", "unknown")
    if isinstance(llm_model, str) and "/" in llm_model:
        llm_model = llm_model.split("/", 1)[-1]
    llm_model = llm_model.strip() if isinstance(llm_model, str) else str(llm_model)
    if not llm_model:
        llm_model = "unknown"

    return f"ans:{dv}:{prompt_hash}:{llm_model}:{sha}"


async def get_ans_cached(key: str) -> dict | None:
    """Lấy cached answer via _get_json (fail-open)."""
    try:
        return await _get_json(key)
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("get_ans_cached failed (fail-open): %s", e)
        return None


async def set_ans_cached(key: str, value: dict) -> None:
    """Set cached answer via _set_json với ANS_TTL 30m (fail-open, CACHE_ENABLED gate)."""
    try:
        await _set_json(key, value, ANS_TTL)
    except Exception as e:  # pragma: no cover - fail-open
        logger.debug("set_ans_cached failed (fail-open): %s", e)
        return



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


async def get_hybrid_cached(query: str, model_id: str | None, top_k: int, skip_rerank: bool) -> list[dict] | None:
    """Lấy cached hybrid_search kết quả. None nếu miss."""
    dv = await data_version()
    key = _hs_key(dv, query, model_id, top_k, skip_rerank)
    return await _get_json(key)


async def set_hybrid_cached(
    query: str, model_id: str | None, top_k: int, skip_rerank: bool, results: list[dict]
) -> None:
    dv = await data_version()
    key = _hs_key(dv, query, model_id, top_k, skip_rerank)
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


async def search_kb_cached(query: str, model_id: str | None = None) -> dict:
    """KB search cache (TTL 2h). `model_id` đã được chuẩn hóa `_model_id` ở tools."""
    dv = await data_version()
    key = _kb_key(dv, query, model_id)
    cached = await _get_json(key)
    if cached is not None:
        return cached

    from app.core.retrieval import hybrid_search

    results = await hybrid_search(query, model_id=model_id, top_k=5)
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
    try:
        from app.core.retrieval import invalidate_sparse_cache

        invalidate_sparse_cache()
    except Exception:
        pass
    return total
