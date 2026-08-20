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


async def main():
    cases = [
        "giới thiệu về vf2",
        "cho tôi biết về vf2",
        "Giới thiệu VF 8 All New",
        "thông tin về vf 5",
        "vf2 là gì",  # not broad — may be clarify or answer
        "VF 2 có mấy màu",  # specific topic → answer colors (control)
        "tổng quan về vf 3",  # broad
    ]
    for q in cases:
        out = await classify_node({"query": q, "history": [], "current_context": {}})
        rel = out.get("response_text", "")
        print(
            f"{q!r:28} -> decision={out.get('decision'):8} category={out.get('category'):12} entities={out.get('entities')} resp={rel!r}"
        )


asyncio.run(main())
