"""Edge-case tests: LEAK VERSION + CONTEXT trong multi-turn — các case user bình thường hay hỏi.

Chạy OFFLINE (stub llm_classify_fallback → classify_node chạy thuần rule).
Mỗi conversation mô phỏng flow thật: history build dần từ các turn trước.

Các nhóm case:
  A. Hỏi range → được hỏi version → đổi version trong cùng xe   (version phải theo)
  B. Nói bản cụ thể xe A → chuyển sang xe B                       (version KHÔNG được leak)
  C. Follow-up lười ("pin bao nhiêu?") ngay sau bản cụ thể        (version phải GIỮ)
  D. So sánh 2 xe rồi đổi hẳn sang xe khác                        (comparison stale phải bỏ)
  E. So sánh 2 xe rồi hỏi tiếp "giá bao nhiêu?"                   (follow-up hợp lệ giữ cặp so sánh)
  F. So sánh eco vs plus rồi hỏi "bản nào rẻ hơn?"                (không khoá cứng 1 version)

Run: python tests/test_version_leak.py
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


async def _no_llm(query, history):
    return None


def _install_offline_stub():
    import app.agent.nodes.classify as cf

    cf.llm_classify_fallback = _no_llm


# Mỗi turn: (query, expected) với expected = {decision, reason?, model?, version?, category?}
# version=None nghĩa là PHẢI không có version trong entities (leak check).
CONVERSATIONS = [
    {
        "name": "A. Cùng xe — đổi version tường minh",
        "turns": [
            # User chưa nói bản → bot phải hỏi lại
            ("VF 8 đi được bao xa?", {"decision": "clarify", "reason": "missing_version", "model": "VF 8"}),
            # Trả lời version → answer đúng bản
            ("bản Plus đi bao nhiêu km?", {"decision": "answer", "model": "VF 8", "version": "Plus"}),
            # Đổi sang bản Eco tường minh → version phải cập nhật theo
            ("còn bản Eco thì sao?", {"decision": "answer", "model": "VF 8", "version": "Eco"}),
            # Follow-up lùi lại pin — vẫn đang nói VF 8 Eco
            ("sạc nhanh mất bao lâu?", {"decision": "answer", "model": "VF 8", "version": "Eco"}),
        ],
    },
    {
        "name": "B. Đổi xe sau khi nói bản cụ thể — version KHÔNG leak",
        "turns": [
            ("giá vf8 all new bao nhiêu?", {"decision": "answer", "model": "VF 8 All New"}),
            # Core leak check: VF 3 không có bản All New → version phải rỗng
            ("còn vf3 thì sao?", {"decision": "answer", "model": "VF 3", "version": None}),
            ("bản plus của vf6 giá bao nhiêu?", {"decision": "answer", "model": "VF 6", "version": "Plus"}),
            # VF 9 không có bản PlusCaptain của VF 6 → không leak
            ("thế vf9 có mấy màu?", {"decision": "answer", "model": "VF 9", "version": None}),
        ],
    },
    {
        "name": "C. Follow-up lười cùng xe — version phải GIỮ",
        "turns": [
            ("vf6 plus công suất bao nhiêu?", {"decision": "answer", "model": "VF 6", "version": "Plus"}),
            # "pin bao nhiêu?" = vẫn nói về VF 6 Plus đang bàn
            ("pin bao nhiêu?", {"decision": "answer", "model": "VF 6", "version": "Plus"}),
            # phạm_vi_di_chuyển là version-dependent — đã có Plus từ context nên không hỏi lại
            ("quãng đường thì sao?", {"decision": "answer", "model": "VF 6", "version": "Plus"}),
        ],
    },
    {
        "name": "D. So sánh 2 xe rồi đổi hẳn sang xe khác — comparison stale phải bỏ",
        "turns": [
            ("so sánh vf2 và vf3", {"decision": "answer", "category": "so_sánh"}),
            # User nhảy sang VF 5 → KHÔNG bị kéo vào so sánh VF2/VF3 nữa
            ("cho mình xem vf5 đi", {"decision": "answer", "model": "VF 5", "version": None}),
            ("nội thất nó thế nào?", {"decision": "answer", "model": "VF 5", "category": "nội_thất"}),
        ],
    },
    {
        "name": "E. So sánh xong hỏi tiếp 'giá bao nhiêu?' — follow-up hợp lệ",
        "turns": [
            ("so sánh vf6 và vf8", {"decision": "answer", "category": "so_sánh"}),
            # Vẫn trong context so sánh → trả giá cả 2 xe, KHÔNG hỏi 'xe nào?'
            ("giá bao nhiêu?", {"decision": "answer", "category": "so_sánh"}),
            # Nhắc model mới → thoát comparison, trả về query đơn
            ("vậy vf9 thì sao?", {"decision": "answer", "model": "VF 9", "version": None}),
        ],
    },
    {
        "name": "F. So sánh eco vs plus rồi hỏi 'bản nào rẻ hơn?' — không khoá 1 version",
        "turns": [
            # Version-pair: entities.version phải bị clear để lấy cả 2 bản
            ("so sánh vf3 eco và plus", {"decision": "answer", "model": "VF 3", "version": None, "category": "phiên_bản"}),
            # 'bản nào' là câu hỏi về versions → không kế thừa Eco từ turn trước
            ("bản nào rẻ hơn?", {"decision": "answer", "model": "VF 3", "version": None}),
        ],
    },
    {
        "name": "H. Utility xen giữa — context model/version phải giữ",
        "turns": [
            ("giá vf8 plus bao nhiêu?", {"decision": "answer", "model": "VF 8", "version": "Plus"}),
            # Showroom là utility — không dùng model nhưng không được phá context
            ("tìm showroom gần đây", {"decision": "answer", "reason": "utility"}),
            # Quay lại xe đang bàn → vẫn là VF 8 Plus
            ("pin nó thế nào?", {"decision": "answer", "model": "VF 8", "version": "Plus"}),
        ],
    },
    {
        "name": "I. Greeting xen giữa follow-up clarify",
        "turns": [
            ("thông số vf6 eco", {"decision": "answer", "model": "VF 6", "version": "Eco"}),
            ("chào bạn", {"decision": "greeting"}),
            # Sau greeting vẫn nhớ đang nói VF 6 → 'plus' = bản Plus của VF 6
            ("plus", {"decision": "answer", "model": "VF 6", "version": "Plus"}),
        ],
    },
    {
        "name": "K. 'eco hay plus tốt hơn?' — fresh clarify, có context thì trả lời",
        "turns": [
            # Fresh: chưa biết xe nào → phải hỏi
            ("eco hay plus tốt hơn?", {"decision": "clarify", "reason": "missing_model"}),
            ("giá vf3 bao nhiêu", {"decision": "answer", "model": "VF 3"}),
            # Có context VF3 → so sánh 2 bản của VF 3 luôn
            ("eco hay plus tốt hơn?", {"decision": "answer", "model": "VF 3", "version": None}),
        ],
    },
    {
        "name": "M. Cross-feature scan rồi follow-up feature — tiếp tục scan KHÔNG clarify",
        "turns": [
            ("xe nào có cửa sổ trời", {"decision": "answer", "model": None, "category": "nội_thất"}),
            # Follow-up feature khác → vẫn quét tất cả xe, không hỏi lại 'xe nào?'
            ("còn ghế massage thì sao?", {"decision": "answer", "model": None, "category": "nội_thất"}),
            # Topic khác map ('trần kính' → option) nhưng vẫn là follow-up scan
            ("còn trần kính thì sao?", {"decision": "answer", "model": None}),
        ],
    },
    {
        "name": "O. 'bản plus thì sao?' ngay sau model không nhắc bản",
        "turns": [
            ("vf8 giá bao nhiêu", {"decision": "answer", "model": "VF 8", "version": None}),
            # User muốn giá bản Plus của chính xe đang bàn
            ("bản plus thì sao?", {"decision": "answer", "model": "VF 8", "version": "Plus"}),
        ],
    },
    {
        "name": "P. Đang clarify version thì đổi sang xe khác",
        "turns": [
            ("vf8 đi được bao xa?", {"decision": "clarify", "reason": "missing_version"}),
            # Đổi xe giữa chừng → clarify lại cho xe MỚI, version cũ không leak
            ("thôi hỏi vf6 đi được bao xa", {"decision": "clarify", "reason": "missing_version", "model": "VF 6"}),
        ],
    },
    {
        "name": "J+L. So sánh cùng dòng khác thế hệ / đổi xe hỏi topic riêng",
        "turns": [
            ("so sánh vf8 và vf8 all new", {"decision": "answer", "category": "so_sánh"}),
            # Sau comparison, nhắc xe mới + topic cụ thể → query đơn xe đó
            ("còn vf9 nội thất thế nào?", {"decision": "answer", "model": "VF 9", "category": "nội_thất"}),
        ],
    },
]


async def run_conversations():
    from app.agent.nodes.classify import classify_node

    for conv in CONVERSATIONS:
        print(f"\n── {conv['name']} ──")
        history = []
        for i, (query, exp) in enumerate(conv["turns"], 1):
            out = await classify_node({"query": query, "history": history})
            ents = out.get("entities", {})
            got = {
                "decision": out.get("decision"),
                "reason": (out.get("reason_code") or ""),
                "model": ents.get("model_code"),
                "version": ents.get("version"),
                "category": out.get("category"),
            }
            tid = f"{conv['name'][:1]}{i}"

            detail = f"{query!r} → dec={got['decision']}"
            problems = []
            if exp.get("decision") != got["decision"]:
                problems.append(f"decision={got['decision']} (exp {exp['decision']})")
            if exp.get("reason") and exp["reason"] not in got["reason"]:
                problems.append(f"reason={got['reason']!r} (exp chứa {exp['reason']!r})")
            if "model" in exp and exp["model"] != got["model"]:
                problems.append(f"model={got['model']} (exp {exp['model']})")
            if "version" in exp and exp["version"] != got["version"]:
                problems.append(
                    f"version={got['version']} (exp {exp['version']})"
                    + ("  <<< LEAK!" if exp["version"] is None else "")
                )
            if "category" in exp and exp["category"] != got["category"]:
                problems.append(f"category={got['category']} (exp {exp['category']})")

            if problems:
                report(tid, False, f"{detail} | {'; '.join(problems)}")
            else:
                extra = f" model={got['model']} ver={got['version']} cat={got['category']}"
                report(tid, True, detail + extra)

            # Build history giống flow thật (user + assistant reply mock)
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": f"[mock answer {i}]"})


async def run_single_shot_regressions():
    """Giữ nguyên các case gốc: current_context (Redis fallback) + clarify version."""
    from app.agent.nodes.classify import classify_node

    print("\n── G. Single-shot regressions (current_context fallback) ──")
    ctx = {"model_code": "VF 8", "version": "Plus", "last_topic": "phạm_vi_di_chuyển"}
    full_hist = [
        {"role": "user", "content": "VF 8 đi được bao nhiêu km?"},
        {"role": "assistant", "content": "Bạn muốn hỏi phiên bản nào của VF 8?"},
        {"role": "user", "content": "Plus"},
        {"role": "assistant", "content": "VF 8 Plus đi 457 km theo WLTP."},
    ]

    cases = [
        # Query tự nêu lại model mà KHÔNG nêu version → câu hỏi mới, phải clarify lại
        (
            "VF 8 đi được bao nhiêu km?",
            full_hist,
            ctx,
            {"decision": "clarify", "reason": "missing_version"},
            "G1: hỏi lại range không nêu bản",
        ),
        # Ellipsis follow-up → kế thừa VF 8 Plus
        ("đi được bao nhiêu km?", full_hist, ctx, {"decision": "answer"}, "G2: ellipsis giữ version"),
        ("VF 8 Plus đi được bao nhiêu km?", full_hist, ctx, {"decision": "answer"}, "G3: version rõ ràng"),
        ("VF 8 đi được bao nhiêu km?", [], {}, {"decision": "clarify"}, "G4: turn đầu không history"),
        ("Plus", full_hist, ctx, {"decision": "answer"}, "G5: trả lời bằng tên bản"),
    ]
    for query, history, cur_ctx, exp, tid in cases:
        out = await classify_node({"query": query, "history": history, "current_context": cur_ctx})
        got_d = out.get("decision")
        got_r = out.get("reason_code") or ""
        ok = got_d == exp["decision"] and (not exp.get("reason") or exp["reason"] in got_r)
        report(tid, ok, f"{query!r} → dec={got_d}, reason={got_r}")


async def main():
    _install_offline_stub()
    print("╔══════════════════════════════════════════════════╗")
    print("║   VERSION-LEAK MULTI-TURN EDGE CASE TESTS        ║")
    print("╚══════════════════════════════════════════════════╝")

    await run_conversations()
    await run_single_shot_regressions()

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
