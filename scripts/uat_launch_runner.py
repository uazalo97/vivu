#!/usr/bin/env python3
"""Run the AI-first launch UAT scenarios against Vivu's non-streaming API.

The input is JSON so the launch pack stays readable and can model multi-turn
conversations without CSV escaping. The runner performs deterministic checks,
keeps the full transcript for AI/PM review, and marks UI-only cases for manual
execution.

Examples:
    python3 scripts/uat_launch_runner.py --prepare-only
    python3 scripts/uat_launch_runner.py --export-copy-pack
    python3 scripts/uat_launch_runner.py --api-url http://localhost:8000
    python3 scripts/uat_launch_runner.py --only F01,F07,C12,G21
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "pm-docs/uat-ai-first-launch/uat-scenarios.json"
DEFAULT_OUTPUT = REPO_ROOT / "pm-docs/uat-ai-first-launch/results/latest-results.jsonl"
DEFAULT_COPY_PACK = REPO_ROOT / "pm-docs/uat-ai-first-launch/UAT-COPY-PASTE.md"
DEFAULT_CSV_PACK = REPO_ROOT / "pm-docs/uat-ai-first-launch/UAT-TEST-CASES.csv"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().split())


def _compact_number_text(text: str) -> str:
    return re.sub(r"[\s.,]", "", (text or "").lower())


def _contains_any(answer: str, values: list[str]) -> bool:
    haystack = _normalise(answer)
    compact_haystack = _compact_number_text(answer)
    return any(
        _normalise(value) in haystack
        or (any(char.isdigit() for char in value) and _compact_number_text(value) in compact_haystack)
        for value in values
    )


def _contains_all(answer: str, values: list[str]) -> bool:
    haystack = _normalise(answer)
    compact_haystack = _compact_number_text(answer)
    return all(
        _normalise(value) in haystack
        or (any(char.isdigit() for char in value) and _compact_number_text(value) in compact_haystack)
        for value in values
    )


def _evaluate_assertions(answer: str, sources: list[dict], assertions: list[dict]) -> list[str]:
    failures: list[str] = []
    for assertion in assertions:
        assertion_type = assertion.get("type")
        values = assertion.get("values", [])
        if assertion_type == "contains_any" and not _contains_any(answer, values):
            failures.append(f"Thiếu ít nhất một giá trị: {values}")
        elif assertion_type == "contains_all" and not _contains_all(answer, values):
            failures.append(f"Thiếu một hoặc nhiều giá trị: {values}")
        elif assertion_type == "not_contains_any" and _contains_any(answer, values):
            failures.append(f"Chứa giá trị bị cấm: {values}")
        elif assertion_type == "sources_min":
            minimum = int(assertion.get("value", 1))
            if len(sources or []) < minimum:
                failures.append(f"Chỉ có {len(sources or [])} source; cần tối thiểu {minimum}")
    return failures


def _expand_cases(payload: dict[str, Any], only: set[str] | None = None) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for scenario in payload.get("scenarios", []):
        scenario_id = scenario["id"]
        if only and scenario_id not in only:
            continue
        for variant in scenario.get("variants", []):
            expanded.append(
                {
                    "run_id": f"{scenario_id}-{variant['id']}",
                    "scenario_id": scenario_id,
                    "scenario_title": scenario["title"],
                    "group": scenario["group"],
                    "severity": scenario["severity"],
                    "surface": variant.get("surface", scenario.get("surface", "api")),
                    "manual_review": variant.get("manual_review", scenario.get("manual_review", False)),
                    "must_have": scenario.get("must_have", []),
                    "must_not": scenario.get("must_not", []),
                    "oracle": scenario.get("oracle", ""),
                    "variant_label": variant.get("label", ""),
                    "setup": variant.get("setup", []),
                    "steps": variant.get("steps", []),
                }
            )
    return expanded


def _run_api_case(case: dict[str, Any], api_url: str, timeout: float, delay: float) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    history: list[dict[str, str]] = []
    transcript: list[dict[str, Any]] = []
    failures: list[str] = []

    for index, step in enumerate(case["steps"], 1):
        message = step["message"]
        started = time.monotonic()
        try:
            payload = {
                "message": message,
                "session_id": session_id,
                "message_id": f"{case['run_id']}-T{index}-{uuid.uuid4().hex[:8]}",
                "history": history,
            }
            request = Request(
                f"{api_url.rstrip('/')}/api/chat",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            answer = data.get("response", "")
            decision = data.get("decision", "")
            sources = data.get("sources", []) or []
            latency_ms = round((time.monotonic() - started) * 1000, 1)

            expected_decisions = step.get("expected_decisions", [])
            step_failures: list[str] = []
            if expected_decisions and decision not in expected_decisions:
                step_failures.append(f"Decision={decision!r}; expected={expected_decisions}")
            step_failures.extend(_evaluate_assertions(answer, sources, step.get("assertions", [])))
            failures.extend(f"T{index}: {failure}" for failure in step_failures)

            transcript.append(
                {
                    "turn": index,
                    "user": message,
                    "assistant": answer,
                    "decision": decision,
                    "sources": sources,
                    "latency_ms": latency_ms,
                    "assertion_failures": step_failures,
                }
            )
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": answer})
        except Exception as exc:  # keep the batch running for discovery
            failures.append(f"T{index}: API error {type(exc).__name__}: {str(exc)[:240]}")
            transcript.append(
                {
                    "turn": index,
                    "user": message,
                    "assistant": "",
                    "decision": "system_error",
                    "sources": [],
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "assertion_failures": failures[-1:],
                }
            )
            break

        if delay > 0:
            time.sleep(delay)

    if failures:
        auto_status = "AUTO_FAIL"
    elif case["manual_review"]:
        auto_status = "REVIEW"
    else:
        auto_status = "AUTO_PASS"

    return {
        **case,
        "executed_at": _utc_now(),
        "auto_status": auto_status,
        "auto_failures": failures,
        "transcript": transcript,
        "pm_verdict": "",
        "root_cause": "",
        "owner": "",
        "evidence": "",
    }


def _manual_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        **case,
        "executed_at": "",
        "auto_status": "MANUAL_REQUIRED",
        "auto_failures": [],
        "transcript": [],
        "pm_verdict": "",
        "root_cause": "UI",
        "owner": "",
        "evidence": "",
    }


def _write_results(results: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")

    statuses = Counter(result["auto_status"] for result in results)
    summary = {
        "generated_at": _utc_now(),
        "total": len(results),
        "statuses": dict(statuses),
        "release_blocker_candidates": [
            result["run_id"]
            for result in results
            if result["severity"] == "S0" and result["auto_status"] == "AUTO_FAIL"
        ],
    }
    output.with_suffix(".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _assertion_note(assertion: dict[str, Any]) -> str:
    assertion_type = assertion.get("type")
    values = [str(value) for value in assertion.get("values", [])]
    display_values = " | ".join(f"`{value}`" for value in values)
    if assertion_type == "contains_any":
        return f"Câu trả lời phải chứa ít nhất một trong: {display_values}."
    if assertion_type == "contains_all":
        return f"Câu trả lời phải chứa tất cả: {display_values}."
    if assertion_type == "not_contains_any":
        return f"Câu trả lời không được chứa: {display_values}."
    if assertion_type == "sources_min":
        return f"Phải có tối thiểu {assertion.get('value', 1)} nguồn."
    return f"Kiểm tra thủ công assertion: `{json.dumps(assertion, ensure_ascii=False)}`."


def _write_copy_pack(cases: list[dict[str, Any]], output: Path) -> None:
    lines = [
        "# Vivu UAT — Copy/Paste Test Pack",
        "",
        f"> {len(cases)} test case được sinh từ `uat-scenarios.json`. Không sửa nội dung test trực tiếp trong file này; hãy sửa source JSON rồi tái xuất.",
        "",
        "## Cách dùng nhanh",
        "",
        "1. Tìm case theo ID, ví dụ `G21-V1`.",
        "2. Làm phần **Setup** nếu có; nếu không, bắt đầu bằng một chat mới.",
        "3. Copy các prompt `T1`, `T2`... theo đúng thứ tự vào chatbot.",
        "4. Đối chiếu **PASS khi** và **Không được**; ghi verdict ngay trong case.",
        "5. Với lỗi S0: dừng test nhánh đó, chụp evidence và tạo bug ngay.",
        "",
        "Verdict chuẩn: `PASS` / `FAIL` / `BLOCKED`. Ưu tiên chạy S0 trước, sau đó S1/S2.",
        "",
        "Smoke sau mỗi lần deploy: `F01-V1`, `F07-V3`, `C12-V3`, `G21-V1`, `G24-V1`; nếu có sửa UI, thêm `U25-V1..V3`.",
        "",
        "---",
        "",
    ]

    for case in cases:
        lines.extend(
            [
                f"## {case['run_id']} — {case['scenario_title']} · {case['variant_label']}",
                "",
                f"**Mức độ:** `{case['severity']}` · **Nhóm:** `{case['group']}` · **Bề mặt:** `{case['surface'].upper()}`",
                "",
            ]
        )

        if case.get("setup"):
            lines.extend(["### Setup", ""])
            lines.extend(f"- {item}" for item in case["setup"])
            lines.append("")
        else:
            lines.extend(["### Setup", "", "- Bắt đầu bằng chat mới.", ""])

        lines.extend(["### Copy lần lượt", ""])
        for index, step in enumerate(case["steps"], 1):
            lines.extend(
                [
                    f"**T{index}**",
                    "",
                    "```text",
                    step["message"],
                    "```",
                    "",
                ]
            )
            expected_decisions = step.get("expected_decisions", [])
            if expected_decisions:
                lines.append(
                    "Decision chấp nhận: " + ", ".join(f"`{decision}`" for decision in expected_decisions) + "."
                )
                lines.append("")
            assertions = step.get("assertions", [])
            if assertions:
                lines.extend(f"- {_assertion_note(assertion)}" for assertion in assertions)
                lines.append("")

        lines.extend(["### PASS khi", ""])
        lines.extend(f"- {item}" for item in case.get("must_have", []))
        if not case.get("must_have"):
            lines.append("- Đáp ứng đúng intent và không tạo thông tin ngoài dữ liệu được xác nhận.")
        lines.extend(["", "### Không được", ""])
        lines.extend(f"- {item}" for item in case.get("must_not", []))
        if not case.get("must_not"):
            lines.append("- Không bịa dữ liệu hoặc bỏ qua yêu cầu chính của người dùng.")

        lines.extend(
            [
                "",
                f"**Oracle:** `{case.get('oracle', '') or 'AI/PM review'}`",
                "",
                "### Ghi kết quả",
                "",
                "- Verdict: `[ ] PASS`  `[ ] FAIL`  `[ ] BLOCKED`",
                "- Actual:",
                "- Evidence/link:",
                "- Bug ID / Owner:",
                "",
                "---",
                "",
            ]
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_csv_pack(cases: list[dict[str, Any]], output: Path) -> None:
    fieldnames = [
        "run_id",
        "scenario_id",
        "scenario_title",
        "variant_label",
        "group",
        "severity",
        "surface",
        "manual_review",
        "setup",
        "prompt_t1",
        "expected_decision_t1",
        "assertions_t1",
        "prompt_t2",
        "expected_decision_t2",
        "assertions_t2",
        "must_have",
        "must_not",
        "oracle",
        "verdict",
        "actual_result",
        "evidence_link",
        "bug_id",
        "owner",
        "note",
    ]

    def step_value(case: dict[str, Any], index: int, key: str) -> str:
        steps = case.get("steps", [])
        if len(steps) <= index:
            return ""
        step = steps[index]
        if key == "message":
            return str(step.get("message", ""))
        if key == "expected_decisions":
            return " | ".join(str(item) for item in step.get("expected_decisions", []))
        if key == "assertions":
            return " | ".join(_assertion_note(assertion).replace("`", "") for assertion in step.get("assertions", []))
        return ""

    output.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 BOM keeps Vietnamese text readable when the file is opened directly in Excel.
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "run_id": case["run_id"],
                    "scenario_id": case["scenario_id"],
                    "scenario_title": case["scenario_title"],
                    "variant_label": case["variant_label"],
                    "group": case["group"],
                    "severity": case["severity"],
                    "surface": case["surface"],
                    "manual_review": case["manual_review"],
                    "setup": " -> ".join(str(item) for item in case.get("setup", [])),
                    "prompt_t1": step_value(case, 0, "message"),
                    "expected_decision_t1": step_value(case, 0, "expected_decisions"),
                    "assertions_t1": step_value(case, 0, "assertions"),
                    "prompt_t2": step_value(case, 1, "message"),
                    "expected_decision_t2": step_value(case, 1, "expected_decisions"),
                    "assertions_t2": step_value(case, 1, "assertions"),
                    "must_have": " | ".join(str(item) for item in case.get("must_have", [])),
                    "must_not": " | ".join(str(item) for item in case.get("must_not", [])),
                    "oracle": case.get("oracle", ""),
                    "verdict": "",
                    "actual_result": "",
                    "evidence_link": "",
                    "bug_id": "",
                    "owner": "",
                    "note": "",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Vivu AI-first launch UAT runner")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--only", default="", help="Comma-separated scenario IDs, e.g. F01,F07,G21")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--delay", type=float, default=2.1, help="Delay between turns to avoid the API IP rate limit")
    parser.add_argument(
        "--prepare-only", action="store_true", help="Expand the 25 scenarios into 75 cases without calling API"
    )
    parser.add_argument(
        "--export-copy-pack", action="store_true", help="Export a manual Markdown pack for copy/paste UAT"
    )
    parser.add_argument("--copy-pack-output", type=Path, default=DEFAULT_COPY_PACK)
    parser.add_argument("--export-csv", action="store_true", help="Export one CSV row per UAT variant")
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_PACK)
    args = parser.parse_args()

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Cannot read scenario file: {exc}", file=sys.stderr)
        return 2

    only = {item.strip() for item in args.only.split(",") if item.strip()} or None
    cases = _expand_cases(payload, only)
    if not cases:
        print("No runnable cases found.", file=sys.stderr)
        return 2

    if args.export_copy_pack:
        _write_copy_pack(cases, args.copy_pack_output)
        print(f"Wrote {len(cases)} copy/paste cases to {args.copy_pack_output}")
        return 0

    if args.export_csv:
        _write_csv_pack(cases, args.csv_output)
        print(f"Wrote {len(cases)} CSV cases to {args.csv_output}")
        return 0

    if args.prepare_only:
        results = [{**case, "auto_status": "NOT_RUN"} for case in cases]
    else:
        results = []
        for index, case in enumerate(cases, 1):
            label = f"[{index:02d}/{len(cases)}] {case['run_id']}"
            if case["surface"] == "ui":
                result = _manual_case(case)
            else:
                result = _run_api_case(case, args.api_url, args.timeout, args.delay)
            results.append(result)
            print(f"{label} -> {result['auto_status']}")

    _write_results(results, args.output)
    statuses = Counter(result["auto_status"] for result in results)
    print(f"Wrote {len(results)} cases to {args.output}")
    print(f"Status: {dict(statuses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
