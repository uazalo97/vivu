import re
from dataclasses import dataclass, field


# Matches any VinFast model pattern (including multi-word like "VF 8 All New")
MODEL_RE = re.compile(
    r"(VF[-\s]*\d+(?:\s*All\s*New|\s*thế\s*hệ\s*mới)?|VF\s*MPV\s*\d+|VF\s*e34|"
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
    "plus awd": "Plus AWD",
    "plusawd": "Plus AWD",
}


@dataclass
class ClassifyResult:
    decision: str = "answer"
    reason: str = ""
    entities: dict = field(default_factory=dict)
    specificity: str = "unclear"


def _normalize_version(raw: str) -> str | None:
    clean = raw.strip().lower()
    return VERSION_ALIASES.get(clean)


def normalize_model(raw: str) -> str:
    """Chuẩn hóa model code về dạng DB: 'vf8' → 'VF 8', 'vf-8' → 'VF 8',
    'vf 8 all new' → 'VF 8 All New', 'vf8 thế hệ mới' → 'VF 8 All New'."""
    clean = re.sub(r"(VF)\s*[-]?\s*(\d+)", r"\1 \2", (raw or "").strip(), flags=re.IGNORECASE).strip()
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
        version_match = re.search(
            r"(Eco|Plus|PlusCaptain|Plus\s*AWD|"
            r"Ti[êe]u\s*[Cc]hu[ẩẩ]?n|TieuChuan|"
            r"N[ââ]ng\s*[Cc]ao|NangCao|"
            r"Cao\s*[Cc][ấấ]?p|CaoCap|"
            r"The\s*All\s*New|All\s*New)",
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
