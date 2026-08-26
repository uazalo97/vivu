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
)
from app.agent.nodes.classify import _distinct_models
from app.agent.context_builder import _extract_query_feature_keys

logger = logging.getLogger("bds.graph.call_tools")

_HIGH_ACCURACY_KEYS = {"price_vnd", "promo_price_vnd", "range_km", "battery_kwh", "fast_charge_min", "specs", "colors", "options"}


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
    elif len(state_models) >= 2 or len(_distinct_models(query)) >= 2 or not model_code:
        tool_results = await _call_cross_model_tools(query, state_models)
    elif model_code:
        tool_results, cache_hits = await _call_model_tools(model_code, version, category, query)
    else:
        tool_results = await _call_cross_model_tools(query, state_models)

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


async def _cached_call(name: str, cache_type: str, func, *args, cache_hits: set) -> dict:
    """Helper dùng chung: gọi cached function, track cache hit. Thread-safe qua tham số cache_hits."""
    try:
        data, hit = await func(*args)
        if hit:
            cache_hits.add(cache_type)
        return {"tool": name, "result": data, "success": True, "cache_hit": hit}
    except Exception as e:
        logger.warning("Tool %s failed: %s", name, e)
        return {"tool": name, "result": {"error": str(e)}, "success": False}


async def _call_model_tools(model_code: str, version: str, category: str, query: str) -> tuple[list[dict], set[str]]:
    """Fetch complete context for the model in parallel: prices, options, colors, all specs, and KB."""
    cache_hits: set[str] = set()

    # Parallel retrieval of all dimensions for this car model
    tasks = [
        _cached_call("get_price", "price", get_price_cached, model_code, None, cache_hits=cache_hits),
        _cached_call("get_options", "options", get_options_cached, model_code, None, cache_hits=cache_hits),
        _cached_call("get_colors", "colors", get_colors_cached, model_code, None, cache_hits=cache_hits),
        _cached_call("get_specs", "specs", get_specs_cached, model_code, None, None, cache_hits=cache_hits),
    ]

    target_keys = _extract_query_feature_keys(query)
    is_high_accuracy = bool(model_code) and bool(target_keys) and target_keys.issubset(_HIGH_ACCURACY_KEYS)
    if not is_high_accuracy:
        tasks.append(_safe_call("search_knowledge_base", search_knowledge_base, query, model_code))

    results = await asyncio.gather(*tasks)
    return list(results), cache_hits


async def _call_cross_model_tools(query: str, model_codes: list[str] | None = None) -> list[dict]:
    """Call tools for cross-model / comparison queries or fleet-wide questions.

    Fix #7: Dùng cached functions thay vì gọi thẳng DB để giảm latency query so sánh.
    """

    mentioned = list(model_codes) if model_codes else _distinct_models(query)

    if mentioned:
        # Fetch complete info for each mentioned model — dùng cache để giảm latency
        cache_hits: set[str] = set()
        tasks = []
        for mc in mentioned:
            tasks.append(_cached_call("get_price", "price", get_price_cached, mc, None, cache_hits=cache_hits))
            tasks.append(_cached_call("get_options", "options", get_options_cached, mc, None, cache_hits=cache_hits))
            tasks.append(_cached_call("get_colors", "colors", get_colors_cached, mc, None, cache_hits=cache_hits))
            tasks.append(_cached_call("get_specs", "specs", get_specs_cached, mc, None, None, cache_hits=cache_hits))
        tasks.append(_safe_call("search_knowledge_base", search_knowledge_base, query))
        return list(await asyncio.gather(*tasks))
    else:
        # Fleet-wide catalog — lấy tất cả model (không cache để đảm bảo fresh data)
        r_models = await _safe_call("list_available_models", list_available_models)
        results = [r_models]
        active_models = ["VF 3", "VF 5", "VF 6", "VF 7", "VF 8", "VF 9", "VF 8 All New", "VF MPV 7"]
        cache_hits_fleet: set[str] = set()
        tasks = []
        for m in active_models:
            tasks.append(_cached_call("get_price", "price", get_price_cached, m, None, cache_hits=cache_hits_fleet))
            tasks.append(
                _cached_call("get_specs", "specs", get_specs_cached, m, None, None, cache_hits=cache_hits_fleet)
            )
            tasks.append(
                _cached_call("get_options", "options", get_options_cached, m, None, cache_hits=cache_hits_fleet)
            )
        tasks.append(_safe_call("search_knowledge_base", search_knowledge_base, query))
        res = await asyncio.gather(*tasks)
        results.extend(res)
        return results


async def _call_utility_tools(query: str) -> list[dict]:
    """Call utility tools based on query content."""
    results = []

    _PATTERNS = [
        (
            r"(showroom|trạm\s*sạc|đại\s*lý|cửa\s*hàng|chi\s*nhánh|hotline|liên\s*hệ|gặp\s*sales|nhân\s*viên|tư\s*vấn\s*viên|tổng\s*đài|hỗ\s*trợ|chăm\s*sóc\s*khách\s*hàng|khiếu\s*nại|cứu\s*hộ|khẩn\s*cấp)",
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
            r"(báo\s*lỗi|sửa\s*chữa|hỏng|trục\s*trặc|bảo\s*hành|tự\s*xử\s*lý|mùi\s*khét|cháy\s*nổ|lỗi\s*pin|pin\s*đỏ)",
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
