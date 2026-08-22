# AI Prompts cho UAT

## Prompt 1 — Judge một case

```text
Bạn là UAT Judge cho Vivu, chatbot tư vấn xe VinFast tại Việt Nam.

Nguyên tắc:
- Chỉ dùng ORACLE và MUST-HAVE/MUST-NOT bên dưới để xác minh factual claim.
- Không dùng kiến thức nền hoặc Internet để tự bổ sung facts.
- Khác wording hoặc khác PRD vẫn có thể PASS nếu đúng, an toàn, hữu ích và hợp lý.
- Nếu oracle không đủ để kết luận một factual claim, trả REVIEW, không đoán.

SCENARIO:
{{scenario_title}}

SEVERITY:
{{severity}}

ORACLE:
{{oracle}}

MUST-HAVE:
{{must_have}}

MUST-NOT:
{{must_not}}

TRANSCRIPT:
{{transcript}}

Hãy trả đúng JSON:
{
  "verdict": "PASS | FAIL | REVIEW",
  "reason": "tối đa 2 câu",
  "violations": ["..."],
  "user_impact": "tối đa 1 câu",
  "suspected_root_cause": "DATA | ENTITY | ROUTING | GROUNDING | CONTEXT | UI | PLATFORM | PRODUCT",
  "suggested_severity": "S0 | S1 | S2",
  "next_test_ids": ["tối đa 3 biến thể nên chạy tiếp"]
}
```

## Prompt 2 — Gom lỗi theo root cause

```text
Bạn là UAT Triage Lead. Dưới đây là các case FAIL đã được PM xác nhận.

{{confirmed_failures}}

Hãy:
1. Gom các lỗi có khả năng cùng root cause.
2. Không tạo ticket riêng cho từng câu hỏi nếu chung lỗi.
3. Ưu tiên theo user impact, tần suất và effort fix trong 3-4 ngày cuối.
4. Chọn tối đa Top 3 cluster cần fix ngay.

Trả JSON:
{
  "clusters": [
    {
      "cluster_id": "...",
      "root_cause": "DATA | ENTITY | ROUTING | GROUNDING | CONTEXT | UI | PLATFORM | PRODUCT",
      "affected_run_ids": ["..."],
      "failure_pattern": "...",
      "user_impact": "...",
      "severity": "S0 | S1 | S2",
      "recommended_action": "FIX_NOW | MITIGATE | ACCEPT",
      "smallest_safe_fix": "...",
      "regression_scope": ["..."]
    }
  ],
  "top_3": ["cluster_id"]
}
```

## Prompt 3 — Sinh regression sau fix

```text
Một lỗi Vivu vừa được fix.

ROOT CAUSE:
{{root_cause}}

ORIGINAL FAILURES:
{{failures}}

FIX SUMMARY:
{{fix_summary}}

Hãy tạo 5 regression cases:
- 2 case tái hiện trực tiếp.
- 2 case cùng pattern nhưng model/version khác.
- 1 case lân cận để phát hiện side effect.

Mỗi case gồm:
- id
- steps
- must_have
- must_not
- oracle_required
- expected_decision
- severity_if_fail

Không tự tạo facts; đánh dấu NEED_ORACLE nếu thiếu dữ liệu chính thức.
```

## Prompt 4 — Tạo bug packet cho engineering

```text
Chuyển failure cluster dưới đây thành bug packet ngắn cho engineering.

{{cluster}}

Output Markdown theo đúng format:

Title:
Severity:
Affected Run IDs:
User impact:
3-step reproduction:
Expected:
Actual:
Evidence:
Suspected layer:
Smallest safe fix:
Regression gate:
Accepted mitigation nếu không kịp fix:

Không viết mô tả chung chung. Tối đa 20 dòng.
```

## Prompt 5 — Daily Go/No-Go summary

```text
Bạn là PM Release Assistant. Tóm tắt UAT trong tối đa 12 dòng.

BUILD/SNAPSHOT:
{{build_and_snapshot}}

RESULT SUMMARY:
{{summary}}

CONFIRMED FAILURES:
{{failures}}

ACCEPTED RISKS:
{{accepted_risks}}

Trả về:
- Go/No-Go recommendation.
- S0 còn mở.
- Top 3 root cause.
- Fix đã verify.
- Mitigation bắt buộc.
- Việc duy nhất cần làm tiếp theo.
```

