"""
Direct tool calls based on classify_node output.
No LLM call — routes tool calls by topic/entities deterministically.
Replaces build_messages_node + execute_tools_node (saves 1 LLM call).
"""
import asyncio
import logging
import re
import time

from app.agent.graph_state import AgentState
from app.agent.prompts import get_system_prompt
from app.agent.tools import (
    get_specs, get_price, get_colors, get_options, list_available_models,
    search_knowledge_base, get_active_promotions, get_onroad_cost_link,
    get_loan_estimate_link, get_showroom_charging_link, get_booking_link,
    get_maintenance_link,
)
from app.agent.nodes.classify import _CROSS_MODEL_RE, _distinct_models

logger = logging.getLogger("bds.graph.call_tools")

# Topic → spec category filter for get_specs
_TOPIC_SPEC_CATEGORY = {
    "pin_và_sạc": "battery",
    "phạm_vi_di_chuyển": "battery",
    "an_toàn": "safety",
    "nội_thất": "interior",
    "ngoại_thất": "exterior",
    "tính_năng_nổi_bật": None,  # spans adas + infotainment + connected + security + convenience
    "kích_thước": "dimension",
    "thông_số_kỹ_thuật": None,  # powertrain + chassis + all specs
    # "giá": handled separately via get_price
    # "phiên_bản": handled separately via list_available_models
}

# Topics that need search_knowledge_base auto-injection
_NEEDS_KB = {"an_toàn", "nội_thất", "ngoại_thất", "tính_năng_nổi_bật"}

# Query → spec-category refinement for thông_số_kỹ_thuật (broad topic).
# Order matters: first match wins.
_QUERY_SPEC_REFINE = [
    (re.compile(
        r"(công\s*suất|mô[\s-]*men|xoắn|tăng\s*tốc|tốc\s*độ|"
        r"power|torque|acceleration|speed|km/h|\bkW\b|\bNm\b)", re.I), "powertrain"),
    (re.compile(
        r"(pin|battery|sạc|charge|dung\s*lượng|kwh|range|"
        r"đi\s*được|quãng\s*đường|bao\s*xa|xa\s*hơn)", re.I), "battery"),
    (re.compile(
        r"(kích\s*thước|dài|rộng|cao|trọng\s*lượng|wheelbase|"
        r"khoảng\s*sáng|gầm|cốp|ground\s*clearance|weight)", re.I), "dimension"),
]


def _refine_spec_category(query: str) -> str | None:
    """Map a broad spec query to a concrete spec_category, or None to get all."""
    if not query:
        return None
    for pattern, cat in _QUERY_SPEC_REFINE:
        if pattern.search(query):
            return cat
    return None


async def call_tools_node(state: AgentState) -> dict:
    entities = state.get("entities", {})
    category = state.get("category", "general")
    query = state.get("query", "")
    model_code = entities.get("model_code")
    version = entities.get("version")
    t_start = time.time()

    logger.info("CALL_TOOLS: category=%s model=%s version=%s", category, model_code, version)

    if category == "utility":
        tool_results = await _call_utility_tools(query)
    elif len(_distinct_models(query)) >= 2 or (not model_code and _CROSS_MODEL_RE.search(query)):
        tool_results = await _call_cross_model_tools(query)
    elif model_code:
        tool_results = await _call_model_tools(model_code, version, category, query)
    else:
        tool_results = []

    # Build system prompt for generate_node
    system_prompt = await get_system_prompt()

    t_end = time.time()
    logger.info("CALL_TOOLS: done, %d tool results in %.0fms",
                len(tool_results), (t_end - t_start) * 1000)

    return {
        "tool_results": tool_results,
        "messages": [{"role": "system", "content": system_prompt}],
        "iteration": 1,
        "t_retrieve_start": t_start,
        "t_retrieve_end": t_end,
    }


async def _call_model_tools(model_code: str, version: str, category: str, query: str) -> list[dict]:
    """Call tools for a specific model based on topic."""
    results = []

    if category == "giá":
        r = await _safe_call("get_price", get_price, model_code, version)
        results.append(r)

    elif category == "phiên_bản":
        r1 = await _safe_call("list_available_models", list_available_models)
        results.append(r1)
        # Only get version-related specs, not ALL specs
        r2 = await _safe_call("get_specs", get_specs, model_code, None, "powertrain")
        results.append(r2)

    elif category == "màu_sắc":
        r = await _safe_call("get_colors", get_colors, model_code, version)
        results.append(r)
        r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query, model_code)
        results.append(r_kb)

    elif category == "option":
        r = await _safe_call("get_options", get_options, model_code, version)
        results.append(r)
        r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query, model_code)
        results.append(r_kb)

    else:
        # Spec-based topics
        spec_cat = _TOPIC_SPEC_CATEGORY.get(category)  # None = all categories
        # Refine broad spec topics (thông_số_kỹ_thuật) by query keyword
        if spec_cat is None:
            spec_cat = _refine_spec_category(query)
        r = await _safe_call("get_specs", get_specs, model_code, version, spec_cat)
        results.append(r)

        # Auto-inject KB for certain topics
        if category in _NEEDS_KB:
            r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query, model_code)
            results.append(r_kb)

        # Color queries under exterior
        if category == "ngoại_thất" and re.search(r"(màu|color)", query, re.I):
            r_color = await _safe_call("get_colors", get_colors, model_code, version)
            results.append(r_color)

    return results


async def _call_cross_model_tools(query: str) -> list[dict]:
    """Call tools for cross-model / comparison queries."""
    results = []

    is_price = re.search(r"(giá|price|rẻ|đắt|triệu|tỷ)", query, re.I)
    spec_cat = _refine_spec_category(query)
    mentioned = _distinct_models(query)

    if mentioned:
        # Fetch specs/price for the models explicitly mentioned (vf6 hay vf8)
        tasks = []
        for mc in mentioned:
            if is_price:
                tasks.append(_safe_call("get_price", get_price, mc))
            else:
                tasks.append(_safe_call("get_specs", get_specs, mc, None, spec_cat))
        results.extend(await asyncio.gather(*tasks))
    else:
        # Generic cross-model: list all models + per-model specs/price
        r_models = await _safe_call("list_available_models", list_available_models)
        results.append(r_models)
        if r_models.get("success"):
            models = r_models["result"].get("models", [])
            tasks = []
            for m in models:
                mc = m.get("model_code", "")
                if not mc:
                    continue
                if is_price:
                    tasks.append(_safe_call("get_price", get_price, mc))
                else:
                    tasks.append(_safe_call("get_specs", get_specs, mc))
            results.extend(await asyncio.gather(*tasks))

    # Comparison/recommendation benefit from knowledge base context
    r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query)
    results.append(r_kb)

    return results


async def _call_utility_tools(query: str) -> list[dict]:
    """Call utility tools based on query content."""
    results = []

    _PATTERNS = [
        (r"(showroom|trạm\s*sạc|đại\s*lý|cửa\s*hàng|chi\s*nhánh|hotline|liên\s*hệ|gặp\s*sales)",
         [("get_showroom_charging_link", get_showroom_charging_link)]),
        (r"(lái\s*thử|test\s*drive|đăng\s*ký\s*lái)",
         [("get_booking_link", get_booking_link, "test_drive")]),
        (r"(bảo\s*dưỡng|đặt\s*lịch|booking)",
         [("get_booking_link", get_booking_link, "maintenance"),
          ("get_maintenance_link", get_maintenance_link, "all")]),
        (r"(trả\s*góp|vay|thẩm\s*định|lăn\s*bánh)",
         [("get_loan_estimate_link", get_loan_estimate_link),
          ("get_onroad_cost_link", get_onroad_cost_link)]),
        (r"(khuyến\s*mãi|ưu\s*đãi|voucher)",
         [("get_active_promotions", get_active_promotions)]),
        (r"(báo\s*lỗi|sửa\s*chữa|hỏng|trục\s*trặc|bảo\s*hành|tự\s*xử\s*lý)",
         [("get_maintenance_link", get_maintenance_link, "all"),
          ("get_showroom_charging_link", get_showroom_charging_link)]),
    ]

    matched = False
    for pattern, tool_specs in _PATTERNS:
        if re.search(pattern, query, re.I):
            matched = True
            for spec in tool_specs:
                name = spec[0]
                func = spec[1]
                args = spec[2:] if len(spec) > 2 else ()
                r = await _safe_call(name, func, *args)
                results.append(r)

    if not matched:
        # Default: showroom link
        r = await _safe_call("get_showroom_charging_link", get_showroom_charging_link)
        results.append(r)

    # Always attach knowledge base search: give a generic answer + specific link
    r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query)
    results.append(r_kb)

    return results


async def _safe_call(name: str, func, *args) -> dict:
    """Safely call a tool function, return standardized result."""
    try:
        result = await func(*args) if asyncio.iscoroutinefunction(func) else func(*args)
        return {"tool": name, "result": result, "success": True}
    except Exception as e:
        logger.warning("Tool %s failed: %s", name, e)
        return {"tool": name, "result": {"error": str(e)}, "success": False}
