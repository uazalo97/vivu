import logging
import re

from app.agent.classifier import get_classifier, MODEL_RE
from app.agent.graph_state import AgentState
from app.agent.intent import MAIN_MODELS

logger = logging.getLogger("bds.graph.classify")

VERSION_QUERY_RE = re.compile(
    r"(phi[eê]n\s+b[aả]n|b[aả]n\s+n[aà]o|c[oó]\s+m[aấ]y\s+b[aả]n|version|edition|có\s*mấy)",
    re.IGNORECASE,
)

# Match ONE version name (dùng để đếm version trong query cho so sánh version-pair)
_VERSION_TOKEN_RE = re.compile(
    r"(PlusCaptain|Plus\s*AWD|Plus|Eco|"
    r"Ti[êe]u\s*[Cc]hu[ẩẩ]?n|N[ââ]ng\s*[Cc]ao|Cao\s*[Cc][ấấ]?p|"
    r"The\s*All\s*New|All\s*New)",
    re.IGNORECASE,
)

_AMBIGUOUS_PRONOUN_RE = re.compile(
    r"(xe\s*này|mẫu\s*này|chiếc\s*này|em\s*này)",
    re.IGNORECASE,
)

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

# Utility queries — don't require model, LLM calls utility tools directly
_UTILITY_QUERY_RE = re.compile(
    r"(showroom|trạm\s*sạc|đại\s*lý|cửa\s*hàng|chi\s*nhánh|"
    r"lái\s*thử|test\s*drive|đăng\s*ký\s*lái|"
    r"bảo\s*dưỡng|đặt\s*lịch|booking|"
    r"trả\s*góp|vay|thẩm\s*định|lăn\s*bánh|"
    r"khuyến\s*mãi|ưu\s*đãi|voucher|"
    r"hotline|liên\s*hệ|gặp\s*sales|"
    r"báo\s*lỗi|sửa\s*chữa|hỏng|trục\s*trặc|"
    r"bảo\s*hành|tự\s*xử\s*lý)",
    re.IGNORECASE,
)

# Car/VinFast-related keywords — queries matching these are in-scope even
# without a specific model, so they should be clarify not out_of_scope.
_CAR_RELATED_RE = re.compile(
    r"(xe|ô\s*tô|oto|vinfast|xe\s*điện|ev\b|car\b|"
    r"mua\s*xe|bán\s*xe|thuê\s*xe|đặt\s*xe|đăng\s*ký\s*xe|"
    r"lái\s*xe|xe\s*hơi|phương\s*tiện|"
    r"\bmẫu\b|\bcon\b|\bchiếc\b|\bhàng\b|"
    r"xe\s*nào|mẫu\s*nào|con\s*nào|chiếc\s*nào)",
    re.IGNORECASE,
)

# Cross-model queries — inherently about ALL models, don't require a specific one.
# Route as "answer" with list_available_models + get_price/get_specs tools.
_CROSS_MODEL_RE = re.compile(
    r"((xe|mẫu|con)\s*nào\s*(rẻ|đắt|tốt|bền|đẹp|an\s*toàn|tiết\s*kiệm|phù\s*hợp|hot|bán\s*chạy)"
    r"|((xe|mẫu|con)\s*nào\s*(giá|price))"
    r"|(so\s*sánh|nên\s*mua|phù\s*hợp\s*với|tư\s*vấn\s*mua)"
    r"|(giá\s*(dưới|trên|khoảng|từ|đến|bao\s*nhiêu))"
    r"|((rẻ|đắt|tốt|bền|đẹp|nhỏ|lớn|ổn)\s*nhất))",
    re.IGNORECASE,
)

# Cross-model FEATURE queries — "xe nào có cửa sổ trời", "những xe nào có ghế massage",
# "dòng nào có camera 360", "xe nào được trang bị HUD"…
# User không biết model nào có tính năng → KHÔNG clarify, scan tất cả model và trả lời.
_CROSS_MODEL_FEATURE_RE = re.compile(
    r"((xe|mẫu|con|dòng|model)\s*nào\s*(có|được\s*trang\s*bị|trang\s*bị)"
    r"|những\s*(xe|mẫu|con|dòng|model)\s*nào"
    r"|có\s*trên\s*(những\s*)?(xe|mẫu|con|dòng|model)\s*nào"
    r"|có\s*ở\s*(những\s*)?(xe|mẫu|con|dòng|model)\s*nào)",
    re.IGNORECASE,
)

# ── Topic classification (spec's 9 supported topics) ────────────────────────

_TOPIC_KEYWORDS = {
    "giá": [
        r"giá\s*bao\s*nhiêu",
        r"giá\s*bán",
        r"giá\s*niêm\s*yết",
        r"\bgiá\b",
        r"bao\s*nhiêu\s*tiền",
        r"chi\s*phí",
        r"ưu\s*đãi",
        r"giá\s*(xe|VF)",
        r"price",
        r"rẻ\s*nhất",
        r"đắt\s*nhất",
        r"rẻ\s*hơn",
        r"đắt\s*hơn",
        r"giá\s*(dưới|trên|khoảng|từ|đến)",
        r"giá\s*của",
        r"triệu\s*đồng",
        r"triệu\b",
        r"tỷ\b",
        r"trả\s*góp",
        r"vay\s*mua",
    ],
    "pin_và_sạc": [
        r"sạc\s*nhanh",
        r"sạc\s*chậm",
        r"sạc\s*đầy",
        r"thời\s*gian\s*sạc",
        r"trạm\s*sạc",
        r"charger",
        r"charging",
        r"ổ\s*điện",
        r"pin\s*(lithium|lipo|LFP)",
        r"dung\s*lượng\s*pin",
        r"pin\s*bao\s*nhiêu",
        r"\bpin\b",
        r"sạc",
        r"nạp\s*pin",
        r"phút.*10.*70",
        r"10.*70.*phút",
    ],
    "phạm_vi_di_chuyển": [
        r"đi\s*được\s*bao\s*xa",
        r"di\s*chuyển",
        r"range",
        r"phạm\s*vi",
        r"đi\s*được\s*bao\s*nhiêu\s*km",
        r"đi\s*được\s*bao\s*km",
        r"quãng\s*đường",
    ],
    "an_toàn": [
        r"túi\s*khí",
        r"airbag",
        r"ADAS",
        r"phanh",
        r"ABS",
        r"EBD",
        r"ESC",
        r"collision",
        r"cảnh\s*báo",
        r"camera\s*lùi",
        r"camera\s*360",
        r"an\s*toàn",
        r"an\s*toàn\s*không",
        r"có\s*an\s*toàn",
        r"isofix",
        r"tpms",
        r"đai\s*an\s*toàn",
        r"chống\s*trộm",
        r"báo\s*động",
    ],
    "màu_sắc": [
        r"màu",
        r"màu\s*(gì|nào|sắc|xe)",
        r"bao\s*nhiêu\s*màu",
        r"mấy\s*màu",
        r"color",
        r"sơn",
    ],
    "option": [
        r"option",
        r"tùy\s*chọn",
        r"tuỳ\s*chọn",
        r"nâng\s*cấp",
        r"lazang",
        r"la-zăng",
        r"mâm\s*(hợp\s*kim|lõi\s*thép)",
        r"trần\s*kính",
        r"hệ\s*dẫn\s*động",
    ],
    "nội_thất": [
        r"nội\s*thất",
        r"ghế",
        r"chỗ\s*ngồi",
        r"seats",
        r"seat\s*(count|number)|số\s*chỗ",
        r"mấy\s*chỗ",
        r"bao\s*nhiêu\s*chỗ",
        r"\bchỗ\b",
        r"màn\s*hình",
        r"loa",
        r"âm\s*thanh",
        r"điều\s*hòa",
        r"khoang\s*xe",
        r"vô\s*lăng",
        r"HUD",
        r"leatherette",
        r"speaker",
        r"display",
        r"sưởi",
        r"thông\s*gió",
        r"massage",
        r"cửa\s*sổ\s*trời",
        r"sunroof",
    ],
    "ngoại_thất": [
        r"ngoại\s*thất",
        r"đèn",
        r"màu\s*xe",
        r"mâm",
        r"la-zăng",
        r"gương",
        r"body",
        r"design",
        r"kiểu\s*dáng",
        r"headlight",
        r"tail\s*light",
        r"DRL",
        r"lốp",
        r"tire",
    ],
    "tính_năng_nổi_bật": [
        r"tính\s*năng",
        r"trang\s*bị",
        r"công\s*nghệ",
        r"thông\s*minh",
        r"tiện\s*nghi",
        r"OTA",
        r"navigation",
        r"bluetooth",
        r"apple\s*carplay",
        r"android\s*auto",
        r"gaming",
        r"trợ\s*lý\s*ảo",
        r"giọng\s*nói",
        r"voice",
        r"karaoke",
        r"ứng\s*dụng",
        r"app",
        r"web\s*browser",
        r"kết\s*nối",
        r"điều\s*khiển\s*từ\s*xa",
        r"esim",
        r"wifi",
    ],
    "phiên_bản": [
        r"phiên\s*bản",
        r"version",
        r"bản\s*nào",
        r"có\s*mấy\s*bản",
        r"danh\s*sách",
        r"khác\s*nhau\s*giữa",
    ],
    "kích_thước": [
        r"kích\s*thước",
        r"chiều\s*dài",
        r"chiều\s*rộng",
        r"chiều\s*cao",
        r"trọng\s*lượng",
        r"wheelbase",
        r"không\s*gian",
        r"ốp\s*lưng",
        r"boot",
        r"cốp",
    ],
    "thông_số_kỹ_thuật": [
        r"công\s*suất",
        r"mô[\s-]*men",
        r"xoắn",
        r"tốc\s*độ",
        r"tốc\s*tối\s*đa",
        r"battery",
        r"kWh",
        r"trọng\s*lượng",
        r"wheelbase",
        r"ground\s*clearance",
        r"power",
        r"torque",
        r"speed",
        r"km/h",
        r"Nm",
        r"kW",
        r"thông\s*số",
        r"specs",
        r"spec",
        r"trọng\s*tải",
        r"tăng\s*tốc",
        r"gia\s*tốc",
        r"tốc\s*độ\s*tối\s*đa",
    ],
}

_TOPIC_RE = {topic: re.compile("|".join(kw), re.IGNORECASE) for topic, kw in _TOPIC_KEYWORDS.items()}

# Topic → allowed tools
# Note: execute_tools_node auto-injects search_knowledge_base parallel to get_specs/get_colors
_TOPIC_TOOLS = {
    "thông_số_kỹ_thuật": {"get_specs", "ask_clarification"},
    "pin_và_sạc": {"get_specs", "ask_clarification"},
    "phạm_vi_di_chuyển": {"get_specs", "ask_clarification"},
    "an_toàn": {"get_specs", "ask_clarification"},
    "nội_thất": {"get_specs", "ask_clarification"},
    "ngoại_thất": {"get_specs", "ask_clarification"},
    "màu_sắc": {"get_colors", "ask_clarification"},
    "option": {"get_options", "ask_clarification"},
    "tính_năng_nổi_bật": {"get_specs", "ask_clarification"},
    "phiên_bản": {"list_available_models", "get_specs", "ask_clarification"},
    "kích_thước": {"get_specs", "ask_clarification"},
    "giá": {"get_price", "ask_clarification"},
    "tổng_quan": {"list_available_models", "get_price", "get_specs", "get_colors"},
    "general": None,
}

# Topics where data typically differs between versions — require version (BDS-03)
_VERSION_DEPENDENT_TOPICS = {"thông_số_kỹ_thuật", "phạm_vi_di_chuyển"}


def _classify_topic(query: str) -> str:
    for topic, pattern in _TOPIC_RE.items():
        if pattern.search(query):
            return topic
    return "general"


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


def _distinct_versions(query: str) -> list[str]:
    """Return distinct version names mentioned in the query (dùng cho so sánh version-pair)."""
    seen: list[str] = []
    for m in _VERSION_TOKEN_RE.finditer(query):
        key = m.group(1).strip().lower().replace(" ", "")
        if key not in seen:
            seen.append(key)
    return seen


def _is_broad_topic(query: str) -> bool:
    """Check if query is too broad (BDS-05)."""
    broad_patterns = [
        r"(cho\s*tôi\s*biết|thông\s*tin\s*về|giới\s*thiệu|"
        r"có\s*gì\s*hay|tổng\s*quan|overview|"
        r"thế\s*nào|như\s*thế\s*nào|ra\s*sao)",
    ]
    broad_re = re.compile("|".join(broad_patterns), re.IGNORECASE)
    return bool(broad_re.search(query))


def _extract_history_context(history: list[dict]) -> dict:
    """Extract model, version, and topic from conversation history.

    Pass 1 (newest→oldest): most recent model/version/topic win.
    Pass 2 (oldest→newest): cross-model comparison context — ghép cặp
    "so sánh với VF X" (1 model + keyword) với model của turn trước, nhưng
    KHÔNG cộng dồn 2 câu hỏi đơn lẻ ("VF 8" rồi "VF 8 All New") thành 2 model giả.
    """
    ctx: dict = {"model_code": None, "version": None, "topic": None, "models": []}
    classifier = get_classifier()

    # Pass 1: newest-first — model_code / version / topic
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

        if m and not ctx["model_code"]:
            ctx["model_code"] = m
            # Always set version from the SAME message as model (even if None).
            # Prevents version leakage from older turns about different models.
            # E.g. "bản Plus" (VF3) must NOT leak into "tôi muốn biết về VF5".
            ctx["version"] = v
        elif not m and v and not ctx["version"]:
            ctx["version"] = v

        t = _classify_topic(text)
        if t != "general" and not ctx["topic"]:
            ctx["topic"] = t

    # Pass 2: oldest-first — multi-model comparison context.
    prior_model = None
    for msg in history:
        if msg.get("role") != "user":
            continue
        text = msg.get("content", "")
        text_models = _distinct_models(text)
        if len(text_models) >= 2:
            # So sánh tường minh ("so sánh VF 8 và VF 9")
            for mm in text_models:
                if mm not in ctx["models"]:
                    ctx["models"].append(mm)
        elif len(text_models) == 1 and _CROSS_MODEL_RE.search(text):
            # "so sánh với VF X" → ghép cặp model turn trước với VF X
            mm = text_models[0]
            if prior_model and prior_model != mm and prior_model not in ctx["models"]:
                ctx["models"].append(prior_model)
            if mm not in ctx["models"]:
                ctx["models"].append(mm)
        # Cập nhật model gần nhất (để ghép cặp ở turn "so sánh với X" sau)
        if text_models:
            prior_model = text_models[0]

    return ctx


def _is_followup_to_clarify(history: list[dict]) -> bool:
    """Check if conversation indicates a follow-up to a clarify question."""
    if not history:
        return False
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            clarify_indicators = [
                "bạn muốn hỏi",
                "bạn muốn tìm",
                "phiên bản nào",
                "vf 6 hay vf 8",
                "vf6 hay vf8",
                "thông tin nào",
                "chủ đề nào",
            ]
            return any(ind in content for ind in clarify_indicators)
    return False


async def classify_node(state: AgentState) -> dict:
    query = state["query"]
    history = state.get("history", [])

    classifier = get_classifier()
    cr = classifier.classify(query, history)

    # ── Decision Order ──

    # Classifier always returns "answer" now (no OOS).
    # If classifier returned clarify (multi-model), handle it.
    if cr.decision == "clarify":
        return {
            "decision": "clarify",
            "reason_code": "missing_context",
            "response_text": "Bạn muốn hỏi về xe nào?",
            "entities": cr.entities,
            "specificity": "unclear",
        }

    # ── Extract history context for multi-turn ──
    hist_ctx = _extract_history_context(history)
    # Fallback sang current_context (Redis session store) khi history bị cắt
    current_context = state.get("current_context") or {}
    if not hist_ctx["model_code"]:
        hist_ctx["model_code"] = current_context.get("model_code")
    if not hist_ctx["version"]:
        hist_ctx["version"] = current_context.get("version")
    if not hist_ctx["topic"]:
        hist_ctx["topic"] = current_context.get("topic") or current_context.get("last_topic")
    is_followup = _is_followup_to_clarify(history)

    # Capture query-only model/version BEFORE history merge (for OOS guard)
    query_has_model = bool(cr.entities.get("model_code"))
    query_has_version = bool(cr.entities.get("version"))

    # Merge history model/version into entities if current turn missing them
    if not cr.entities.get("model_code") and hist_ctx["model_code"]:
        cr.entities["model_code"] = hist_ctx["model_code"]
    if not cr.entities.get("version") and hist_ctx["version"]:
        cr.entities["version"] = hist_ctx["version"]

    has_model = bool(cr.entities.get("model_code"))
    has_version = bool(cr.entities.get("version"))
    topic = _classify_topic(query)
    raw_topic = topic  # Before history inheritance — used for OOS check

    # Version-pair comparison ("vf8 eco và plus", "eco vs plus") → phiên_bản
    # (chỉ khi query không có topic cụ thể; topic feature như giá/camera vẫn thắng)
    # Clear version: get_specs cần trả TẤT CẢ versions để so sánh, không chỉ 1 version.
    if topic == "general" and len(_distinct_versions(query)) >= 2:
        topic = "phiên_bản"
        cr.entities.pop("version", None)

    # Inherit topic from history if current query topic is general
    if topic == "general" and hist_ctx["topic"]:
        topic = hist_ctx["topic"]

    # Small talk / greetings → answer directly, never out_of_scope
    if _GREETING_RE.search(query):
        return {
            "decision": "greeting",
            "reason_code": "sufficient_direct_evidence",
            "entities": cr.entities,
            "specificity": "clear",
            "category": "general",
            "response_text": _GREETING_RESPONSE,
        }

    # Utility queries (showroom, charging station, booking, loan, promotions)
    # take precedence over model/topic routing — they don't need a model.
    if _UTILITY_QUERY_RE.search(query):
        return {
            "decision": "answer",
            "reason_code": "utility_query",
            "entities": cr.entities,
            "specificity": "unclear",
            "category": "utility",
        }

    # Comparison between 2+ distinct models (vf6 hay vf8, so sánh ...) → cross-model
    multi_models = _distinct_models(query)
    if len(multi_models) >= 2:
        return {
            "decision": "answer",
            "reason_code": "sufficient_direct_evidence",
            "entities": {},
            "specificity": "clear",
            "category": "so_sánh",
            "allowed_tools": {"list_available_models", "get_price", "get_specs"},
            "model_codes": multi_models,
        }

    # "so sánh với VF 8 Plus" — keyword so sánh + 1 model trong query + model context KHÁC → cross-model.
    # (Không nhầm với version-pair "so sánh vf8 eco và plus" — có 2 version thì đi phiên_bản, không vào đây.)
    if _CROSS_MODEL_RE.search(query) and query_has_model and len(_distinct_versions(query)) < 2:
        q_model = cr.entities.get("model_code")
        hist_model = hist_ctx.get("model_code")
        if hist_model and hist_model != q_model:
            return {
                "decision": "answer",
                "reason_code": "sufficient_direct_evidence",
                "entities": {},
                "specificity": "clear",
                "category": "so_sánh",
                "allowed_tools": {"list_available_models", "get_price", "get_specs"},
                "model_codes": [hist_model, q_model],
            }

    # Follow-up to a multi-model comparison (e.g. "vậy giá thì sao" after
    # "so sánh VF 8 và VF 9") — query has no model but history had 2+ models.
    # Only trigger if the most recent model context is still one of the comparison
    # models. If user moved to a different model ("tôi muốn biết về VF5"), the
    # comparison context is stale — don't force so_sánh.
    hist_models = hist_ctx.get("models", [])
    recent_model = hist_ctx.get("model_code")
    if not query_has_model and len(hist_models) >= 2 and (not recent_model or recent_model in hist_models):
        return {
            "decision": "answer",
            "reason_code": "sufficient_direct_evidence",
            "entities": {},
            "specificity": "clear",
            "category": "so_sánh",
            "allowed_tools": {"list_available_models", "get_price", "get_specs"},
            "model_codes": hist_models,
        }

    # Cross-model FEATURE queries ("xe nào có cửa sổ trời", "những xe nào có ghế massage",
    # "dòng nào có camera 360") — user không biết model nào có tính năng →
    # KHÔNG clarify thiếu model, scan TẤT CẢ model chính và trả lời luôn.
    # Đặt TRƯỚC merge history model: có model từ turn trước vẫn là câu hỏi cross-model mới.
    if not query_has_model and _CROSS_MODEL_FEATURE_RE.search(query):
        cross_topic = _classify_topic(query)
        return {
            "decision": "answer",
            "reason_code": "sufficient_direct_evidence",
            "entities": {},
            "specificity": "unclear",
            "category": cross_topic if cross_topic != "general" else "tính_năng_nổi_bật",
            "allowed_tools": {"get_specs", "search_knowledge_base"},
            "model_codes": list(MAIN_MODELS),
        }

    if not has_model:
        if _AMBIGUOUS_PRONOUN_RE.search(query):
            return {
                "decision": "clarify",
                "reason_code": "ambiguous_context",
                "response_text": "Bạn muốn hỏi về xe nào?",
                "entities": cr.entities,
                "specificity": "unclear",
                "category": topic,
            }
        # Cross-model queries (xe nào rẻ nhất, giá dưới 600 triệu, nên mua...)
        # → answer with tools that work across all models
        if _CROSS_MODEL_RE.search(query):
            cross_tools = {"list_available_models", "get_price", "get_specs"}
            return {
                "decision": "answer",
                "reason_code": "sufficient_direct_evidence",
                "entities": cr.entities,
                "specificity": "unclear",
                "category": topic if topic != "general" else "giá",
                "allowed_tools": cross_tools,
            }
        if topic != "general":
            return {
                "decision": "clarify",
                "reason_code": "missing_model",
                "response_text": "Bạn muốn hỏi về xe VinFast nào?",
                "entities": cr.entities,
                "specificity": "unclear",
                "category": topic,
            }
        # No model AND no recognized VinFast topic
        if topic == "general":
            # If query mentions cars/VinFast → clarify (ask which model)
            if _CAR_RELATED_RE.search(query):
                return {
                    "decision": "clarify",
                    "reason_code": "missing_model",
                    "response_text": "Bạn muốn hỏi về xe VinFast nào?",
                    "entities": cr.entities,
                    "specificity": "unclear",
                    "category": "general",
                }
            # Otherwise truly out of scope (e.g. weather, cooking, sports)
            return {
                "decision": "out_of_scope",
                "reason_code": "unsupported_topic",
                "response_text": "Hiện tại mình chỉ hỗ trợ tư vấn thông tin sản phẩm xe VinFast. Bạn có thể hỏi về thông số, tính năng, pin/sạc, phạm vi di chuyển của xe.",
                "entities": cr.entities,
                "specificity": "unclear",
                "category": "general",
            }

    # Broad/intro topic (model known, topic vague, NOT a follow-up)
    # "giới thiệu về X", "cho tôi biết về X" → trả lời thông tin cơ bản luôn, không hỏi lại.
    if has_model and topic == "general" and _is_broad_topic(query) and not is_followup:
        return {
            "decision": "answer",
            "reason_code": "sufficient_direct_evidence",
            "entities": cr.entities,
            "specificity": "unclear",
            "category": "tổng_quan",
            "allowed_tools": {"list_available_models", "get_price", "get_specs", "get_colors"},
        }

    # Missing version (only for version-dependent topics).
    # Query tự nêu model + KHÔNG nêu version → câu hỏi "mới": làm rõ phiên bản lại,
    # KHÔNG kế thừa version từ turn trước (tránh leak cache của VF 8 Plus khi user
    # hỏi lại "VF 8 đi được bao nhiêu km").
    if not VERSION_QUERY_RE.search(query) and topic in _VERSION_DEPENDENT_TOPICS:
        missing_version = (query_has_model and not query_has_version) or (has_model and not has_version)
        if missing_version:
            model = cr.entities["model_code"]
            return {
                "decision": "clarify",
                "reason_code": "missing_version",
                "response_text": f"Bạn muốn hỏi phiên bản nào của {model}?",
                "entities": cr.entities,
                "specificity": "unclear",
                "category": topic,
            }

    # Out-of-scope guard: chỉ OOS khi KHÔNG có chút context xe nào (query lẫn history).
    # Query follow-up ("các thông tin khác thì sao") có model ở history → giữ context, không OOS.
    if raw_topic == "general" and not query_has_model and not query_has_version and not has_model:
        if not _CAR_RELATED_RE.search(query) and not _UTILITY_QUERY_RE.search(query):
            return {
                "decision": "out_of_scope",
                "reason_code": "unsupported_topic",
                "response_text": "Hiện tại mình chỉ hỗ trợ tư vấn thông tin sản phẩm xe VinFast. Bạn có thể hỏi về thông số, tính năng, pin/sạc, phạm vi di chuyển của xe.",
                "entities": cr.entities,
                "specificity": "unclear",
                "category": "general",
            }

    # Answer
    return {
        "decision": "answer",
        "reason_code": "sufficient_direct_evidence",
        "entities": cr.entities,
        "specificity": cr.specificity,
        "category": topic,
        "allowed_tools": _TOPIC_TOOLS.get(topic),
    }
