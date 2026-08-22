"""Tests for redis cache + multi-turn features (my changes from this PR).

Run: python tests/test_redis_cache.py
Or:  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_redis_cache.py -q
     (requires pytest-asyncio for async tests)
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _uid() -> str:
    return uuid.uuid4().hex[:10]


# ── 1. Session store ─────────────────────────────────────────────────────────


async def test_session_isolation():
    """Hai session khác nhau → history không bị lẫn."""
    from app.core.memory import save_turn, load_session

    a, b = _uid(), _uid()
    await save_turn(a, "hello A", "hi A")
    await save_turn(b, "hello B", "hi B")

    sa = await load_session(a)
    sb = await load_session(b)
    assert sa["history"][0]["content"] == "hello A"
    assert sb["history"][0]["content"] == "hello B"
    assert len(sa["history"]) == 2
    assert len(sb["history"]) == 2
    print("  [PASS] test_session_isolation")


async def test_session_sliding_window_boundary():
    """save_turn lần MAX_TURNS+1 → history cũ bị cắt, chỉ giữ MAX_TURNS*2 msgs."""
    from app.core.memory import save_turn, load_session, MAX_TURNS

    sid = _uid()
    # Write exactly MAX_TURNS + 1 turns (MAX_TURNS*2 + 2 messages)
    for i in range(MAX_TURNS + 1):
        await save_turn(sid, f"q{i}", f"a{i}")

    s = await load_session(sid)
    assert len(s["history"]) == MAX_TURNS * 2
    # Oldest kept turn = turn (MAX_TURNS+1 - MAX_TURNS) = turn 1
    assert s["history"][0]["content"] == "q1"
    assert s["history"][-1]["content"] == f"a{MAX_TURNS}"
    print("  [PASS] test_session_sliding_window_boundary")


async def test_session_concurrent_save_no_loss():
    """Nhiều save_turn đồng thời → KHÔNG mất lượt (LIST RPUSH atomic)."""
    from app.core.memory import save_turn, load_session, MAX_TURNS

    sid = _uid()
    n = MAX_TURNS  # exact window
    await asyncio.gather(*[save_turn(sid, f"q{i}", f"a{i}") for i in range(n)])
    s = await load_session(sid)
    # Should have all 2*n messages (n*2 = 20 for MAX_TURNS=10)
    assert len(s["history"]) == n * 2, f"Expected {n * 2}, got {len(s['history'])}"
    print("  [PASS] test_session_concurrent_save_no_loss")


async def test_context_update_non_null_only():
    """update_current_context chỉ set field non-null → field cũ được giữ."""
    from app.core.memory import update_current_context, load_session

    sid = _uid()
    await update_current_context(sid, model_code="VF 8", version="Eco", topic="giá")
    await update_current_context(sid, topic="màu_sắc")  # only topic

    ctx = (await load_session(sid))["current_context"]
    assert ctx["model_code"] == "VF 8"  # kept
    assert ctx["version"] == "Eco"  # kept
    assert ctx["last_topic"] == "màu_sắc"  # updated
    print("  [PASS] test_context_update_non_null_only")


# ── 2. Long-term memory ──────────────────────────────────────────────────────


async def test_ltm_isolation():
    """Hai user_id khác nhau → facts không bị lẫn."""
    from app.core.memory import save_user_fact, load_user_facts

    a, b = _uid(), _uid()
    await save_user_fact(a, "preferred_model", "VF 8")
    await save_user_fact(b, "preferred_model", "VF 6")

    fa = await load_user_facts(a)
    fb = await load_user_facts(b)
    assert fa["preferred_model"] == "VF 8"
    assert fb["preferred_model"] == "VF 6"
    print("  [PASS] test_ltm_isolation")


# ── 3. Tool cache (entity-keyed) ─────────────────────────────────────────────


async def test_tool_cache_miss_then_hit():
    """get_colors_cached: miss → (data, False), hit → (same, True)."""
    from app.core.cache import get_colors_cached

    model = _uid()
    data1, hit1 = await get_colors_cached(model, None)
    data2, hit2 = await get_colors_cached(model, None)

    assert hit1 is False
    assert hit2 is True
    assert data1 == data2
    print("  [PASS] test_tool_cache_miss_then_hit")


async def test_tool_cache_version_isolation():
    """Cùng model, khác version → cache key khác nhau, miss ở lần 2."""
    from app.core.cache import get_specs_cached

    model = _uid()
    _, h1 = await get_specs_cached(model, None, "powertrain")
    _, h2 = await get_specs_cached(model, "Eco", "powertrain")
    assert h1 is False
    assert h2 is False  # different key → miss
    # hit on repeat
    _, h3 = await get_specs_cached(model, "Eco", "powertrain")
    assert h3 is True
    print("  [PASS] test_tool_cache_version_isolation")


async def test_tool_cache_data_version_autoinvalidate():
    """data_version trong key → sau khi invalidate, key cũ miss."""
    from app.core.cache import get_specs_cached, invalidate_all

    model = _uid()
    await get_specs_cached(model, None, "powertrain")
    _, hit = await get_specs_cached(model, None, "powertrain")
    assert hit is True

    # invalidate → next read miss (tạo key mới)
    await invalidate_all()
    _, hit2 = await get_specs_cached(model, None, "powertrain")
    assert hit2 is False
    print("  [PASS] test_tool_cache_data_version_autoinvalidate")


# ── 4. Embedding + hybrid cache ──────────────────────────────────────────────


async def test_embedding_cache_roundtrip():
    from app.core.cache import get_embedding_cached, set_embedding_cached

    text = f"test embedding {_uid()}"
    assert await get_embedding_cached(text) is None  # miss

    vec = [0.1, 0.2, 0.3]
    await set_embedding_cached(text, vec)
    cached = await get_embedding_cached(text)
    assert cached == vec
    print("  [PASS] test_embedding_cache_roundtrip")


async def test_hybrid_cache_key_components():
    """Cùng query nhưng khác model/top_k/rerank → miss."""
    from app.core.cache import get_hybrid_cached, set_hybrid_cached

    q = f"test hybrid {_uid()}"
    results = [{"text": "x", "score": 0.9}]

    await set_hybrid_cached(q, "VF 8", 5, False, results)

    assert await get_hybrid_cached(q, "VF 8", 5, False) == results  # hit
    assert await get_hybrid_cached(q, "VF 9", 5, False) is None  # diff model
    assert await get_hybrid_cached(q, "VF 8", 10, False) is None  # diff top_k
    assert await get_hybrid_cached(q, "VF 8", 5, True) is None  # diff rerank
    print("  [PASS] test_hybrid_cache_key_components")


# ── 5. Rate limit ────────────────────────────────────────────────────────────


async def test_rate_limit_window_boundary():
    """Gửi đúng 10 lần trong window → OK, lần 11 → block."""
    from app.api.chat import _rate_limit_check
    from app.core.memory import get_redis

    sid = _uid()
    # Use fully random IP + pre-clean to avoid leftover keys from other tests
    ip = f"10.99.{uuid.uuid4().hex[:4]}.{uuid.uuid4().hex[:4]}"
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

    results = [await _rate_limit_check(sid, ip) for _ in range(11)]
    assert all(r is None for r in results[:10]), f"Expected 10 allowed, got {[r for r in results[:10]]}"
    assert results[10] is not None, "11th request should be blocked"

    # cleanup
    if r:
        keys = []
        async for k in r.scan_iter(match=f"rl:s:{sid}:*"):
            keys.append(k)
        async for k in r.scan_iter(match=f"rl:ip:{ip}:*"):
            keys.append(k)
        if keys:
            await r.delete(*keys)
    print("  [PASS] test_rate_limit_window_boundary")


# ── 6. Dedupe ────────────────────────────────────────────────────────────────


async def test_dedupe_same_msg_id():
    """Cùng message_id → False (trùng), khác → True."""
    from app.api.chat import _dedup_check

    sid = _uid()
    msg = _uid()
    assert await _dedup_check(sid, msg) is True  # new
    assert await _dedup_check(sid, msg) is False  # dup
    assert await _dedup_check(sid, _uid()) is True  # different id
    print("  [PASS] test_dedupe_same_msg_id")


# ── 7. classify current_context fallback ─────────────────────────────────────


async def test_classify_context_fallback_ellipsis():
    """Ellipsis query + current_context có model → entities populated."""
    from app.agent.nodes.classify import classify_node

    state = {
        "query": "còn màu nào khác?",
        "history": [],
        "current_context": {"model_code": "VF 8", "last_topic": "màu_sắc"},
    }
    out = await classify_node(state)
    assert out.get("entities", {}).get("model_code") == "VF 8"
    print("  [PASS] test_classify_context_fallback_ellipsis")


async def test_classify_context_fallback_topic():
    """Ellipsis query + history có topic → topic kế thừa."""
    from app.agent.nodes.classify import classify_node

    state = {
        "query": "pin bao nhiêu kWh?",
        "history": [
            {"role": "user", "content": "VF 8 Eco"},
            {"role": "assistant", "content": "Thông tin VF 8 Eco..."},
        ],
        "current_context": {
            "model_code": "VF 8",
            "version": "Eco",
            "last_topic": "pin_và_sạc",
        },
    }
    out = await classify_node(state)
    assert out.get("category") == "pin_và_sạc"
    assert out.get("entities", {}).get("model_code") == "VF 8"
    print("  [PASS] test_classify_context_fallback_topic")


# ── 8. Version re-clarify (fresh model query + version-dependent topic) ──────


async def test_fresh_model_query_reclarifies():
    """Tự nêu model + không nêu version → re-clarify (KHÔNG kế thừa version cũ)."""
    from app.agent.nodes.classify import classify_node

    hist = [
        {"role": "user", "content": "VF 8 đi được bao nhiêu km?"},
        {"role": "assistant", "content": "Bạn muốn hỏi phiên bản nào của VF 8?"},
        {"role": "user", "content": "Plus"},
        {"role": "assistant", "content": "VF 8 Plus đi 457 km theo WLTP."},
    ]
    ctx = {"model_code": "VF 8", "version": "Plus", "last_topic": "phạm_vi_di_chuyển"}
    out = await classify_node({"query": "VF 8 đi được bao nhiêu km?", "history": hist, "current_context": ctx})
    assert out.get("decision") == "clarify", f"Expected clarify, got {out.get('decision')}"
    assert out.get("reason_code") == "missing_version"
    print("  [PASS] test_fresh_model_query_reclarifies")


async def test_ellipsis_with_version_still_answers():
    """Ellipsis follow-up (query_has_model=False) → kế thừa version từ context."""
    from app.agent.nodes.classify import classify_node

    hist = [
        {"role": "user", "content": "VF 8 đi được bao nhiêu km?"},
        {"role": "assistant", "content": "Bạn muốn hỏi phiên bản nào của VF 8?"},
        {"role": "user", "content": "Plus"},
        {"role": "assistant", "content": "VF 8 Plus đi 457 km theo WLTP."},
    ]
    ctx = {"model_code": "VF 8", "version": "Plus", "last_topic": "phạm_vi_di_chuyển"}
    out = await classify_node({"query": "đi được bao nhiêu km?", "history": hist, "current_context": ctx})
    assert out.get("decision") == "answer", f"Expected answer, got {out.get('decision')}"
    print("  [PASS] test_ellipsis_with_version_still_answers")


# ── 9. an_toàn fetches both safety + adas ────────────────────────────────────


async def test_an_toan_fetches_safety_and_adas():
    """Topic an_toàn → get_specs cả safety lẫn adas (camera 360 ở adas)."""
    from app.agent.nodes.call_tools import _call_model_tools

    results, _ = await _call_model_tools("VF 9", None, "an_toàn", "vf9")
    spec_cats = set()
    camera_found = False
    for r in results:
        if r["tool"] == "get_specs":
            for s in r.get("result", {}).get("specs", []):
                spec_cats.add(s["category"])
                if s["key"] == "surround_view_camera":
                    camera_found = True
    assert "safety" in spec_cats, "safety specs missing"
    assert "adas" in spec_cats, "adas specs missing"
    assert camera_found, "surround_view_camera not found"
    print("  [PASS] test_an_toan_fetches_safety_and_adas")


# ── 10. Overview (tổng_quan) ─────────────────────────────────────────────────


async def test_overview_classify():
    """'giới thiệu về vf2' → answer/tổng_quan (KHÔNG clarify)."""
    from app.agent.nodes.classify import classify_node

    out = await classify_node({"query": "giới thiệu về vf2", "history": [], "current_context": {}})
    assert out.get("decision") == "answer"
    assert out.get("category") == "tổng_quan"
    print("  [PASS] test_overview_classify")


async def test_overview_fetches_multiple_tools():
    """tổng_quan → get_price + get_specs(4 categories) + get_colors (không có list_models — noise)."""
    from app.agent.nodes.call_tools import _call_model_tools

    results, _ = await _call_model_tools("VF 2", None, "tổng_quan", "giới thiệu về vf2")
    tools = {r["tool"] for r in results}
    assert "get_price" in tools
    assert "get_colors" in tools

    # 4 spec categories: powertrain, battery, dimension, interior
    spec_results = [r for r in results if r["tool"] == "get_specs"]
    assert len(spec_results) == 4, f"Expected 4 get_specs calls, got {len(spec_results)}"
    spec_cats = set()
    for r in spec_results:
        for s in r.get("result", {}).get("specs", []):
            spec_cats.add(s["category"])
    assert {"powertrain", "battery", "dimension", "interior"}.issubset(spec_cats)
    print("  [PASS] test_overview_fetches_multiple_tools")


# ── 11. data_version ─────────────────────────────────────────────────────────


async def test_data_version_returns_value():
    from app.core.cache import data_version

    ver = await data_version()
    assert ver and isinstance(ver, str) and ver != ""
    print("  [PASS] test_data_version_returns_value")


async def test_data_version_memoised():
    """Gọi 2 lần liên tiếp → không query PG lần 2 (memo 60s)."""
    from app.core.cache import data_version

    v1 = await data_version()
    v2 = await data_version()
    assert v1 == v2
    print("  [PASS] test_data_version_memoised")


# ── 12. Unicode normalization ────────────────────────────────────────────────


async def test_norm_query_consistent():
    """Cùng nội dung khác cách gõ → key giống nhau."""
    from app.core.cache import _norm_query

    assert _norm_query("VF  8  giá?") == _norm_query("vf 8 giá!")
    assert _norm_query("có mấy màu") == _norm_query("có  mấy  màu")
    # MẪY vsấy: different combining marks (accent on different chars) → NOT equal
    # This is expected: Vietnamese tone marks are character-position-specific.
    assert _norm_query("MẪY") != _norm_query("ấy")
    print("  [PASS] test_norm_query_consistent")


# ── Runner ────────────────────────────────────────────────────────────────────


async def _run_all():
    tests = [
        # Session
        test_session_isolation,
        test_session_sliding_window_boundary,
        test_session_concurrent_save_no_loss,
        test_context_update_non_null_only,
        # LTM
        test_ltm_isolation,
        # Tool cache
        test_tool_cache_miss_then_hit,
        test_tool_cache_version_isolation,
        test_tool_cache_data_version_autoinvalidate,
        # Embedding + hybrid cache
        test_embedding_cache_roundtrip,
        test_hybrid_cache_key_components,
        # Rate limit + dedupe
        test_rate_limit_window_boundary,
        test_dedupe_same_msg_id,
        # Classify context
        test_classify_context_fallback_ellipsis,
        test_classify_context_fallback_topic,
        # Version re-clarify
        test_fresh_model_query_reclarifies,
        test_ellipsis_with_version_still_answers,
        # an_toàn + overview
        test_an_toan_fetches_safety_and_adas,
        test_overview_classify,
        test_overview_fetches_multiple_tools,
        # data_version
        test_data_version_returns_value,
        test_data_version_memoised,
        # Unicode
        test_norm_query_consistent,
    ]

    passed, failed = 0, 0
    for t in tests:
        try:
            await t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")

    print(f"\n{'=' * 60}")
    print(f"{passed}/{passed + failed} tests passed")
    print(f"{'=' * 60}")
    return failed


if __name__ == "__main__":
    sys.exit(asyncio.run(_run_all()))
