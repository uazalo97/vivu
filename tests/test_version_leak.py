import asyncio
import sys

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

sys.path.insert(0, ".")

from app.agent.nodes.classify import classify_node  # noqa: E402


async def run(q, history, ctx):
    out = await classify_node({"query": q, "history": history, "current_context": ctx})
    return out.get("decision"), out.get("reason_code"), out.get("entities"), out.get("response_text")


async def main():
    ctx = {"model_code": "VF 8", "version": "Plus", "last_topic": "phạm_vi_di_chuyển"}
    full_hist = [
        {"role": "user", "content": "VF 8 đi được bao nhiêu km?"},
        {"role": "assistant", "content": "Bạn muốn hỏi phiên bản nào của VF 8?"},
        {"role": "user", "content": "Plus"},
        {"role": "assistant", "content": "VF 8 Plus đi 457 km theo WLTP."},
    ]

    print("=== Case người dùng báo bug ===")
    d, r, e, resp = await run("VF 8 đi được bao nhiêu km?", full_hist, ctx)
    print(f"  'VF 8 đi được bao nhiêu km?' -> decision={d}, reason={r}, entities={e}")
    print(f"  response: {resp!r}")
    assert d == "clarify" and r == "missing_version", "FAIL: phải clarify lại phiên bản"

    print("\n=== Control: follow-up ellipsis vẫn phải kế thừa version ===")
    d, r, e, resp = await run("đi được bao nhiêu km?", full_hist, ctx)
    print(f"  'đi được bao nhiêu km?' -> decision={d}, reason={r}, entities={e}")
    assert d == "answer", "FAIL: ellipsis follow-up phải answer (kế thừa VF 8 Plus)"

    print("\n=== Control: query có version rõ ràng → không clarify ===")
    d, r, e, resp = await run("VF 8 Plus đi được bao nhiêu km?", full_hist, ctx)
    print(f"  'VF 8 Plus đi được bao nhiêu km?' -> decision={d}, reason={r}")
    assert d == "answer", "FAIL: có version thì phải answer"

    print("\n=== Control: turn đầu tiên (không history) vẫn clarify ===")
    d, r, e, resp = await run("VF 8 đi được bao nhiêu km?", [], {})
    print(f"  'VF 8 đi được bao nhiêu km?' (fresh) -> decision={d}, reason={r}")
    assert d == "clarify", "FAIL: turn đầu phải clarify"

    print("\n=== Control: 'Plus' trả lời phiên bản vẫn answer ===")
    d, r, e, resp = await run("Plus", full_hist, ctx)
    print(f"  'Plus' -> decision={d}, entities={e}")
    assert d == "answer", "FAIL: trả lời version phải answer"

    print("\nALL VERSION-LEAK CHECKS PASSED")


asyncio.run(main())
