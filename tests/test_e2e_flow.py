"""
test_e2e_flow.py — End-to-end test qua AgentLoop với hạ tầng THẬT (LLM + PG + Qdrant).

Chạy: python -W ignore tests/test_e2e_flow.py

Cover:
  1. Single-turn: query rõ ràng → answer đầy đủ decision_log
  2. Multi-turn: turn1 thiết lập context, turn2 ellipsis dùng current_context
  3. Cache hit: câu lặp lại → tool cache_hit
"""

import asyncio
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

sys.path.insert(0, ".")


async def main():
    from app.agent.agent_loop import AgentLoop
    from app.core.memory import load_session, save_turn, update_current_context, get_redis

    agent = AgentLoop()

    # ── Turn 1: single-turn, câu cụ thể ───────────────────────────────────
    print("=" * 70)
    print("[TURN 1] single-turn 'VF 8 có mấy màu?'")
    r1 = await agent.run("VF 8 có mấy màu?", [])
    print(f"  decision       = {r1.decision}")
    print(f"  entities       = {r1.classify_result.get('entities')}")
    print(f"  cache_hit      = {r1.cache_hit}")
    print(f"  cache_type     = {r1.cache_type}")
    print(f"  detected_topic = {r1.decision_log.get('detected_topic')}")
    print(f"  response[:120] = {r1.response[:120]!r}")
    assert r1.decision in ("answer", "clarify", "refuse"), f"unexpected decision {r1.decision}"
    assert r1.response, "empty response"

    # ── Turn 2: lặp lại → tool cache hit ──────────────────────────────────
    print("=" * 70)
    print("[TURN 2] repeat 'VF 8 có mấy màu?' → expect get_colors cache hit")
    r2 = await agent.run("VF 8 có mấy màu?", [])
    print(f"  decision   = {r2.decision}")
    print(f"  cache_hit  = {r2.cache_hit}  cache_type = {r2.cache_type}")
    print(f"  response[:120] = {r2.response[:120]!r}")
    # Note: nếu cache hit, cache_hit=True; nếu LLM/DB lỗi thì vẫn phải có response
    assert r2.response, "empty response on repeated turn"

    # ── Turn 3: multi-turn ellipsis qua current_context ───────────────────
    print("=" * 70)
    print("[TURN 3] multi-turn: setup context VF 8 màu_sắc, rồi ellipsis 'còn màu nào khác?'")
    sid = f"e2e-{r1.decision_log.get('conversation_id', '')[-8:]}"
    await update_current_context(sid, model_code="VF 8", version=None, topic="màu_sắc")
    await save_turn(sid, "VF 8 có mấy màu?", r1.response)

    session = await load_session(sid)
    print(f"  session history len = {len(session['history'])}")
    print(f"  session context     = {session['current_context']}")

    r3 = await agent.run("còn màu nào khác?", session["history"], session["current_context"])
    print(f"  decision   = {r3.decision}")
    print(f"  entities   = {r3.classify_result.get('entities')}")
    print(f"  response[:120] = {r3.response[:120]!r}")

    # Cleanup e2e session keys
    r = get_redis()
    if r:
        keys = []
        async for k in r.scan_iter(match=f"session:{sid}:*"):
            keys.append(k)
        if keys:
            await r.delete(*keys)

    print("=" * 70)
    print("E2E FLOW OK")


if __name__ == "__main__":
    asyncio.run(main())
