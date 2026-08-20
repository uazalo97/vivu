import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.nodes.classify import classify_node  # noqa: E402
from app.agent.nodes.call_tools import _call_model_tools  # noqa: E402


async def main():
    # Step 1: classify follow-up "vf9" after "xe này có camera 360 không?" clarify
    history = [
        {"role": "user", "content": "xe này có camera 360 không?"},
        {"role": "assistant", "content": "Bạn muốn hỏi về xe nào?"},
    ]
    out = await classify_node({"query": "vf9", "history": history, "current_context": {}})
    category = out.get("category")
    entities = out.get("entities", {})
    model_code = entities.get("model_code")
    version = entities.get("version")
    print(f"classify 'vf9' → category={category}, model={model_code}, version={version}")
    assert category == "an_toàn", f"expected an_toàn, got {category}"
    print()

    # Step 2: call_tools — now fetches BOTH safety + adas for an_toàn
    results, cache_hits = await _call_model_tools(model_code, version, category, "vf9")
    print(f"tool results: {len(results)} entries")
    camera_found = False
    for r in results:
        tool = r.get("tool")
        success = r.get("success")  # noqa: F841
        specs = r.get("result", {}).get("specs", [])
        cats = set(s["category"] for s in specs) if specs else set()
        keys = [s["key"] for s in specs if "camera" in s["key"].lower() or "surround" in s["key"].lower()]
        if keys:
            camera_found = True
            for s in specs:
                if s["key"] in keys:
                    print(f"  ✅ {tool} [{s['category']}] {s['version_name']:14} {s['key']:24} = {s['value']}")
        if cats:
            print(f"  {tool} categories: {sorted(cats)}, camera keys: {keys}")
    print()
    assert camera_found, "FAIL: camera 360 specs not found in any tool result"
    print("PASS: an_toàn now fetches BOTH safety + adas → camera 360 data surfaced")


asyncio.run(main())
