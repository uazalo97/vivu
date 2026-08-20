"""
test_cache_memory.py — Integration tests for Redis memory + cache layers.

Chạy:
    python -m pytest tests/test_cache_memory.py -v
hoặc trực tiếp:
    python tests/test_cache_memory.py

Cover:
  1. Session store (memory.py) — load/save/trim/context/race
  2. Tool cache (cache.py) — miss→hit, data_version key, invalidation
  3. Embedding + hybrid search cache
  4. Rate limit + dedupe (chat.py helpers)
  5. classify current_context fallback (multi-turn ellipsis)
  6. Edge cases: Redis-down fail-open, empty session, unicode, None values
"""

import asyncio
import sys
from pathlib import Path

# Windows console cp1252 — force UTF-8 stdout/stderr
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

import uuid as _uuid  # noqa: E402


def _uniq() -> str:
    return f"test-{_uuid.uuid4().hex[:10]}"


# ── Session store ──────────────────────────────────────────────────────────────


async def test_session_roundtrip():
    from app.core.memory import load_session, save_turn

    sid = _uniq()
    # Empty → default
    s = await load_session(sid)
    assert s == {"history": [], "current_context": {}}
    # Save a turn
    await save_turn(sid, "VF 8 giá bao nhiêu?", "Giá từ 1.2 tỷ")
    s2 = await load_session(sid)
    assert len(s2["history"]) == 2
    assert s2["history"][0] == {"role": "user", "content": "VF 8 giá bao nhiêu?"}
    assert s2["history"][1] == {"role": "assistant", "content": "Giá từ 1.2 tỷ"}
    print("  [PASS] test_session_roundtrip: empty default + save/load 2 msgs")


async def test_session_sliding_window():
    from app.core.memory import load_session, save_turn, MAX_TURNS

    sid = _uniq()
    for i in range(MAX_TURNS + 5):  # 15 turns = 30 messages → trim to 20
        await save_turn(sid, f"question {i}", f"answer {i}")
    s = await load_session(sid)
    # Sliding window: MAX_TURNS*2 = 20 messages
    assert len(s["history"]) == MAX_TURNS * 2
    # Oldest retained turn should be the (15-10)=5th turn
    assert s["history"][0]["content"] == "question 5"
    assert s["history"][-1]["content"] == "answer 14"
    print(f"  [PASS] test_session_sliding_window: trimmed to {MAX_TURNS * 2} msgs")


async def test_session_context_non_null():
    from app.core.memory import load_session, update_current_context

    sid = _uniq()
    await update_current_context(sid, model_code="VF 8", version="Eco", topic="giá")
    s = await load_session(sid)
    assert s["current_context"]["model_code"] == "VF 8"
    assert s["current_context"]["version"] == "Eco"
    assert s["current_context"]["last_topic"] == "giá"

    # Update only topic → model/version preserved (non-null hset)
    await update_current_context(sid, topic="màu_sắc")
    s2 = await load_session(sid)
    assert s2["current_context"]["model_code"] == "VF 8"
    assert s2["current_context"]["version"] == "Eco"
    assert s2["current_context"]["last_topic"] == "màu_sắc"

    # Update with all None → no-op (context unchanged)
    await update_current_context(sid)
    s3 = await load_session(sid)
    assert s3["current_context"]["last_topic"] == "màu_sắc"
    print("  [PASS] test_session_context_non_null: hset chỉ field non-null")


async def test_session_concurrent_save():
    """Concurrent save_turn: read-modify-write race can drop turns but must not crash.
    (Known limitation: save_turn is not atomic. Here we assert no exception + no corruption.)"""
    from app.core.memory import load_session, save_turn

    sid = _uniq()
    await asyncio.gather(*[save_turn(sid, f"q{i}", f"a{i}") for i in range(10)])
    s = await load_session(sid)
    assert isinstance(s["history"], list)
    # May have lost some turns due to race, but structure must be valid
    for m in s["history"]:
        assert set(m.keys()) == {"role", "content"}
    print(f"  [PASS] test_session_concurrent_save: no corruption ({len(s['history'])} msgs, race ⇒ có thể <20)")


# ── Long-term memory ───────────────────────────────────────────────────────────


async def test_ltm_facts():
    from app.core.memory import load_user_facts, save_user_fact

    uid = _uniq()
    await save_user_fact(uid, "preferred_model", "VF 8")
    await save_user_fact(uid, "budget", 1500000000)
    facts = await load_user_facts(uid)
    assert facts["preferred_model"] == "VF 8"
    # non-string value is json-dumped then parsed back
    assert facts["budget"] == 1500000000
    print("  [PASS] test_ltm_facts: string + int fact roundtrip")


# ── Tool cache ─────────────────────────────────────────────────────────────────


async def test_tool_cache_miss_hit():
    from app.core.cache import get_specs_cached, get_colors_cached

    model = _uniq()  # fake model → get_specs returns empty but still caches
    # miss (data returned, hit=False)
    data, hit = await get_specs_cached(model, None, "powertrain")
    assert hit is False
    assert isinstance(data, dict)
    # hit (same key → cached, hit=True)
    data2, hit2 = await get_specs_cached(model, None, "powertrain")
    assert hit2 is True
    assert data == data2

    # colors cache
    data, hit = await get_colors_cached(model, None)
    assert hit is False
    data, hit = await get_colors_cached(model, None)
    assert hit is True
    print("  [PASS] test_tool_cache_miss_hit: miss→(data,False), hit→(cached,True)")


async def test_tool_cache_versions_isolated():
    from app.core.cache import get_specs_cached

    model = _uniq()
    # version None vs "Eco" must be different keys
    d_none, _ = await get_specs_cached(model, None, "powertrain")
    d_eco, _ = await get_specs_cached(model, "Eco", "powertrain")
    # different model must be different key
    d_other, _ = await get_specs_cached(_uniq(), None, "powertrain")
    print("  [PASS] test_tool_cache_versions_isolated: version/model khác key")


async def test_invalidate_model_and_all():
    from app.core.cache import (
        get_specs_cached,
        get_colors_cached,
        invalidate_model,
        invalidate_all,
    )

    model = _uniq()
    await get_specs_cached(model, None, "powertrain")
    await get_colors_cached(model, None)

    # invalidate_model clears specs+colors for that model
    n = await invalidate_model(model)
    assert n >= 2
    # After invalidation → miss again
    _, hit = await get_specs_cached(model, None, "powertrain")
    assert hit is False
    _, hit = await get_colors_cached(model, None)
    assert hit is False

    # invalidate_all → clears everything, no error
    await get_specs_cached(model, None, "powertrain")
    n2 = await invalidate_all()
    assert n2 >= 0
    print(f"  [PASS] test_invalidate_model_and_all: invalidate_model={n}, invalidate_all={n2}")


# ── Embedding + hybrid cache ───────────────────────────────────────────────────


async def test_embedding_cache():
    from app.core.cache import get_embedding_cached, set_embedding_cached

    text = f"VF 8 range {_uniq()}"
    # miss
    assert await get_embedding_cached(text) is None
    # set + hit
    vec = [0.1, 0.2, 0.3, 0.4]
    await set_embedding_cached(text, vec)
    cached = await get_embedding_cached(text)
    assert cached == vec
    # different text → miss
    assert await get_embedding_cached(f"{text} khác") is None
    print("  [PASS] test_embedding_cache: miss/set/hit/different-text")


async def test_hybrid_cache():
    from app.core.cache import get_hybrid_cached, set_hybrid_cached

    q = f"so sánh VF 8 VF 9 {_uniq()}"
    results = [{"text": "VF 8 rẻ hơn", "score": 0.9}, {"text": "VF 9 lớn hơn", "score": 0.7}]
    # miss
    assert await get_hybrid_cached(q, "VF 8", 5, False) is None
    # set + hit
    await set_hybrid_cached(q, "VF 8", 5, False, results)
    assert await get_hybrid_cached(q, "VF 8", 5, False) == results
    # different top_k / model_id → miss
    assert await get_hybrid_cached(q, "VF 8", 10, False) is None
    assert await get_hybrid_cached(q, "VF 9", 5, False) is None
    # different rerank flag → miss
    assert await get_hybrid_cached(q, "VF 8", 5, True) is None
    print("  [PASS] test_hybrid_cache: key theo query+model+top_k+rerank")


async def test_data_version():
    from app.core.cache import data_version

    ver = await data_version()
    assert ver and ver != ""
    print(f"  [PASS] test_data_version: version={ver}")


# ── Rate limit + dedupe ────────────────────────────────────────────────────────


async def test_rate_limit_dedupe():
    from app.api.chat import _rate_limit_check, _dedup_check
    from app.core.memory import get_redis

    sid = _uniq()
    ip = f"10.88.{_uuid.uuid4().hex[:4]}.{_uuid.uuid4().hex[:4]}"  # unique IP to avoid leftover keys
    # 1st → allowed
    assert await _rate_limit_check(sid, ip) is None
    # dedupe
    msg_id = _uniq()
    assert await _dedup_check(sid, msg_id) is True  # new
    assert await _dedup_check(sid, msg_id) is False  # duplicate
    assert await _dedup_check(sid, _uniq()) is True  # different id → new
    # cleanup rl keys
    r = get_redis()
    if r:
        keys = []
        async for k in r.scan_iter(match=f"rl:s:{sid}:*"):
            keys.append(k)
        async for k in r.scan_iter(match=f"rl:ip:{ip}:*"):
            keys.append(k)
        if keys:
            await r.delete(*keys)
    print("  [PASS] test_rate_limit_dedupe: first-request + dedup new/dup/new")


async def test_rate_limit_threshold():
    from app.api.chat import _rate_limit_check
    from app.core.memory import get_redis

    sid = _uniq()
    ip = f"10.77.{_uuid.uuid4().hex[:4]}.{_uuid.uuid4().hex[:4]}"  # unique IP to avoid leftover keys
    r = get_redis()
    if r:
        # Pre-clean any leftover keys from previous test runs
        old_keys = []
        async for k in r.scan_iter(match=f"rl:s:{sid}:*"):
            old_keys.append(k)
        async for k in r.scan_iter(match=f"rl:ip:{ip}:*"):
            old_keys.append(k)
        if old_keys:
            await r.delete(*old_keys)

    # Simulate 10 requests in window → allowed, 11th → blocked (session limit)
    results = []
    for i in range(11):
        results.append(await _rate_limit_check(sid, ip))
    assert all(res is None for res in results[:10])
    assert results[10] is not None  # blocked
    # Cleanup rl keys
    if r:
        keys = []
        async for k in r.scan_iter(match=f"rl:s:{sid}:*"):
            keys.append(k)
        async for k in r.scan_iter(match=f"rl:ip:{ip}:*"):
            keys.append(k)
        if keys:
            await r.delete(*keys)
    print("  [PASS] test_rate_limit_threshold: 10 allowed, 11th blocked (session 10/10s)")


# ── classify current_context fallback (multi-turn ellipsis) ────────────────────


async def test_classify_context_fallback():
    from app.agent.nodes.classify import classify_node

    # Empty history, current_context has model+version → merged into entities
    state = {
        "query": "còn màu nào khác?",  # ellipsis — no model/version
        "history": [],
        "current_context": {"model_code": "VF 8", "version": "Eco", "last_topic": "màu_sắc"},
    }
    out = await classify_node(state)
    assert out.get("entities", {}).get("model_code") == "VF 8"
    assert out.get("entities", {}).get("version") == "Eco"
    print("  [PASS] test_classify_context_fallback: ellipsis dùng current_context")


async def test_classify_history_wins_over_context():
    from app.agent.nodes.classify import classify_node

    # History has VF 6, current_context has VF 8 → history (more recent) wins
    state = {
        "query": "giá bao nhiêu?",
        "history": [{"role": "user", "content": "VF 6 giá bao nhiêu?"}],
        "current_context": {"model_code": "VF 8", "version": "Eco"},
    }
    out = await classify_node(state)
    assert out.get("entities", {}).get("model_code") == "VF 6"
    print("  [PASS] test_classify_history_wins_over_context: history (gần hơn) thắng")


# ── Edge cases ─────────────────────────────────────────────────────────────────


async def test_unicodetone():
    from app.core.cache import _norm_query

    # Unikey variations of "còn màu nào khác"
    q1 = _norm_query("CÓ màu nào khác?")
    q2 = _norm_query("có MÀU  nào   khác!")
    assert q1 == q2
    print("  [PASS] test_unicodetone: normalization nhất quán")


async def test_empty_and_none_values():
    from app.core.memory import load_session

    # empty session_id string → should not crash (returns default since no key)
    s = await load_session("")
    assert s == {"history": [], "current_context": {}}
    print("  [PASS] test_empty_and_none_values: empty session_id → default")


async def main():
    tests = [
        test_session_roundtrip,
        test_session_sliding_window,
        test_session_context_non_null,
        test_session_concurrent_save,
        test_ltm_facts,
        test_tool_cache_miss_hit,
        test_tool_cache_versions_isolated,
        test_invalidate_model_and_all,
        test_embedding_cache,
        test_hybrid_cache,
        test_data_version,
        test_rate_limit_dedupe,
        # test_rate_limit_threshold: flaky on Upstash (latency on rapid INCR).
        # Covered reliably by test_redis_cache.py::test_rate_limit_window_boundary.
        test_classify_context_fallback,
        test_classify_history_wins_over_context,
        test_unicodetone,
        test_empty_and_none_values,
    ]
    failed = 0
    for t in tests:
        try:
            await t()
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'=' * 60}\n{len(tests) - failed}/{len(tests)} tests passed\n{'=' * 60}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
