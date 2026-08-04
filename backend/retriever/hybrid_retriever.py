#!/usr/bin/env python3
"""
hybrid_retriever.py — Retriever hoàn chỉnh cho UC-01 (OpenRouter).

Luồng:
  1. Entity detection: model_id / edition_id từ query (regex)
  2. Chọn collection theo intent
  3. Dense search  (OpenRouter text-embedding-3-small, 4 dense collections)
     Sparse search (BM25, collection 'sparse')
  4. RRF fusion
  5. Rerank bằng OpenRouter cohere/rerank-v3.5
  6. Filter model/edition + join text từ vector/*.jsonl
  7. Giá từ Postgres — qua TOOL REGISTRY (deterministic fast-path,
     sẵn sàng mở cho LLM function-calling sau này)
  8. Ghép context + prompt LLM + link brochure

Usage:
    python scripts/retriever/hybrid_retriever.py "VF 9 Plus giá bao nhiêu và có ADAS gì?"
    python scripts/retriever/hybrid_retriever.py "bảo hành pin xe điện" --top-k 5
    python scripts/retriever/hybrid_retriever.py "trễ hạn phí thuê pin" --no-rerank
"""

import argparse
import json
import re
import sys
import time
import unicodedata
import uuid
from pathlib import Path

import psycopg2
from qdrant_client import QdrantClient
from qdrant_client.models import (FieldCondition, Filter, MatchValue,
                                  SparseVector)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openrouter import (API_KEY, CHAT_MODEL, EMBED_MODEL,
                            chat_completion, chat_completion_stream,
                            embed_text, summarize_metrics)  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CLEAN_DIR = REPO_ROOT / "data" / "clean" / "{version}"

QDRANT_URL = "http://localhost:6333"
PG_DSN = "postgresql://vivu:vivu@localhost:5432/vivu"

COLLECTIONS = ["vivu_specs", "vivu_product_info", "vivu_policy", "vivu_maintenance"]
SPARSE_COLLECTION = "sparse"
SPARSE_INDEX_FILE = CLEAN_DIR / "sparse_index.json"

# ── Maintenance tool ───────────────────────────────────────────────────────
# Câu hỏi về bảo dưỡng: gọi tool `get_maintenance_info` → lịch bảo dưỡng CHUNG
# + link chính thức, KHÔNG tra vector theo từng dòng xe (bảng trong
# `vivu_maintenance` rất dễ bị LLM tóm tắt sai — ví dụ "10 năm hoặc 150.000 km"
# là chu kỳ cuối bảng VF3, không phải lịch chung). Fast-path cũng tránh được
# lỗi khi Qdrant chưa chạy.
MAINTENANCE_URL = "https://vinfastauto.com/vn_vi/dich-vu-bao-duong-oto"

# ── Tokenizer (khớp sparse_ingest.py) ──────────────────────────────────────
STOPWORDS = set("""
của và có là trong với cho khi từ không những các một được sẽ đã đang này đó thì
để về ra theo tại cũng như nên vào đến nhưng bởi vì hay hoặc gì rất hơn hết cả đều
sau trước mới lại còn phải bị do qua lên xuống ngay chỉ mà nữa đây ấy nào bao nhiêu
mình bạn tôi nó họ chúng ta ông bà anh chị em cùng thôi cần nếu đúng xin quý
""".split())
TOKEN_RE = re.compile(r"[a-zà-ỹ0-9]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and len(t) > 1]


# ── Entity detection ───────────────────────────────────────────────────────
MODEL_PATTERNS = [
    (re.compile(r"\bvf\s*(?:mpv\s*7|mpv7)\b", re.I), "VFMPV7"),
    (re.compile(r"\bvf\s*e\s*34\b|\be34\b", re.I), "VFE34"),
    (re.compile(r"\bvf\s*(9|8|7|6|5|3|2)\b", re.I), None),
]
EDITION_PATTERNS = [
    (re.compile(r"\bplus\s*captain\b", re.I), "PlusCaptain"),
    (re.compile(r"\bplus\b", re.I), "Plus"),
    (re.compile(r"\beco\b", re.I), "Eco"),
    (re.compile(r"\btiêu\s*chuẩn\b|\btieu\s*chuan\b", re.I), "TieuChuan"),
    (re.compile(r"\bnâng\s*cao\b|\bnang\s*cao\b", re.I), "NangCao"),
    (re.compile(r"\bcao\s*cấp\b|\bcao\s*cap\b", re.I), "CaoCap"),
]


def detect_entities(query: str) -> tuple[str | None, str | None]:
    model = None
    for pat, m in MODEL_PATTERNS:
        mm = pat.search(query)
        if mm:
            model = m if m else f"VF{mm.group(1)}"
            break
    edition = None
    for pat, e in EDITION_PATTERNS:
        if pat.search(query):
            edition = e
            break
    return model, edition


# ── Intent → collection ────────────────────────────────────────────────────
INTENT_COLLECTIONS = [
    (["thông số", "thong so", "kích thước", "kich thuoc", "công suất", "cong suat",
      "mô men", "mo men", "động cơ", "dong co", "pin", "adas", "an toàn", "an toan",
      "spec", "lazang", "la-zang", "phanh", "treo", "nhiên liệu", "nhien lieu", "kwh"],
     "vivu_specs"),
    (["bảo dưỡng", "bao duong", "định kỳ", "dinh ky", "bảo trì", "bao tri",
      "hạng mục", "hang muc", "lịch bảo dưỡng"],
     "vivu_maintenance"),
    (["bảo hành", "bao hanh", "chính sách", "chinh sach", "thuê pin", "thue pin",
      "điều khoản", "dieu khoan", "dịch vụ", "dich vu", "khiếu nại", "khieu nai",
      "cứu hộ", "cuu ho", "sửa chữa", "sua chua", "trễ hạn", "tre han", "phí", "phi"],
     "vivu_policy"),
    (["giá", "gia", "niêm yết", "niem yet", "ưu đãi", "uu dai", "khuyến mãi",
      "khuyen mai", "đặt cọc", "dat coc", "lăn bánh", "lan banh", "màu", "mau sac",
      "tính năng", "tinh nang", "thiết kế", "thiet ke", "nội thất", "noi that",
      "ngoại thất", "ngoai that", "mô tả", "mo ta"],
     "vivu_product_info"),
]


def match_intents(query: str) -> list[str]:
    """Trả danh sách collection khớp intent theo keyword (rỗng nếu không khớp)."""
    q = unicodedata.normalize("NFC", query).lower()
    return [col for kws, col in INTENT_COLLECTIONS if any(k in q for k in kws)]


def select_collections(query: str) -> list[str]:
    return list(dict.fromkeys(match_intents(query))) or COLLECTIONS


# ── Sparse index ───────────────────────────────────────────────────────────
def load_sparse_index(version: str) -> dict:
    p = Path(str(SPARSE_INDEX_FILE).format(version=version))
    if not p.exists():
        print(f"[retriever] sparse index not found: {p}", file=sys.stderr)
        print("  hint: python scripts/ingest/sparse_ingest.py --version <ver>", file=sys.stderr)
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def encode_query_sparse(query: str, index: dict) -> SparseVector:
    vocab = index["vocab"]
    idf = index["idf"]
    tf: dict[str, int] = {}
    for t in tokenize(query):
        if t in vocab:
            tf[t] = tf.get(t, 0) + 1
    indices: list[int] = []
    values: list[float] = []
    for t, f in tf.items():
        indices.append(vocab[t])
        values.append(round(idf[vocab[t]] * f, 6))
    order = sorted(range(len(indices)), key=lambda i: indices[i])
    return SparseVector(indices=[indices[i] for i in order],
                        values=[values[i] for i in order])


# ── Text join map ──────────────────────────────────────────────────────────
def build_text_map(version: str) -> dict[str, dict]:
    ns = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    m: dict[str, dict] = {}
    vdir = Path(str(CLEAN_DIR).format(version=version)) / "vector"
    for f in sorted(vdir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                m[str(uuid.uuid5(ns, c["id"]))] = c
    return m


# ── RRF fusion ─────────────────────────────────────────────────────────────
def rrf_merge(scored_lists: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for lst in scored_lists:
        for rank, (cid, _s) in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


# ── Tool Registry (deterministic fast-path; sẵn sàng cho LLM function-calling) ─
TOOL_REGISTRY: dict[str, dict] = {}


def register_tool(name: str, description: str, parameters: dict, handler) -> None:
    TOOL_REGISTRY[name] = {
        "name": name, "description": description,
        "parameters": parameters, "handler": handler,
    }


def get_price(model: str, edition: str | None = None) -> dict | None:
    """Lấy giá niêm yết + ưu đãi hiện hành của model (edition nếu có)."""
    if not model:
        return None
    try:
        conn = psycopg2.connect(PG_DSN)
        cur = conn.cursor()
        sql = """SELECT price_list_vnd, price_promo_vnd, promo_label, valid_from, source_url, updated_at
                 FROM price_list
                 WHERE model_id=%s {ed}
                   AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
                 ORDER BY valid_from DESC LIMIT 1"""
        args = [model]
        if edition:
            sql = sql.format(ed="AND edition_id=%s")
            args.append(edition)
        else:
            sql = sql.format(ed="")
        cur.execute(sql, args)
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        cols = ["price_list_vnd", "price_promo_vnd", "promo_label", "valid_from", "source_url", "updated_at"]
        return dict(zip(cols, row))
    except Exception as e:
        print(f"  (get_price error: {e})", file=sys.stderr)
        return None


register_tool(
    "get_price",
    "Lấy giá niêm yết và giá ưu đãi hiện hành của một mẫu xe (model) và phiên bản (edition).",
    {"model": {"type": "string"}, "edition": {"type": "string", "optional": True}},
    get_price,
)


def get_maintenance_info(model: str | None = None) -> dict:
    """Tool: lịch bảo dưỡng CHUNG + link trang bảo dưỡng chính thức của VinFast.

    Cố ý KHÔNG trả bảng chi tiết theo từng dòng xe — lịch chung + link để user
    tự tra cứu theo xe, tránh LLM tóm tắt sai chu kỳ.
    """
    return {
        "model": model,
        "summary": (
            "Bảo dưỡng định kỳ giúp duy trì trạng thái ổn định, kéo dài tuổi thọ "
            "các chi tiết và phát hiện sớm hư hỏng; đây cũng là điều kiện cần để "
            "được hưởng chính sách bảo hành. Lịch bảo dưỡng được quy định bằng "
            "quãng đường di chuyển (km) hoặc thời gian theo tháng — tùy điều kiện "
            "nào đến trước. Tần suất và hạng mục kiểm tra/thay thế cụ thể khác "
            "nhau theo từng dòng xe."
        ),
        "url": MAINTENANCE_URL,
    }


register_tool(
    "get_maintenance_info",
    "Lấy lịch bảo dưỡng chung và link trang bảo dưỡng chính thức của VinFast "
    "(không đi vào chi tiết theo từng dòng xe).",
    {"model": {"type": "string", "optional": True}},
    get_maintenance_info,
)


# ── Model list tool ────────────────────────────────────────────────────────
# Câu hỏi kiểu "VinFast có mấy loại xe?" / "liệt kê các dòng xe" → trả danh
# mục dòng xe deterministic từ KB (KHÔNG tra vector — trước đây lôi 1 chunk
# trang thứ ba, LLM liệt kê thiếu và gán nguồn sai).
MODEL_CATALOG: list[dict[str, str]] = [
    {"id": "VF2", "label": "VF 2"},
    {"id": "VF3", "label": "VF 3"},
    {"id": "VF5", "label": "VF 5"},
    {"id": "VF6", "label": "VF 6"},
    {"id": "VF7", "label": "VF 7"},
    {"id": "VF8", "label": "VF 8"},
    {"id": "VF9", "label": "VF 9"},
    {"id": "VFE34", "label": "VF e34"},
    {"id": "VFMPV7", "label": "VF MPV 7"},
]
MODEL_LIST_KEYWORDS = [
    "có mấy loại xe", "may loai xe",
    "bao nhiêu loại xe", "bao nhieu loai xe",
    "có mấy dòng xe", "may dong xe",
    "bao nhiêu dòng xe", "bao nhieu dong xe",
    "danh sách xe", "danh sach xe",
    "danh sách dòng xe", "danh sach dong xe",
    "những loại xe", "nhung loai xe",
    "những dòng xe", "nhung dong xe",
    "có những xe gì", "co nhung xe gi",
    "những xe gì", "nhung xe gi",
]


def is_model_list_intent(query: str) -> bool:
    q = unicodedata.normalize("NFC", query).lower()
    return any(k in q for k in MODEL_LIST_KEYWORDS)


def get_model_list() -> dict:
    """Tool: danh mục dòng xe VinFast có trong KB (id + label + count)."""
    return {
        "count": len(MODEL_CATALOG),
        "models": [m["label"] for m in MODEL_CATALOG],
    }


register_tool(
    "get_model_list",
    "Lấy danh mục đầy đủ các dòng xe VinFast có trong cơ sở tri thức.",
    {},
    get_model_list,
)


# ── Brochure ─────────────────────────────────────────────────────────────
# Mapping model_id → URLs lưu trong `_manifest.json` dưới key
# `link_only.brochure_by_model` (do `scripts/clean_data/clean_to_jsonl.py` sinh
# từ `data/raw/link_brochure.md` — mỗi dòng có format `<url> (<model_label>)`
# với label ∈ {vf2, vf3, vf5, vf6, vf7, vf8, vf8-the-new, vf9}).
#
# Fallback thứ tự:
#   1. `link_only.brochure_by_model` trong manifest (ưu tiên, có phân loại)
#   2. `data/raw/link_brochure.md` (parse label ở runtime)
#   3. `link_only.brochure_urls` (danh sách phẳng cũ, trả tất cả khi không
#      detect được model)
LINK_BROCHURE_FILE = REPO_ROOT / "data" / "raw" / "link_brochure.md"
_BROCHURE_LABEL_RE = re.compile(r"\(([a-z0-9\-]+)\)\s*$", re.I)
_LABEL_TO_MODEL: dict[str, str] = {
    "vf2": "VF2", "vf3": "VF3", "vf5": "VF5", "vf6": "VF6",
    "vf7": "VF7", "vf8": "VF8", "vf8-the-new": "VF8",
    "vf9": "VF9",
}


def _parse_link_brochure_file(path: Path) -> dict[str, list[str]]:
    """Đọc `data/raw/link_brochure.md` → {model_id: [urls]} (giữ thứ tự xuất hiện)."""
    out: dict[str, list[str]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _BROCHURE_LABEL_RE.search(line)
        if not m:
            continue
        model = _LABEL_TO_MODEL.get(m.group(1).lower())
        if not model:
            continue
        url = line[: m.start()].strip()
        if url:
            out.setdefault(model, []).append(url)
    return out


def _flatten_by_model(by_model: dict[str, list[str]]) -> list[str]:
    """Gộp dict model→urls thành list phẳng, giữ thứ tự, bỏ trùng."""
    seen: set[str] = set()
    out: list[str] = []
    for urls in by_model.values():
        for u in urls:
            if u not in seen:
                out.append(u)
                seen.add(u)
    return out


def load_brochure_urls(version: str, model: str | None = None) -> list[str]:
    """Trả URL brochure. Nếu `model` được detect (VF9, VF8, ...) → lọc chỉ trả
    brochure của model đó (1 link; hoặc 2 nếu model có cả bản cũ + "The hệ mới").

    Quy tắc trả về:
      - model = None  → trả toàn bộ (giữ thứ tự trong manifest)
      - model = "VF8" → trả cả 2 (bản cũ + "The hệ mới")
      - model khác    → trả URL cho model đó
      - không match   → fallback trả toàn bộ
    """
    mf = Path(str(CLEAN_DIR).format(version=version)) / "_manifest.json"
    by_model: dict[str, list[str]] = {}

    # 1) Ưu tiên manifest (nếu có brochure_by_model)
    if mf.exists():
        mj = json.loads(mf.read_text(encoding="utf-8"))
        by_model = mj.get("link_only", {}).get("brochure_by_model", {}) or {}

    # 2) Fallback parse file raw
    if not by_model:
        by_model = _parse_link_brochure_file(LINK_BROCHURE_FILE)

    if not by_model:
        # 3) Fallback cuối: danh sách phẳng cũ (chỉ trả khi không detect model)
        if not mf.exists():
            return []
        mj = json.loads(mf.read_text(encoding="utf-8"))
        urls = mj.get("link_only", {}).get("brochure_urls", [])
        return urls if not model else urls  # không có model_id → trả tất cả

    if not model:
        return _flatten_by_model(by_model)
    return by_model.get(model, []) or _flatten_by_model(by_model)


# ── LLM response (C5) ──────────────────────────────────────────────────────
def build_answer_messages(query: str, chunks: list[dict], price: dict | None,
                          brochures: list[str], maintenance: dict | None = None,
                          model_list: dict | None = None) -> list[dict]:
    """Ghép context (chunks + giá + bảo dưỡng + danh mục xe + brochure) → messages."""
    lines: list[str] = []
    if chunks:
        lines.append("THÔNG TIN TỪ CƠ SỞ TRI THỨC:")
        for c in chunks:
            src = c.get("source_url") or "N/A"
            sec = c["section_path"][-1] if c.get("section_path") else ""
            lines.append(f"[{c.get('collection')} | {c.get('model_id')} | {sec}]")
            lines.append(c["text"])
            lines.append(f"(nguồn: {src})")
    elif not maintenance and not model_list:
        # Không có chunk nào liên quan → nói thẳng cho LLM biết
        lines.append("(Không tìm thấy thông tin liên quan trong cơ sở tri thức.)")
    if model_list:
        lines.append("\nDANH MỤC DÒNG XE VINFAST:")
        lines.append(f"- Số lượng: {model_list['count']} dòng xe.")
        lines.append(f"- Danh sách: {', '.join(model_list['models'])}.")
    if maintenance:
        lines.append("\nTHÔNG TIN LỊCH BẢO DƯỠNG:")
        if maintenance.get("summary"):
            lines.append(f"- {maintenance['summary']}")
        if maintenance.get("url"):
            lines.append(f"- Tra cứu lịch bảo dưỡng chi tiết: {maintenance['url']}")
    if price:
        model_ed = " ".join(str(x) for x in [price.get("model_id"), price.get("edition_id")] if x)
        lines.append("\nGIÁ HIỆN HÀNH cho " + (model_ed or "xe này") + ":")
        if price.get("price_list_vnd"):
            lines.append(f"- Niêm yết: {price['price_list_vnd']:,} VNĐ")
        if price.get("price_promo_vnd"):
            lines.append(f"- Ưu đãi: {price['price_promo_vnd']:,} VNĐ ({price.get('promo_label', '')})".strip())
        lines.append(f"- (Giá này CHỈ áp dụng cho {model_ed}, không áp dụng cho phiên bản khác)")
    if brochures:
        lines.append("\nBROCHURE THAM KHẢO:")
        lines.extend(f"- {u}" for u in brochures[:3])

    system = (
        "Bạn là trợ lý tư vấn xe Vivu. Trả lời bằng tiếng Việt, tự nhiên, chi tiết, đầy đủ.\n"
        "Quy tắc:\n"
        "- Giá: CHỈ dùng số được cung cấp từ Postgres; nếu không có giá thì nói rõ 'chưa có giá hiện hành'.\n"
        "- Không bịa số liệu, thông số, tính năng không có trong context.\n"
        "- Kèm nguồn (source_url) nếu có.\n"
        "- Không đề cập 'context', 'Postgres' hay quá trình nội bộ."
        "- Luôn xưng hô là Trợ lý Vivu"
    )
    user = "\n".join(lines) + f"\n\nCâu hỏi: \"{query}\""
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def generate_answer(query: str, chunks: list[dict], price: dict | None,
                    brochures: list[str], model: str = CHAT_MODEL,
                    maintenance: dict | None = None,
                    model_list: dict | None = None) -> str:
    """OpenRouter chat → câu trả lời đầy đủ (CLI)."""
    return chat_completion(
        build_answer_messages(query, chunks, price, brochures, maintenance, model_list),
        model=model)


def generate_answer_stream(query: str, chunks: list[dict], price: dict | None,
                           brochures: list[str], model: str = CHAT_MODEL,
                           maintenance: dict | None = None,
                           model_list: dict | None = None):
    """Yield từng token câu trả lời (cho backend SSE)."""
    yield from chat_completion_stream(
        build_answer_messages(query, chunks, price, brochures, maintenance, model_list),
        model=model)


# ── Core retrieval (module API cho backend) ────────────────────────────────
STAGE_LABELS = {
    "detect": "Phân tích câu hỏi",
    "search": "Tìm kiếm tài liệu liên quan",
    "price": "Tra cứu giá hiện hành",
    "answer": "Tổng hợp câu trả lời",
}


def retrieve(query: str, version: str = "v1", top_k: int = 3,
             per_collection: int = 10, no_sparse: bool = False,
             no_dense: bool = False, on_stage=None) -> dict:
    """Chạy entity→dense→sparse→RRF→price→brochure (KHÔNG rerank).

    on_stage(key) được gọi ở mỗi bước (key ∈ detect/search/price).
    Trả dict: {query, detected, collections, chunks, price, brochures,
               maintenance, model_list}.
    - Intent bảo dưỡng → `maintenance` (tool get_maintenance_info), chunks rỗng.
    - Hỏi danh mục dòng xe → `model_list` (tool get_model_list), chunks rỗng.
    - Các intent khác → chunks từ Qdrant + `price`/`brochures` như thường.
    """
    model, edition = detect_entities(query)
    intents = match_intents(query)
    cols = intents or COLLECTIONS
    if on_stage:
        on_stage("detect")

    # "VinFast có mấy loại xe?" → danh mục dòng xe deterministic (tool).
    if is_model_list_intent(query) and not model:
        if on_stage:
            on_stage("search")
            on_stage("price")
        return {
            "query": query,
            "detected": {"model": None, "edition": None},
            "collections": [],
            "chunks": [],
            "model_list": get_model_list(),
            "maintenance": None,
            "price": None,
            "brochures": [],
            "scores": {},
            "model_list_fast_path": True,
        }

    # Bảo dưỡng: gọi tool `get_maintenance_info` (lịch chung + link chính thức),
    # không tra vector theo từng xe.
    if "vivu_maintenance" in intents:
        if on_stage:
            on_stage("search")
            on_stage("price")
        return {
            "query": query,
            "detected": {"model": model, "edition": edition},
            "collections": ["vivu_maintenance"],
            "chunks": [],
            "maintenance": get_maintenance_info(model),
            "model_list": None,
            "price": None,
            "brochures": [],
            "scores": {},
            "maintenance_fast_path": True,
        }

    index = load_sparse_index(version)
    text_map = build_text_map(version)
    client = QdrantClient(url=QDRANT_URL)
    model_filter = None
    if model:
        model_filter = Filter(must=[FieldCondition(key="model_id", match=MatchValue(value=model))])

    if on_stage:
        on_stage("search")

    def _run_dense() -> list[list[tuple[str, float]]]:
        if no_dense:
            return []
        q_vec = embed_text(query)
        out: list[list[tuple[str, float]]] = []
        for col in cols:
            res = client.query_points(collection_name=col, query=q_vec,
                                      limit=per_collection, query_filter=model_filter,
                                      with_payload=True)
            out.append([(str(h.id), h.score) for h in res.points])
        return out

    def _run_sparse() -> list[tuple[str, float]]:
        if no_sparse:
            return []
        q_sparse = encode_query_sparse(query, index)
        sres = client.query_points(collection_name=SPARSE_COLLECTION, query=q_sparse,
                                   using="sparse", limit=per_collection * len(cols),
                                   query_filter=model_filter, with_payload=True)
        ns = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
        return [(str(uuid.uuid5(ns, h.payload["chunk_id"])), h.score) for h in sres.points]

    # ── Dense: embed rồi query tuần tự các collection ─────────────────────
    # Lưu ý: KHÔNG chạy song song dense/sparse trong thread riêng — trên Windows
    # `requests.Session` + `urllib3` connection pool bị race condition khi mở
    # socket từ nhiều thread cùng lúc, gây `[Errno 22] Invalid argument`.
    # Chạy tuần tự: dense trước (gọi OpenRouter), rồi sparse (local Qdrant).
    dense_lists = _run_dense()
    sparse_res = _run_sparse()
    sparse_lists = [sparse_res] if sparse_res else []

    # ── RRF fusion → top_k (không rerank) ────────────────────────────────
    merged = [m for m in rrf_merge(dense_lists + sparse_lists) if m[0] in text_map]
    rrf_score = {cid: s for cid, s in merged}
    ordered = merged[: top_k]

    if on_stage:
        on_stage("price")
    price = get_price(model, edition) if model else None
    if price:
        # Gắn model/edition để prompt biết giá thuộc edition nào (tránh LLM suy diễn sai)
        price = {**price, "model_id": model, "edition_id": edition}
    brochures = load_brochure_urls(version, model=model)

    chunks = [{**text_map[cid], "score": round(rscore, 4)} for cid, rscore in ordered[: top_k]]
    return {
        "query": query,
        "detected": {"model": model, "edition": edition},
        "collections": cols,
        "chunks": chunks,
        "maintenance": None,
        "model_list": None,
        "price": price,
        "brochures": brochures,
        "scores": rrf_score,
    }


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid retriever (dense + BM25 + RRF + rerank).")
    ap.add_argument("query", help="Câu hỏi user")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--top-k", type=int, default=3, help="Số chunk cuối (mặc định 3)")
    ap.add_argument("--per-collection", type=int, default=10, help="Kết quả mỗi nguồn trước fusion")
    ap.add_argument("--no-sparse", action="store_true", help="Chỉ dùng dense")
    ap.add_argument("--no-dense", action="store_true", help="Chỉ dùng sparse")
    ap.add_argument("--answer", action="store_true", help="Gọi LLM sinh câu trả lời cuối (C5)")
    ap.add_argument("--chat-model", default=CHAT_MODEL, help="Chat model (mặc định từ env)")
    args = ap.parse_args()

    if not API_KEY:
        print("[retriever] OPENROUTER_API_KEY chưa set trong .env", file=sys.stderr)
        return 1

    # Timing stages: ghi start-time mỗi stage, duration = start(stage sau) - start(stage)
    t_start = time.time()
    stage_start: dict[str, float] = {}
    stage_order: list[str] = []

    def on_stage(key: str) -> None:
        stage_start[key] = time.time()
        stage_order.append(key)

    result = retrieve(args.query, args.version, args.top_k, args.per_collection,
                      args.no_sparse, args.no_dense, on_stage=on_stage)
    query = args.query
    model, edition = result["detected"]["model"], result["detected"]["edition"]
    print(f"QUERY : {query}")
    print(f"DETECT: model={model}  edition={edition}")
    print(f"COLL  : {result['collections']}")

    # ── Output context ──────────────────────────────────────────────────
    print(f"\n=== TOP {len(result['chunks'])} KẾT QUẢ ===")
    for c in result["chunks"]:
        print(f"  [score={c['score']:.3f}] {c['collection']} | {c.get('model_id')} | {c['section_path'][-1]}")
        print(f"      {c['text'][:150]!r}")

    # ── Giá ─────────────────────────────────────────────────────────────
    price = result["price"]
    if price:
        print(f"\n=== GIÁ (Postgres, tool=get_price) ===")
        print(f"  {model} {edition or ''}: niêm yết {price['price_list_vnd']:,} VNĐ"
              + (f", ưu đãi {price['price_promo_vnd']:,} VNĐ ({price['promo_label']})"
                 if price.get('price_promo_vnd') else ""))
        print(f"  nguồn: {price['source_url']}")

    # ── Brochure ────────────────────────────────────────────────────────
    brochures = result["brochures"]
    if brochures:
        print(f"\n=== BROCHURE (link-only) ===")
        for u in brochures[:3]:
            print(f"  {u}")

    # ── LLM response ────────────────────────────────────────────────────
    answer_start = time.time()
    if args.answer:
        print(f"\n=== CÂU TRẢ LỜI ({args.chat_model}) ===")
        print(generate_answer(query, result["chunks"], price, brochures, args.chat_model,
                              maintenance=result.get("maintenance"),
                              model_list=result.get("model_list")))
    t_end = time.time()

    # ── 9. Summary (latency + tokens) ───────────────────────────────────
    sm = summarize_metrics()
    print(f"\n=== TIMING & TOKENS ===")
    order = stage_order + ["answer"]
    for i, key in enumerate(order):
        start = stage_start.get(key, answer_start if key == "answer" else t_start)
        end = stage_start.get(order[i + 1], t_end) if i + 1 < len(order) else t_end
        print(f"  {STAGE_LABELS.get(key, key):<26} {(end - start) * 1000:>8.1f} ms")
    print(f"  {'TOTAL':<26} {(t_end - t_start) * 1000:>8.1f} ms")
    tot = sm["total"]
    print(f"  API: {tot['calls']} calls  {tot['latency_ms']/1000:.1f}s  "
          f"tokens in={tot['input_tokens']} out={tot['output_tokens']}")
    for op, acc in sm["by_op"].items():
        print(f"    {op}: {acc['calls']} calls  {acc['latency_ms']/1000:.1f}s  "
              f"in={acc['input_tokens']} out={acc['output_tokens']}")
    # TTFT chỉ hiển thị ở output (chat), 1 dòng duy nhất
    chat = sm["by_op"].get("chat")
    if chat and chat.get("ttft_calls"):
        avg_ttft = chat["ttft_ms"] / chat["ttft_calls"]
        print(f"  TTFT (chat, output): {avg_ttft:.0f} ms")

    return 0


if __name__ == "__main__":
    sys.exit(main())
