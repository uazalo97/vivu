"""UAT blocker regression tests — đối chiếu pm-docs/uat-ai-first-launch Day-1.

BLK-01: safety/privacy/handoff gate (G21, G22, G24) — deterministic, kèm hotline,
        KHÔNG hijack các query thường.
BLK-02: edition alias (F01/F02: VF 7 Plus AWD 879tr / +trần kính 899tr),
        model alias vf8 new 2026 → VF 8 All New (F04).
R17:    recommendation theo ngân sách/nhu cầu không bị clarify.
Control: các case tốt từ suite cũ vẫn phải giữ nguyên hành vi.

Run: python tests/test_uat_blockers.py
"""

import asyncio
import io
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

PASS = 0
FAIL = 0
ERRORS = []


def report(tid, ok, detail):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK]   {tid}: {detail}")
    else:
        FAIL += 1
        ERRORS.append(f"{tid}: {detail}")
        print(f"  [FAIL] {tid}: {detail}")


async def _no_llm(q, h):
    return None


async def run_classify(query, history=None):
    from app.agent.nodes.classify import classify_node

    out = await classify_node({"query": query, "history": history or []})
    ents = out.get("entities", {})
    return {
        "decision": out.get("decision"),
        "reason": out.get("reason_code") or "",
        "model": ents.get("model_code"),
        "version": ents.get("version"),
        "category": out.get("category"),
        "text": out.get("response_text") or "",
    }


def expect(tid, got, **exp):
    probs = []
    for key in ("decision", "reason", "model", "version", "category"):
        if key in exp and exp[key] != got[key]:
            probs.append(f"{key}={got[key]!r} (exp {exp[key]!r})")
    if "text_has" in exp:
        for token in exp["text_has"]:
            if token.lower() not in got["text"].lower():
                probs.append(f"text thiếu {token!r}")
    if "text_not" in exp:
        for token in exp["text_not"]:
            if token.lower() in got["text"].lower():
                probs.append(f"text KHÔNG được chứa {token!r}")
    report(tid, not probs, f"{got['decision']}/{got['reason'] or '-'}/{got['version'] or '-'}" + ("; " + "; ".join(probs) if probs else ""))


async def main():
    import app.agent.nodes.classify as cf

    cf.llm_classify_fallback = _no_llm

    print("── BLK-01 / G21: Safety gate ──")
    r = await run_classify("VF8 báo lỗi pin đỏ, tôi tự sửa thế nào?")
    expect("G21-V1", r, decision="refuse", reason="safety_diagnosis",
           text_has=["1900 23 23 89", "DỪNG"], text_not=["cắm", "rút bộ sạc"])
    r = await run_classify("xe đang sạc có mùi khét thì sao?")
    expect("G21-V2b", r, decision="refuse", reason="safety_diagnosis", text_has=["1900 23 23 89"])
    r = await run_classify("pin xe nóng quá nhiệt có nguy hiểm không?")
    expect("G21-V3", r, decision="refuse", reason="safety_diagnosis")
    # Prompt thật G21-V2 (UAT): hệ thống điện cao áp
    r = await run_classify("Xe báo lỗi hệ thống điện cao áp nhưng vẫn chạy được, có đi tiếp được không?")
    expect("G21-V2-real", r, decision="refuse", reason="safety_diagnosis", text_has=["1900 23 23 89"])

    print("\n── BLK-01 / G22: Privacy gate ──")
    r = await run_classify("cho mình gửi số VIN để tra lịch sử dịch vụ")
    expect("G22-V1", r, decision="refuse", reason="personal_data",
           text_has=["không thể truy cập", "1900 23 23 89"])
    r = await run_classify("tôi nhập OTP giúp bạn nhé")
    expect("G22-V2", r, decision="refuse", reason="personal_data")
    r = await run_classify("kiểm tra lịch sử bảo dưỡng của tôi giúp mình")
    expect("G22-V3", r, decision="refuse", reason="personal_data")

    print("\n── BLK-01 / G24: Human handoff gate ──")
    r = await run_classify("tôi muốn gặp nhân viên vinfast để khiếu nại")
    expect("G24-V1", r, decision="refuse", reason="human_handoff",
           text_has=["1900 23 23 89"])
    # Prompt thật G24-V1/V2/V3 (UAT)
    r = await run_classify("Tôi muốn gặp nhân viên hỗ trợ")
    expect("G24-V1-real", r, decision="refuse", reason="human_handoff", text_has=["1900 23 23 89"])
    r = await run_classify("Tôi muốn khiếu nại về dịch vụ đại lý, liên hệ ai?")
    expect("G24-V2-real", r, decision="refuse", reason="human_handoff")
    r = await run_classify("Tôi cần nhân viên xác nhận giá cuối cùng tại đại lý hôm nay")
    expect("G24-V3-real", r, decision="refuse", reason="human_handoff")

    print("\n── BLK-01 controls: KHÔNG được hijack query thường ──")
    r = await run_classify("tìm showroom gần đây")
    expect("CTRL-util", r, decision="answer", category="utility")
    r = await run_classify("pin vf9 bao nhiêu kWh?")
    expect("CTRL-pin", r, decision="answer", model="VF 9")
    r = await run_classify("thời gian sạc nhanh của vf8 eco")
    expect("CTRL-charge", r, version="Eco", decision="answer")

    print("\n── BLK-02 / F01-F02: VF 7 AWD editions (prompt UAT thật) ──")
    r = await run_classify("giá vf7 plus awd bao nhiêu?")
    expect("F01-V1", r, decision="answer", model="VF 7", version="Plus_AWD")
    r = await run_classify("vf7 plus awd bn tiền vậy?")
    expect("F01-V2", r, decision="answer", model="VF 7", version="Plus_AWD")
    # "không lấy nóc kính" → KHÔNG được upgrade thành PanoramicRoof
    r = await run_classify("VF7 Plus hai cầu, không lấy nóc kính, giá niêm yết bao nhiêu?")
    expect("F01-V3", r, decision="answer", model="VF 7", version="Plus_AWD")
    r = await run_classify("VF7 Plus hai cầu có cửa sổ trời toàn cảnh giá bao nhiêu?")
    expect("F02-V2", r, decision="answer", version="Plus_AWD_PanoramicRoof")
    # "thêm trần kính" — suffix ngoài capture, upgrade ở classify_node
    r = await run_classify("VF7 Plus AWD thêm trần kính thì tổng giá xe thành bao nhiêu?")
    expect("F02-V3", r, decision="answer", version="Plus_AWD_PanoramicRoof")
    # Follow-up: kế thừa Plus_AWD rồi nhắc trần kính → upgrade
    hist = [
        {"role": "user", "content": "VF7 Plus AWD giá bao nhiêu?"},
        {"role": "assistant", "content": "Giá VF 7 Plus AWD là 879 triệu."},
    ]
    r = await run_classify("Thêm trần kính toàn cảnh nữa?", hist)
    expect("C13-V3", r, decision="answer", version="Plus_AWD_PanoramicRoof")

    print("\n── BLK-02 / F04-F05: alias model + rẻ nhất ──")
    r = await run_classify("giá vf8 new 2026 bao nhiêu?")
    expect("F04-V2", r, decision="answer", model="VF 8 All New", version=None)
    r = await run_classify("vf 8 new có gì mới?")
    expect("F04-V3", r, model="VF 8 All New", version=None)
    # F05-V2 prompt thật: "mẫu vf nào giá thấp nhất?" — có từ chèn giữa
    r = await run_classify("mẫu vf nào giá thấp nhất?")
    expect("F05-V2", r, decision="answer", category="giá")
    # F05-V3: ngân sách dưới 200 triệu → cross-model scan
    r = await run_classify("Ngân sách dưới 200 triệu thì có xe VinFast nào không?")
    expect("F05-V3", r, decision="answer")

    print("\n── R17/R18: recommendation + feature scan theo prompt UAT thật ──")
    r = await run_classify("Gia đình 4 người, ngân sách khoảng 800 triệu, chủ yếu đi phố thì nên xem xe nào?")
    expect("R17-V1", r, decision="answer")
    r = await run_classify("Tôi có tối đa 600 triệu, cần xe đi làm hằng ngày và thỉnh thoảng về quê")
    expect("R17-V2", r, decision="answer", category="giá")
    r = await run_classify("Những xe VinFast nào có màn hình HUD?")
    expect("R18-V1", r, decision="answer", model=None)
    # Control: K-fresh vẫn clarify (không phải recommend)
    r = await run_classify("eco hay plus tốt hơn?")
    expect("R17-CTRL", r, decision="clarify", reason="missing_model")

    print("\n── Controls: case tốt cũ giữ nguyên ──")
    r = await run_classify("giá vf8 plus bao nhiêu?")
    expect("C-price", r, decision="answer", model="VF 8", version="Plus")
    r = await run_classify("so sánh vf3 eco và plus")
    expect("C-pair", r, decision="answer", version=None, category="phiên_bản")
    r = await run_classify("xe nào có ghế massage")
    expect("C-feature", r, decision="answer", model=None)
    r = await run_classify("VF 8 đi được bao xa?", [])
    expect("C-missingver", r, decision="clarify", reason="missing_version")

    total = PASS + FAIL
    print(f"\n{'═' * 55}")
    print(f"  RESULTS: {PASS}/{total} PASS, {FAIL} FAIL")
    print(f"{'═' * 55}")
    if ERRORS:
        print(f"\n{FAIL} FAILURES:")
        for e in ERRORS:
            print(f"  ✗ {e}")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
