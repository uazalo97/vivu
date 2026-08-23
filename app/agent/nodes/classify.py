import logging
import re

from app.agent.classifier import get_classifier, MODEL_RE
from app.agent.graph_state import AgentState

logger = logging.getLogger("bds.graph.classify")

# Small talk / greetings — answer directly, never out_of_scope
_GREETING_RE = re.compile(
    r"^(hello|hi|hey|chào|chào\s*bạn|xin\s*chào|alo|"
    r"bạn\s*là\s*ai|bạn\s*tên\s*gì|mày\s*là\s*ai|"
    r"cảm\s*ơn|thanks|thank\s*you|"
    r"chào\s*buổi\s*(sáng|trưa|chiều|tối))[\s!?.]*$",
    re.IGNORECASE,
)
_GREETING_RESPONSE = (
    "Xin chào! Tôi là trợ lý tư vấn xe VinFast. "
    "Tôi có thể giúp bạn tra cứu thông số, giá, màu sắc, tùy chọn "
    "của các dòng xe VinFast (VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 9, VF MPV 7). "
    "Bạn muốn tìm hiểu về xe nào?"
)

# Utility queries — don't require model, calls utility tools directly
_UTILITY_QUERY_RE = re.compile(
    r"(showroom|trạm\s*sạc|đại\s*lý|cửa\s*hàng|chi\s*nhánh|"
    r"lái\s*thử|test\s*drive|đăng\s*ký\s*lái|"
    r"bảo\s*dưỡng|đặt\s*lịch|booking|"
    r"trả\s*góp|vay|thẩm\s*định|lăn\s*bánh|"
    r"khuyến\s*mãi|ưu\s*đãi|voucher|"
    r"hotline|liên\s*hệ|gặp\s*sales|nhân\s*viên|tư\s*vấn\s*viên|tổng\s*đài|hỗ\s*trợ|chăm\s*sóc\s*khách\s*hàng|khiếu\s*nại|"
    r"báo\s*lỗi|sửa\s*chữa|hỏng|trục\s*trặc|mùi\s*khét|cháy\s*nổ|lỗi\s*pin|pin\s*đỏ|cứu\s*hộ|"
    r"bảo\s*hành|tự\s*xử\s*lý)",
    re.IGNORECASE,
)

# Car/VinFast-related keywords — queries matching these are in-scope
_CAR_RELATED_RE = re.compile(
    r"(xe|ô\s*tô|oto|vinfast|xe\s*điện|ev\b|car\b|"
    r"mua\s*xe|bán\s*xe|thuê\s*xe|đặt\s*xe|đăng\s*ký\s*xe|"
    r"lái\s*xe|xe\s*hơi|phương\s*tiện|pin|sạc|hud|trần\s*kính|cửa\s*sổ\s*trời|"
    r"\bmẫu\b|\bcon\b|\bchiếc\b|\bhàng\b|"
    r"xe\s*nào|mẫu\s*nào|con\s*nào|chiếc\s*nào|giá|quãng\s*đường|thông\s*số)",
    re.IGNORECASE,
)


def _distinct_models(query: str) -> list[str]:
    """Return all distinct normalized model codes mentioned in the query."""
    seen: list[str] = []
    for m in MODEL_RE.finditer(query):
        raw = m.group(1).strip()
        clean = re.sub(r"(VF)\s*(\d+)", r"\1 \2", raw, flags=re.IGNORECASE).strip()
        parts = clean.split()
        clean = " ".join(p.upper() if p.upper().startswith("VF") or p.isdigit() else p.capitalize() for p in parts)
        if clean not in seen:
            seen.append(clean)
    return seen


def _extract_history_context(history: list[dict]) -> dict:
    """Extract model and version from conversation history."""
    ctx: dict = {"model_code": None, "version": None, "models": []}
    classifier = get_classifier()
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        text = msg.get("content", "")
        try:
            cr = classifier.classify(text)
            m = cr.entities.get("model_code")
            v = cr.entities.get("version")
        except Exception:
            m = v = None

        for mm in _distinct_models(text):
            if mm not in ctx["models"]:
                ctx["models"].append(mm)

        if m and not ctx["model_code"]:
            ctx["model_code"] = m
            if v:
                ctx["version"] = v
        elif not m and v and not ctx["version"]:
            ctx["version"] = v
    return ctx


async def classify_node(state: AgentState) -> dict:
    query = state["query"]
    history = state.get("history", [])

    classifier = get_classifier()
    cr = classifier.classify(query, history)

    # ── Extract history context for multi-turn ──
    hist_ctx = _extract_history_context(history)
    current_context = state.get("current_context") or {}
    if not hist_ctx["model_code"]:
        hist_ctx["model_code"] = current_context.get("model_code")
    if not hist_ctx["version"]:
        hist_ctx["version"] = current_context.get("version")

    # Capture query-only model/version BEFORE history merge
    query_has_model = bool(cr.entities.get("model_code"))

    # Merge history model/version if current turn lacks them
    if not cr.entities.get("model_code") and hist_ctx["model_code"]:
        cr.entities["model_code"] = hist_ctx["model_code"]
    if not cr.entities.get("version") and hist_ctx["version"]:
        cr.entities["version"] = hist_ctx["version"]
    has_model = bool(cr.entities.get("model_code"))

    # 1. Small talk / greetings → answer directly
    if _GREETING_RE.search(query):
        return {
            "decision": "greeting",
            "reason_code": "sufficient_direct_evidence",
            "entities": cr.entities,
            "specificity": "clear",
            "category": "general",
            "response_text": _GREETING_RESPONSE,
        }

    # 2. Utility queries (showroom, trạm sạc, hotline 1900 23 23 89, cứu hộ, booking)
    if _UTILITY_QUERY_RE.search(query):
        return {
            "decision": "answer",
            "reason_code": "utility_query",
            "entities": cr.entities,
            "specificity": "unclear",
            "category": "utility",
        }

    # 3. Multi-model comparison (VF6 vs VF8, so sánh ...)
    multi_models = _distinct_models(query)
    if len(multi_models) >= 2:
        return {
            "decision": "answer",
            "reason_code": "sufficient_direct_evidence",
            "entities": {},
            "specificity": "clear",
            "category": "so_sánh",
            "model_codes": multi_models,
        }

    # Follow-up to multi-model comparison from history
    hist_models = hist_ctx.get("models", [])
    if not query_has_model and len(hist_models) >= 2:
        return {
            "decision": "answer",
            "reason_code": "sufficient_direct_evidence",
            "entities": {},
            "specificity": "clear",
            "category": "so_sánh",
            "model_codes": hist_models,
        }

    # 4. Single model query (VF7, VF8, VF6...)
    if has_model:
        return {
            "decision": "answer",
            "reason_code": "sufficient_direct_evidence",
            "entities": cr.entities,
            "specificity": cr.specificity,
            "category": "general",
        }

    # 5. Cross-model / Fleet query without a specific model (e.g. "xe nào có HUD", "giá xe điện")
    if _CAR_RELATED_RE.search(query):
        return {
            "decision": "answer",
            "reason_code": "sufficient_direct_evidence",
            "entities": cr.entities,
            "specificity": "unclear",
            "category": "cross_model",
        }

    # 6. Truly out of scope (weather, cooking, football...)
    return {
        "decision": "out_of_scope",
        "reason_code": "unsupported_topic",
        "response_text": "Hiện tại mình chỉ hỗ trợ tư vấn thông tin sản phẩm xe VinFast. Bạn có thể hỏi về thông số, tính năng, pin/sạc, phạm vi di chuyển của xe.",
        "entities": cr.entities,
        "specificity": "unclear",
        "category": "general",
    }
