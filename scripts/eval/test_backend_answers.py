import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(Path(".env"))

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.agent.agent_loop import AgentLoop  # noqa: E402


async def run_tests():
    agent = AgentLoop()
    test_queries = [
        "VF 3 thông số kỹ thuật?",
        "Xe nào có cửa sổ trời",
        "VF 6 có mấy chỗ ngồi?",
        "Chính sách bảo hành pin xe điện VinFast được bao nhiêu năm?",
    ]

    print("=" * 80)
    print("BACKEND AGENT EVALUATION AFTER FIXING CLARIFY & NULL-SAFETY")
    print("=" * 80)

    for idx, query in enumerate(test_queries, 1):
        print(f"\n[{idx}] USER QUERY: {query}")
        print("-" * 80)

        t0 = asyncio.get_event_loop().time()
        result = await agent.run(query=query, history=[])
        dt = asyncio.get_event_loop().time() - t0

        response_text = result.response if hasattr(result, "response") else str(result)
        sources = getattr(result, "sources", [])
        decision = getattr(result, "decision", "answer")

        print(f"⏱️ Response Time: {dt:.2f}s | Decision: {decision}")
        print("\n🤖 AGENT RESPONSE:")
        print(response_text)
        print("\n🔗 SOURCES / CITATIONS RETURNED:")
        if sources:
            for s in sources:
                if isinstance(s, dict):
                    title = s.get("title") or s.get("text_type") or "Tài liệu"
                    url = s.get("source_url") or s.get("url") or s.get("source_file") or "N/A"
                    print(f"  • [{title}]: {url}")
                else:
                    print(f"  • {s}")
        else:
            print("  (No direct sources array)")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_tests())
