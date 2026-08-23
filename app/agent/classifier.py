import re
from dataclasses import dataclass, field


# Matches any VinFast model pattern (including multi-word like "VF 8 All New")
MODEL_RE = re.compile(
    r"(VF[-\s]*\d+(?:\s*All\s*New|\s*thế\s*hệ\s*mới|\s*new(?:\s*20\d{2})?)?|VF\s*MPV\s*\d+|VF\s*e34|"
    r"Herio\s*Green|Minio\s*Green|Limo\s*Green|EC\s*VAN|Nerio\s*Green)",
    re.IGNORECASE,
)

VERSION_ALIASES = {
    "eco": "Eco",
    "bản eco": "Eco",
    "ban eco": "Eco",
    "plus": "Plus",
    "bản plus": "Plus",
    "ban plus": "Plus",
    # VF 7 AWD editions — map thẳng về edition_id trong DB (có underscore)
    "plus awd": "Plus_AWD",
    "plusawd": "Plus_AWD",
    "awd": "Plus_AWD",
    "hai cầu": "Plus_AWD",
    "hai cau": "Plus_AWD",
    "2 cầu": "Plus_AWD",
    "2 cau": "Plus_AWD",
    "plus awd panoramic roof": "Plus_AWD_PanoramicRoof",
    "plus awd trần kính": "Plus_AWD_PanoramicRoof",
    "plus awd kính toàn cảnh": "Plus_AWD_PanoramicRoof",
    "plus awd toàn cảnh": "Plus_AWD_PanoramicRoof",
    "hai cầu trần kính": "Plus_AWD_PanoramicRoof",
    "hai cầu kính toàn cảnh": "Plus_AWD_PanoramicRoof",
    "hai cầu toàn cảnh": "Plus_AWD_PanoramicRoof",
    "2 cầu trần kính": "Plus_AWD_PanoramicRoof",
    "awd trần kính": "Plus_AWD_PanoramicRoof",
    "awd kính toàn cảnh": "Plus_AWD_PanoramicRoof",
    "tiêu chuẩn": "TieuChuan",
    "tieuchuan": "TieuChuan",
    "tiêu_chuẩn": "TieuChuan",
    "nâng cao": "NangCao",
    "nangcao": "NangCao",
    "cao cấp": "CaoCap",
    "caocap": "CaoCap",
    "pluscaptain": "PlusCaptain",
    "plus captain": "PlusCaptain",
    "the all new": "The All New",
    "all new": "The All New",
    "thenew": "The All New",
}


@dataclass
class ClassifyResult:
    decision: str = "answer"
    reason: str = ""
    entities: dict = field(default_factory=dict)
    specificity: str = "unclear"


def _normalize_version(raw: str) -> str | None:
    clean = (raw or "").strip().lower()
    if clean in VERSION_ALIASES:
        return VERSION_ALIASES[clean]
    # Fuzzy AWD fallback: bắt mọi cách nói biến thể của VF 7 hai cầu
    # ("plus awd thêm kính", "hai cầu cửa sổ trời toàn cảnh"…) → edition DB.
    if re.search(r"(awd|hai\s*c[ầa]u|2\s*c[ầa]u)", clean):
        if re.search(r"(panoramic|c[ửu]a\s*s[ổo]\s*tr[ờo]i|tr[ầa]n\s*k[íi]nh|to[àa]n\s*c[ảa]nh)", clean):
            return "Plus_AWD_PanoramicRoof"
        return "Plus_AWD"
    return None


def normalize_model(raw: str) -> str:
    """Chuẩn hóa model code về dạng DB: 'vf8' → 'VF 8', 'vf-8' → 'VF 8',
    'vf 8 all new' → 'VF 8 All New', 'vf8 thế hệ mới'/'vf8 new 2026' → 'VF 8 All New'."""
    clean = re.sub(r"(VF)\s*[-]?\s*(\d+)", r"\1 \2", (raw or "").strip(), flags=re.IGNORECASE).strip()
    # 'new' / 'new 2026' → 'All New'; giữ nguyên 'All New' sẵn có (không nhân đôi)
    if re.search(r"all\s*new", clean, re.IGNORECASE):
        clean = re.sub(r"(all)\s*new(?:\s*20\d{2})?", r"\1 New", clean, flags=re.IGNORECASE)
    else:
        clean = re.sub(r"\bnew(?:\s*20\d{2})?\b", "All New", clean, flags=re.IGNORECASE)
    # Normalize "thế hệ mới" → "All New"
    clean = re.sub(r"thế\s*hệ\s*mới", "All New", clean, flags=re.IGNORECASE)
    parts = clean.split()
    return " ".join(p.upper() if p.upper().startswith("VF") or p.isdigit() else p.capitalize() for p in parts)


class QueryClassifier:
    """Detect model + version from query. No OOS gating — all models supported."""

    def _detect_model(self, query: str) -> tuple[str | None, str | None]:
        m = MODEL_RE.search(query)
        if m:
            raw = m.group(1).strip()
            return normalize_model(raw), raw
        return None, None

    def classify(self, query: str, history: list[dict] = None) -> ClassifyResult:
        entities = {}

        normalized, raw = self._detect_model(query)
        if normalized:
            entities["model_code"] = normalized

        # Version detection — chạy trên query ĐÃ bỏ phần model match.
        # "vf8 all new" → 'All New' là một phần TÊN MODEL, không phải phiên bản;
        # nếu không bỏ sẽ set version='The All New' → get_price/get_specs lọc
        # edition không tồn tại → 0 rows → refuse oan.
        version_query = query.replace(raw, " ") if raw else query
        # Suffix tùy chọn cho AWD/hai cầu: "trần kính", "cửa sổ trời toàn cảnh"…
        # Trường hợp nối kiểu "thêm trần kính" được xử lý ở classify_node
        # (upgrade Plus_AWD → Plus_AWD_PanoramicRoof dựa trên full query).
        _roof_suffix = r"(?:\s*(?:Panoramic\s*Roof|c[ửu]a\s*s[ổo]\s*tr[ờo]i|tr[ầa]n\s*k[íi]nh|to[àa]n\s*c[ảa]nh|k[íi]nh\s*to[àa]n\s*c[ảa]nh))?"
        version_match = re.search(
            r"(PlusCaptain"
            rf"|Plus\s+(?:hai\s*c[ầa]u|\bAWD\b){_roof_suffix}"
            r"|Plus\s*AWD"
            rf"|(?:Hai\s*c[ầa]u|2\s*c[ầa]u|\bAWD\b){_roof_suffix}"
            r"|Ti[êe]u\s*[Cc]hu[ẩẩ]?n|TieuChuan"
            r"|N[ââ]ng\s*[Cc]ao|NangCao"
            r"|Cao\s*[Cc][ấấ]?p|CaoCap"
            r"|The\s*All\s*New|All\s*New"
            r"|Eco|Plus)",
            version_query,
            re.IGNORECASE,
        )
        if version_match:
            nv = _normalize_version(version_match.group(1))
            if nv:
                entities["version"] = nv

        has_model = "model_code" in entities
        specificity = "clear" if has_model else "unclear"

        return ClassifyResult(
            decision="answer",
            reason="proceed to retrieval",
            entities=entities,
            specificity=specificity,
        )


_classifier = None


def get_classifier() -> QueryClassifier:
    global _classifier
    if _classifier is None:
        _classifier = QueryClassifier()
    return _classifier
