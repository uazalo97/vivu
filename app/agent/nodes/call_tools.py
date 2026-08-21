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
    get_specs,
    get_price,  # noqa: F401 — kept for _safe_call fallback, primary is get_price_cached
    list_available_models,
    search_knowledge_base,
    get_active_promotions,
    get_onroad_cost_link,
    get_loan_estimate_link,
    get_showroom_charging_link,
    get_booking_link,
    get_maintenance_link,
)
from app.core.cache import (
    get_price_cached,
    get_specs_cached,
    get_colors_cached,
    get_options_cached,
    list_models_cached,
)
from app.agent.nodes.classify import _CROSS_MODEL_RE, _distinct_models

logger = logging.getLogger("bds.graph.call_tools")

# Topic → spec category filter for get_specs.
# Tuple = query multiple categories (an_toàn spans safety + adas).
_TOPIC_SPEC_CATEGORY = {
    "pin_và_sạc": "battery",
    "phạm_vi_di_chuyển": "battery",
    "an_toàn": ("safety", "adas"),  # ADAS keywords (camera 360, camera lùi, ADAS...) nằm ở adas
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
    (
        re.compile(
            r"(công\s*suất|mô[\s-]*men|xoắn|tăng\s*tốc|tốc\s*độ|"
            r"power|torque|acceleration|speed|km/h|\bkW\b|\bNm\b)",
            re.I,
        ),
        "powertrain",
    ),
    (
        re.compile(
            r"(pin|battery|sạc|charge|dung\s*lượng|kwh|range|"
            r"đi\s*được|quãng\s*đường|bao\s*xa|xa\s*hơn)",
            re.I,
        ),
        "battery",
    ),
    (
        re.compile(
            r"(kích\s*thước|dài|rộng|cao|trọng\s*lượng|wheelbase|"
            r"khoảng\s*sáng|gầm|cốp|ground\s*clearance|weight)",
            re.I,
        ),
        "dimension",
    ),
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
    state_models = state.get("model_codes") or []
    t_start = time.time()

    logger.info("CALL_TOOLS: category=%s model=%s version=%s", category, model_code, version)

    cache_hits: set[str] = set()
    if category == "utility":
        tool_results = await _call_utility_tools(query)
    elif (
        len(state_models) >= 2
        or len(_distinct_models(query)) >= 2
        or (not model_code and _CROSS_MODEL_RE.search(query))
    ):
        tool_results = await _call_cross_model_tools(query, state_models)
    elif model_code:
        tool_results, cache_hits = await _call_model_tools(model_code, version, category, query)
    else:
        tool_results = []

    # Build system prompt for generate_node
    system_prompt = await get_system_prompt()

    t_end = time.time()
    logger.info(
        "CALL_TOOLS: done, %d tool results in %.0fms (cache_hits=%s)",
        len(tool_results),
        (t_end - t_start) * 1000,
        sorted(cache_hits),
    )

    return {
        "tool_results": tool_results,
        "messages": [{"role": "system", "content": system_prompt}],
        "iteration": 1,
        "t_retrieve_start": t_start,
        "t_retrieve_end": t_end,
        "cache_hit": bool(cache_hits),
        "cache_type": ",".join(sorted(cache_hits)),
    }


async def _call_model_tools(model_code: str, version: str, category: str, query: str) -> tuple[list[dict], set[str]]:
    """Call tools for a specific model based on topic. Returns (results, cache_hit_types)."""
    results: list[dict] = []
    cache_hits: set[str] = set()

    async def _cached(name: str, cache_type: str, func, *args):
        try:
            data, hit = await func(*args)
            results.append({"tool": name, "result": data, "success": True, "cache_hit": hit})
            if hit:
                cache_hits.add(cache_type)
        except Exception as e:
            logger.warning("Tool %s failed: %s", name, e)
            results.append({"tool": name, "result": {"error": str(e)}, "success": False})

    if category == "giá":
        await _cached("get_price", "price", get_price_cached, model_code, version)

    elif category == "tổng_quan":
        # Thông tin cơ bản: phiên bản + giá + thông số then chốt + màu sắc
        await _cached("list_available_models", "list_models", list_models_cached)
        await _cached("get_price", "price", get_price_cached, model_code, version)
        # Spec then chốt: công suất/tốc độ, pin/quãng đường, kích thước, nội thất (số chỗ)
        for cat in ("powertrain", "battery", "dimension", "interior"):
            await _cached("get_specs", "specs", get_specs_cached, model_code, version, cat)
        await _cached("get_colors", "colors", get_colors_cached, model_code, version)

    elif category == "phiên_bản":
        await _cached("list_available_models", "list_models", list_models_cached)
        # Only get version-related specs, not ALL specs
        r2 = await _safe_call("get_specs", get_specs, model_code, None, "powertrain")
        results.append(r2)

    elif category == "màu_sắc":
        await _cached("get_colors", "colors", get_colors_cached, model_code, version)
        r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query, model_code)
        results.append(r_kb)

    elif category == "option":
        await _cached("get_options", "options", get_options_cached, model_code, version)
        r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query, model_code)
        results.append(r_kb)

    else:
        # Spec-based topics
        spec_cat = _TOPIC_SPEC_CATEGORY.get(category)  # None = all categories; tuple = multiple
        # Refine broad spec topics (thông_số_kỹ_thuật) by query keyword
        if spec_cat is None:
            spec_cat = _refine_spec_category(query)
        # an_toàn spans safety + adas (camera 360, ADAS in adas; airbags, ABS in safety)
        if isinstance(spec_cat, (list, tuple)):
            for sc in spec_cat:
                await _cached("get_specs", "specs", get_specs_cached, model_code, version, sc)
        else:
            await _cached("get_specs", "specs", get_specs_cached, model_code, version, spec_cat)

        # Auto-inject KB for certain topics
        if category in _NEEDS_KB:
            r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query, model_code)
            results.append(r_kb)

        # Color queries under exterior
        if category == "ngoại_thất" and re.search(r"(màu|color)", query, re.I):
            await _cached("get_colors", "colors", get_colors_cached, model_code, version)

    return results, cache_hits


async def _call_cross_model_tools(query: str, model_codes: list[str] | None = None) -> list[dict]:
    """Call tools for cross-model / comparison queries.

    model_codes: explicit models from state (multi-turn comparison follow-up).
    """
    results = []

    is_price = re.search(r"(giá|price|rẻ|đắt|triệu|tỷ)", query, re.I)
    spec_cat = _refine_spec_category(query)
    mentioned = list(model_codes) if model_codes else _distinct_models(query)

    if mentioned:
        # Fetch specs/price for the models explicitly mentioned (vf6 hay vf8)
        tasks = []
        for mc in mentioned:
            if is_price:
                # Price cache 15m theo docs — wrap get_price_cached (trả tuple)
                async def _price_task(m=mc):
                    data, _hit = await get_price_cached(m)
                    return {"tool": "get_price", "result": data, "success": True}

                tasks.append(_price_task())
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

                    async def _price_task(m=mc):
                        data, _hit = await get_price_cached(m)
                        return {"tool": "get_price", "result": data, "success": True}

                    tasks.append(_price_task())
                else:
                    tasks.append(_safe_call("get_specs", get_specs, mc))
            results.extend(await asyncio.gather(*tasks))

    # Comparison/recommendation benefit from knowledge base context.
    # Chỉ search vivu_product_info — tránh nhiễu từ policy/maintenance (bảo hành, cứu hộ).
    r_kb = await _safe_call("search_knowledge_base", search_knowledge_base, query, None, ["vivu_product_info"])
    results.append(r_kb)

    return results


async def _call_utility_tools(query: str) -> list[dict]:
    """Call utility tools based on query content."""
    results = []

    _PATTERNS = [
        (
            r"(showroom|trạm\s*sạc|đại\s*lý|cửa\s*hàng|chi\s*nhánh|hotline|liên\s*hệ|gặp\s*sales)",
            [("get_showroom_charging_link", get_showroom_charging_link)],
        ),
        (r"(lái\s*thử|test\s*drive|đăng\s*ký\s*lái)", [("get_booking_link", get_booking_link, "test_drive")]),
        (
            r"(bảo\s*dưỡng|đặt\s*lịch|booking)",
            [
                ("get_booking_link", get_booking_link, "maintenance"),
                ("get_maintenance_link", get_maintenance_link, "all"),
            ],
        ),
        (
            r"(trả\s*góp|vay|thẩm\s*định|lăn\s*bánh)",
            [("get_loan_estimate_link", get_loan_estimate_link), ("get_onroad_cost_link", get_onroad_cost_link)],
        ),
        (r"(khuyến\s*mãi|ưu\s*đãi|voucher)", [("get_active_promotions", get_active_promotions)]),
        (
            r"(báo\s*lỗi|sửa\s*chữa|hỏng|trục\s*trặc|bảo\s*hành|tự\s*xử\s*lý)",
            [
                ("get_maintenance_link", get_maintenance_link, "all"),
                ("get_showroom_charging_link", get_showroom_charging_link),
            ],
        ),
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
