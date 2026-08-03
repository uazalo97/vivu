#!/usr/bin/env python3
"""
clean_to_jsonl.py — Clean markdown raw data + model_specs.json into an
intermediate JSONL that follows the UC-01 data-format contract.

Output: data/clean/<version>/intermediate/<collection>.jsonl
Each line = one chunk with schema:
  {
    "id", "collection", "vector_version", "model_id", "edition_id",
    "category", "section_path", "text", "text_type", "structured",
    "language", "tags", "confidence", "source_file", "source_url",
    "source_type", "fetched_at", "ingested_at", "is_hot"
  }

is_hot = True for price rows later extracted to Postgres; these rows are kept
in a separate intermediate bucket so split_cold_hot.py can emit them as CSV.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"

# ── Canonical mappings ─────────────────────────────────────────────────────
MODEL_ID_MAP = {
    "Products-Car-ECVAN": "ECVAN",
    "Products-Car-FADIL": "FADIL",
    "Products-Car-HerioGreen": "HERIO",
    "Products-Car-LimoGreen": "LIMO",
    "Products-Car-LUX-A": "LUXA",
    "Products-Car-LUX-SA": "LUXSA",
    "Products-Car-MinioGreen": "MINIO",
    "Products-Car-NerioGreen": "NERIO",
    "Products-Car-VF2": "VF2",
    "Products-Car-VF3": "VF3",
    "Products-Car-VF5": "VF5",
    "Products-Car-VF6": "VF6",
    "Products-Car-VF7": "VF7",
    "Products-Car-VF8": "VF8",
    "Products-Car-VF9": "VF9",
    "Products-Car-VFMPV7": "VFMPV7",
    "Products-Car-MPV7": "VFMPV7",
}

EDITION_ID_MAP = {
    # VF9
    "NE3LV": "Eco",
    "NE3MV": "Plus",
    "NE3NV": "PlusCaptain",
    # VF8
    "ND42V": "Eco",
    "ND43V": "Plus",
    # VF7
    "JB10V": "Eco",
    "JB12V": "Plus",
    # VF6
    "JA10V": "Eco",
    "JA12V": "Plus",
    # VF5
    "GA12V": "Eco",
    "GA13V": "Plus",
    # VF3
    "GI10V": "TieuChuan",
    "GI11V": "Plus",
    "TI1CV": "Eco",
    "TI1BV": "Plus",
    # MPV7
    "MDS34": "Eco",
    "MDS35": "Plus",
    # EC VAN
    "TG10V": "TieuChuan",
    "TG11V": "NangCao",
    "TG12V": "CaoCap",
}

# Model label + default edition mapping used when emitting product info.
MODEL_LABEL = {
    "VF2": "VF 2",
    "VF3": "VF 3",
    "VF5": "VF 5",
    "VF6": "VF 6",
    "VF7": "VF 7",
    "VF8": "VF 8",
    "VF9": "VF 9",
    "VFMPV7": "VF MPV 7",
    "ECVAN": "EC Van",
    "FADIL": "Fadil",
    "HERIO": "Herio Green",
    "LIMO": "Limo Green",
    "LUXA": "LUX A",
    "LUXSA": "LUX SA",
    "MINIO": "Minio Green",
    "NERIO": "Nerio Green",
}

# When a markdown is specific to one model, infer from filename.
MODEL_FROM_FILENAME = {
    "vf2": "VF2",
    "vf3": "VF3",
    "vf5": "VF5",
    "vf6": "VF6",
    "vf7": "VF7",
    "vf8": "VF8",
    "vf8_2026": "VF8",
    "vf9": "VF9",
    "vf_mpv7": "VFMPV7",
    "vf_e34": "VFE34",
}

# Section-path tags used to route chunks into vector collections.
COLLECTION_BY_CATEGORY = {
    "thong_so_ky_thuat": "vivu_specs",
    "thong_tin_san_pham": "vivu_product_info",
    "ho_tro_mua_xe": "vivu_faq",
    "chinh_sach_dich_vu": "vivu_policy",
    "dat_lich_bao_duong": "vivu_maintenance",
}

CATEGORY_BY_DIR = {
    "01_thong_tin_san_pham": "thong_tin_san_pham",
    "02_thong_so_ky_thuat": "thong_so_ky_thuat",
    "03_chi_phi_lan_banh": "chi_phi_lan_banh",
    "04_ho_tro_mua_xe": "ho_tro_mua_xe",
    "05_chinh_sach_dich_vu": "chinh_sach_dich_vu",
    "06_showroom_tram_sac": "showroom_tram_sac",
    "07_khuyen_mai_uu_dai": "khuyen_mai_uu_dai",
    "08_dat_lich_bao_duong": "dat_lich_bao_duong",
}

# Heuristics to detect Vietnamese money strings in text.
MONEY_RE = re.compile(
    r"\b(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:\s*(?:triệu|tr|tỷ|nghìn|đồng|VNĐ|VND|\bđ\b))?",
    flags=re.IGNORECASE,
)
PRICE_KEYWORDS = [
    "giá bán", "giá niêm yết", "giá ưu đãi", "giá xe", "triệu đồng", "vnđ",
    "đặt cọc", "cọc", "lăn bánh",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_model_id(raw: str) -> str:
    return MODEL_ID_MAP.get(raw, raw.replace("Products-Car-", ""))


def to_edition_id(raw: str) -> str:
    return EDITION_ID_MAP.get(raw, raw)


def parse_price(value: Any) -> int | None:
    """Extract integer VND from a price string/number."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        s = value.strip().lower()
        # handle "1.280.600.000" or "1280600000"
        s = s.replace("vnđ", "").replace("vnd", "").replace("đ", "").replace(",", "").strip()
        if s == "" or s == "0":
            return None
        try:
            return int(float(s))
        except ValueError:
            # try after removing all non-digits
            digits = re.sub(r"[^0-9]", "", s)
            if digits:
                return int(digits)
    return None


def infer_model_from_path(path: Path) -> str | None:
    name = path.stem.lower()
    for key, model in MODEL_FROM_FILENAME.items():
        if key in name:
            return model
    # Try by directory semantic: 01 files always belong to a model filename
    return None


def extract_yaml_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse simple YAML frontmatter delimited by --- and return (meta, body)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            meta_text = parts[1].strip()
            body = parts[2].lstrip("\n")
            meta: dict[str, Any] = {}
            for line in meta_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"')
            return meta, body
    return {}, text


NOISE_PATTERNS = [
    r"^Đăng nhập\s*/\s*Đăng ký$",
    r"^VF\s+\d+\s+Hero\s+Background$",
    r"^\s*\(\*\)\s*Hình ảnh.*$",
    r"^\s*\(\*\*\)\s*.*phiên bản.*$",
    r"^\s*\(\*\*\*\)\s*.*$",
    r"^\s*\[.*\]\(.*\)\s*$",  # bare link lines
    r"^\s*!\[.*\]\(.*\)\s*$",  # bare image lines
    r"^\s*---\s*$",
    r"^\s*#+$",
]
NOISE_RE = [re.compile(p, flags=re.IGNORECASE) for p in NOISE_PATTERNS]


def strip_markdown_images(line: str) -> str:
    """Remove markdown image syntax ![alt](url), keep alt text if meaningful."""
    return re.sub(r"!\[([^\]]*)\]\([^)]+\)", lambda m: m.group(1) if m.group(1) else "", line)


def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def clean_line(line: str) -> str:
    line = strip_markdown_images(line)
    line = strip_html_tags(line)
    line = line.replace("&amp;", "&")
    line = line.replace("&nbsp;", " ")
    # Collapse whitespace
    line = re.sub(r"\s+", " ", line)
    line = line.strip()
    # Drop pure noise
    for pat in NOISE_RE:
        if pat.match(line):
            return ""
    return line


def remove_money_sentences(paragraphs: list[str]) -> list[str]:
    """Drop paragraphs that are dominated by price/deposit info."""
    cleaned = []
    # Strict money pattern: must have unit keyword
    money_re = re.compile(
        r"(?:\d{1,3}(?:[.,]\d{3})+|\d{6,})\s*(?:triệu|tr|tỷ|nghìn|đồng|VNĐ|VND|\bđ\b)|"
        r"(?:triệu|tr|tỷ|nghìn|đồng|VNĐ|VND|\bđ\b)\s*(?:\d{1,3}(?:[.,]\d{3})+|\d+)",
        flags=re.IGNORECASE,
    )
    for p in paragraphs:
        lowered = p.lower()
        has_price_kw = any(kw in lowered for kw in PRICE_KEYWORDS)
        money_hits = len(money_re.findall(p))
        # If paragraph mentions price words AND has a money number, drop it.
        if has_price_kw and money_hits >= 1:
            continue
        cleaned.append(p)
    return cleaned


def normalize_numbers(text: str) -> str:
    """Unify numeric formatting: '5.119 x 2.254' -> '5119 × 2254' only for dimension numbers."""
    # Replace 'x' / 'X' between dimension-like numbers with multiplication sign.
    text = re.sub(r"(\d{1,3}(?:[.,]\d{3}){1,2})\s*[xX×]\s*(\d{1,3}(?:[.,]\d{3}){1,2})\s*[xX×]?\s*(\d{1,3}(?:[.,]\d{3}){1,2})?",
                  lambda m: " × ".join(p.replace(".", "").replace(",", "") for p in m.groups() if p),
                  text)
    return text


def chunkify_markdown(path: Path, category: str, source_url: str = "") -> list[dict[str, Any]]:
    """
    Convert a markdown file into cleaned chunks.
    Returns list of dicts with intermediate schema (is_hot=False for vectors).
    """
    text = path.read_text(encoding="utf-8")
    meta, body = extract_yaml_frontmatter(text)
    source_url = source_url or meta.get("url", "")

    # Drop markdown internal notes (> ...)
    lines = []
    for line in body.splitlines():
        if line.strip().startswith(">"):
            # But keep source URLs noted in blockquote when useful
            continue
        cl = clean_line(line)
        if cl == "" or cl in {"---", "", "*", "#"}:
            continue
        lines.append(line)

    # Clean and group by headings
    chunks: list[dict[str, Any]] = []
    section_stack: list[tuple[int, str]] = []
    buf: list[str] = []
    
    def current_section_title():
        return section_stack[-1][1] if section_stack else ""

    def emit() -> None:
        if not buf:
            return
        paragraphs = [clean_line(line) for line in buf]
        paragraphs = [p for p in paragraphs if p]
        paragraphs = remove_money_sentences(paragraphs)
        if not paragraphs:
            buf.clear()
            return

        # Merge very short fragments (single words / orphan alt texts)
        merged = []
        carry = ""
        for p in paragraphs:
            if len(p) < 25 and not any(c in p for c in (".", ":", ";", "-", "|")):
                carry = (carry + " " + p).strip() if carry else p
            else:
                if carry:
                    merged.append(carry)
                    carry = ""
                merged.append(p)
        if carry:
            merged.append(carry)

        body_text = "\n\n".join(merged)
        body_text = normalize_numbers(body_text)
        if len(body_text) < 20:
            buf.clear()
            return

        model_id = infer_model_from_path(path)
        section_title = current_section_title()
        section_path = [CATEGORY_BY_DIR.get(path.parent.name, category)]
        if section_title:
            section_path.append(section_title)

        text_type = "prose"
        if "|" in body_text and "---" in body_text:
            text_type = "table"
        elif all(line.strip().startswith(("- ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ", "9. ")) for line in body_text.splitlines() if line.strip()):
            text_type = "list"
        elif "Q:" in body_text and "A:" in body_text:
            text_type = "qa_pair"

        collection = COLLECTION_BY_CATEGORY.get(category, "vivu_product_info")

        chunk = {
            "id": "",  # assigned by split_cold_hot to keep stable IDs
            "collection": collection,
            "vector_version": None,
            "model_id": model_id,
            "edition_id": None,
            "category": category,
            "section_path": section_path,
            "text": body_text,
            "text_type": text_type,
            "structured": {},
            "language": "vi",
            "tags": [category.replace("_", "")] + ([model_id.lower()] if model_id else []),
            "confidence": 1.0,
            "source_file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "source_url": source_url,
            "source_type": meta.get("title", path.parent.name),
            "fetched_at": meta.get("fetched_at", ""),
            "ingested_at": "",
            "is_hot": False,
        }
        chunks.append(chunk)
        buf.clear()

    for raw in lines:
        m = re.match(r"^(#{1,6})\s+(.*)", raw.strip())
        if m:
            emit()
            level = len(m.group(1))
            title = clean_line(m.group(2))
            while section_stack and section_stack[-1][0] >= level:
                section_stack.pop()
            section_stack.append((level, title))
            continue
        buf.append(raw)
    emit()

    return chunks


def specs_json_to_chunks(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse model_specs.json into:
      - vector chunks (specs, adas, dimension, powertrain, exterior, interior, safety)
      - hot rows (edition + price_list)
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    products = data.get("products", {})
    models = products.get("models", [])
    promotions = products.get("promotions", {})

    vector_chunks: list[dict[str, Any]] = []
    hot_rows: list[dict[str, Any]] = []

    for raw_model in models:
        model_id = to_model_id(raw_model)
        model_label = MODEL_LABEL.get(model_id, model_id)
        model_obj = products.get(raw_model, {})
        if not isinstance(model_obj, dict):
            continue
        list_edition = model_obj.get("listEdition", [])
        for raw_ed in list_edition:
            ed_obj = model_obj.get(raw_ed)
            if not isinstance(ed_obj, dict):
                continue
            edition_id = to_edition_id(raw_ed)
            edition_label = ed_obj.get("label", edition_id)
            price_value = parse_price(ed_obj.get("priceValue"))
            specs = ed_obj.get("specs", {})

            # ── HOT rows ─────────────────────────────────────────────────
            hot_rows.append({
                "model_id": model_id,
                "edition_id": edition_id,
                "model_label": model_label,
                "edition_label": edition_label,
                "year_range": "2025-2026",  # current VinFast line-up default
                "is_active": True,
                "price_list_vnd": price_value,
                "price_promo_vnd": None,
                "promo_label": "",
                "vat_included": True,
                "battery_included": True,
                "valid_from": "2026-07-01",
                "valid_to": None,
                "updated_at": "",
                "source_url": specs.get("urlPdp", ""),
            })

            # Promotion price from promotions[model][edition].
            promos = promotions.get(raw_model, {}).get(raw_ed, {})
            pay_direct = promos.get("PayDirectly", {})
            promo_price = parse_price(pay_direct.get("promoPriceValue") or pay_direct.get("promoPrice"))
            if promo_price is not None:
                hot_rows[-1]["price_promo_vnd"] = promo_price
                hot_rows[-1]["promo_label"] = "Ưu đãi đặt cọc 2026"

            # ── VECTOR chunks from specs ─────────────────────────────────
            chunk_base = {
                "id": "",
                "collection": "vivu_specs",
                "vector_version": None,
                "model_id": model_id,
                "edition_id": edition_id,
                "category": "thong_so_ky_thuat",
                "section_path": ["Thông số kỹ thuật"],
                "text": "",
                "text_type": "key_value",
                "structured": {},
                "language": "vi",
                "tags": ["ky_thuat", model_id.lower()],
                "confidence": 1.0,
                "source_file": str(path.relative_to(REPO_ROOT)),
                "source_url": specs.get("urlPdp", ""),
                "source_type": "specs_json",
                "fetched_at": "",
                "ingested_at": "",
                "is_hot": False,
            }

            # Dimension
            dim = specs.get("dimension", {})
            if dim:
                dim_text = f"{model_label} {edition_label} — Kích thước: "
                parts = []
                structured_dim: dict[str, Any] = {}
                length = dim.get("length", "")
                wheelbase = dim.get("wheelbase", "")
                payload = dim.get("kurbWeightPayload", "")
                clearance = dim.get("croundClearance", "")
                if length:
                    parts.append(f"Dài × Rộng × Cao {length} mm")
                    # try parse
                    try:
                        lwh = [float(x.replace(".", "").replace(",", ".").strip()) for x in str(length).split("x")]
                        keys = ["length_mm", "width_mm", "height_mm"]
                        for k, v in zip(keys, lwh):
                            structured_dim[k] = v
                    except Exception:
                        pass
                if wheelbase:
                    parts.append(f"Chiều dài cơ sở {wheelbase} mm")
                    try:
                        structured_dim["wheelbase_mm"] = int(float(str(wheelbase).replace(",", "")))
                    except Exception:
                        pass
                if payload:
                    parts.append(f"Khối lượng không tải/trọng tải {payload} kg")
                    try:
                        kw, pay = str(payload).replace(" ", "").split("/")
                        structured_dim["kerb_weight_kg"] = int(float(kw))
                        structured_dim["payload_kg"] = int(float(pay))
                    except Exception:
                        pass
                if clearance:
                    parts.append(f"Khoảng sáng gầm {clearance} mm")
                    try:
                        structured_dim["ground_clearance_mm"] = int(float(str(clearance).replace(",", "")))
                    except Exception:
                        pass
                if parts:
                    c = {**chunk_base}
                    c["section_path"] = ["Thông số kỹ thuật", "KÍCH THƯỚC & TẢI TRỌNG"]
                    c["text"] = dim_text + "; ".join(parts)
                    c["structured"] = {"dimension": structured_dim}
                    c["tags"] = c["tags"] + ["kich_thuoc"]
                    vector_chunks.append(c)

            # Powertrain
            pt = specs.get("powertrain", {})
            if pt:
                pt_parts = []
                structured_pt: dict[str, Any] = {}
                if "maxPower" in pt:
                    mp = str(pt["maxPower"])
                    pt_parts.append(f"Công suất tối đa {mp}")
                    try:
                        # "402 hp/300 kW" or "402"
                        num = re.search(r"(\d+)", mp)
                        if num:
                            structured_pt["max_power_hp"] = int(num.group(1))
                    except Exception:
                        pass
                if "maxTorque" in pt:
                    mt = str(pt["maxTorque"])
                    pt_parts.append(f"Mô-men xoắn {mt} Nm")
                    try:
                        structured_pt["max_torque_nm"] = int(re.search(r"(\d+)", mt).group(1))  # type: ignore
                    except Exception:
                        pass
                if pt.get("drivetrain"):
                    pt_parts.append(f"Hệ dẫn động {pt['drivetrain']}")
                    structured_pt["drivetrain"] = pt["drivetrain"]
                if pt.get("distance"):
                    pt_parts.append(f"Quãng đường/lần sạc {pt['distance']}")
                    structured_pt["range"] = pt["distance"]
                if pt.get("batteryCapacity"):
                    bc = pt["batteryCapacity"]
                    pt_parts.append(f"Dung lượng pin {bc} kWh")
                    try:
                        structured_pt["battery_kwh"] = float(bc)
                    except Exception:
                        structured_pt["battery_kwh"] = bc
                if pt.get("fastChargingTime"):
                    pt_parts.append(f"Thời gian sạc nhanh {pt['fastChargingTime']}")
                    structured_pt["fast_charging_time"] = pt["fastChargingTime"]
                if pt.get("maxACCharging"):
                    pt_parts.append(f"Sạc AC tối đa {pt['maxACCharging']}")
                    structured_pt["max_ac_charging"] = pt["maxACCharging"]
                if pt.get("topSpeed"):
                    pt_parts.append(f"Tốc độ tối đa {pt['topSpeed']} km/h")
                    try:
                        structured_pt["top_speed_kmh"] = int(re.search(r"(\d+)", str(pt["topSpeed"])).group(1))  # type: ignore
                    except Exception:
                        structured_pt["top_speed_kmh"] = pt["topSpeed"]
                seats = specs.get("seats") or pt.get("seats")
                if seats:
                    pt_parts.append(f"Số chỗ ngồi {seats}")
                    try:
                        structured_pt["seats"] = int(seats)
                    except Exception:
                        structured_pt["seats"] = seats
                if pt_parts:
                    c = {**chunk_base}
                    c["section_path"] = ["Thông số kỹ thuật", "ĐỘNG CƠ & VẬN HÀNH"]
                    c["text"] = f"{model_label} {edition_label} — " + "; ".join(pt_parts)
                    c["structured"] = {"powertrain": structured_pt}
                    c["tags"] = c["tags"] + ["dong_co"]
                    vector_chunks.append(c)

            # ADAS
            adas = specs.get("adas", {})
            if adas:
                yes = [k for k, v in adas.items() if isinstance(v, str) and v.strip().lower() in ("có", "yes", "true")]
                no = [k for k, v in adas.items() if isinstance(v, str) and v.strip().lower() in ("không", "no", "false")]
                c = {**chunk_base}
                c["section_path"] = ["Thông số kỹ thuật", "AN TOÀN & ADAS"]
                text_parts = [f"{model_label} {edition_label} — ADAS:"]
                if yes:
                    text_parts.append("Có: " + ", ".join(yes))
                if no:
                    text_parts.append("Không có: " + ", ".join(no))
                c["text"] = "; ".join(text_parts)
                c["structured"] = {"adas": adas}
                c["tags"] = c["tags"] + ["adas", "an_toan"]
                vector_chunks.append(c)

            # Exterior
            ext = specs.get("exterior", {})
            if ext:
                items = [f"{k}: {v}" for k, v in ext.items()]
                c = {**chunk_base}
                c["section_path"] = ["Thông số kỹ thuật", "NGOẠI THẤT"]
                c["text"] = f"{model_label} {edition_label} — Ngoại thất: " + "; ".join(items)
                c["structured"] = {"exterior": ext}
                c["tags"] = c["tags"] + ["ngoai_that"]
                vector_chunks.append(c)

            # Interior
            inter = specs.get("interior", {})
            if inter:
                items = [f"{k}: {v}" for k, v in inter.items()]
                c = {**chunk_base}
                c["section_path"] = ["Thông số kỹ thuật", "NỘI THẤT & TIỆN NGHI"]
                c["text"] = f"{model_label} {edition_label} — Nội thất: " + "; ".join(items)
                c["structured"] = {"interior": inter}
                c["tags"] = c["tags"] + ["noi_that"]
                vector_chunks.append(c)

            # Safety
            safety = specs.get("safety", {})
            if safety:
                items = [f"{k}: {v}" for k, v in safety.items()]
                c = {**chunk_base}
                c["section_path"] = ["Thông số kỹ thuật", "AN TOÀN & AN NINH"]
                c["text"] = f"{model_label} {edition_label} — An toàn: " + "; ".join(items)
                c["structured"] = {"safety": safety}
                c["tags"] = c["tags"] + ["an_toan"]
                vector_chunks.append(c)

    return vector_chunks, hot_rows


def product_info_chunks(path: Path) -> list[dict[str, Any]]:
    return chunkify_markdown(path, "thong_tin_san_pham")


def brochure_chunks(path: Path) -> list[dict[str, Any]]:
    # Brochures are OCR-heavy; treat as specs but confidence lower.
    chunks = chunkify_markdown(path, "thong_so_ky_thuat")
    for c in chunks:
        c["collection"] = "vivu_specs"
        c["tags"] = [t if t != "thongtinsanpham" else "ky_thuat" for t in c["tags"]]
        c["confidence"] = 0.85
    return chunks


def faq_chunks(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    meta, body = extract_yaml_frontmatter(text)
    source_url = source_url_from_meta(meta, path)

    chunks = []
    questions = re.split(r"\n##\s+", body)
    for idx, qblock in enumerate(questions[1:], start=1):
        lines = qblock.splitlines()
        if not lines:
            continue
        q = clean_line(lines[0])
        a = "\n".join(clean_line(line) for line in lines[1:] if clean_line(line))
        a = re.sub(r"^Nguồn:\s*https?://\S+", "", a, flags=re.MULTILINE).strip()
        if not q or not a:
            continue
        model_id = infer_model_from_path(path)
        c = {
            "id": "",
            "collection": "vivu_faq",
            "vector_version": None,
            "model_id": model_id,
            "edition_id": None,
            "category": "ho_tro_mua_xe",
            "section_path": ["FAQ", "Lái thử xe"],
            "text": f"Q: {q}\nA: {a}",
            "text_type": "qa_pair",
            "structured": {"question": q, "answer": a},
            "language": "vi",
            "tags": ["lai_thu", "faq"] + ([model_id.lower()] if model_id else []),
            "confidence": 0.9,
            "source_file": str(path.relative_to(REPO_ROOT)),
            "source_url": source_url,
            "source_type": "faq",
            "fetched_at": meta.get("fetched_at", ""),
            "ingested_at": "",
            "is_hot": False,
        }
        chunks.append(c)
    return chunks


def source_url_from_meta(meta: dict[str, Any], path: Path) -> str:
    if meta.get("url"):
        return meta["url"]
    # Fallback: derive from known patterns
    stem = path.stem
    if stem == "chinh_sach_ban_hang":
        return "https://vinfastauto.com/vn_vi/chinh-sach-ban-hang"
    if stem == "dieu_khoan_phap_ly":
        return "https://vinfastauto.com/vn_vi/dieu-khoan-phap-ly"
    if stem == "maintenance_links":
        return "https://om.vinfastauto.com/vi_vn/detail"
    return ""


def policy_chunks(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    meta, body = extract_yaml_frontmatter(text)
    source_url = source_url_from_meta(meta, path)

    # Split by articles like "Điều 1.", "Điều 2."
    pattern = r"(?:\n|\*\*?)(Điều\s+\d+)[\.\s]+([^\n\*]+)"
    matches = list(re.finditer(pattern, body))
    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        clause_title = m.group(2).strip("*.: ")
        clause_body = body[start:end]
        clause_body = re.sub(r"\*\*", "", clause_body)
        clause_body = clean_line(clause_body)
        if not clause_body:
            continue

        # Extract numbered points 1.1, 1.2 ...
        points = re.findall(r"(\d+\.\d+)\.?\s+([^\n]+)", clause_body)
        c = {
            "id": "",
            "collection": "vivu_policy",
            "vector_version": None,
            "model_id": None,
            "edition_id": None,
            "category": "chinh_sach_dich_vu",
            "section_path": ["Điều khoản Pháp lý", "CHÍNH SÁCH DỊCH VỤ CHO THUÊ PIN", m.group(1)],
            "text": clause_body,
            "text_type": "legal_clause",
            "structured": {
                "policy_name": "Chính sách dịch vụ cho thuê pin xe ô tô điện VinFast",
                "clause": m.group(1),
                "clause_title": clause_title,
                "points": [f"{p[0]} {p[1].strip()}" for p in points],
            },
            "language": "vi",
            "tags": ["phap_ly", "thue_pin", "vinfast_trading"],
            "confidence": 1.0,
            "source_file": str(path.relative_to(REPO_ROOT)),
            "source_url": source_url,
            "source_type": "policy_legal",
            "fetched_at": meta.get("fetched_at", ""),
            "ingested_at": "",
            "is_hot": False,
        }
        chunks.append(c)
    return chunks


def maintenance_link_chunks(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    meta, body = extract_yaml_frontmatter(text)
    source_url = source_url_from_meta(meta, path)

    # Parse markdown table rows
    chunks = []
    rows = re.findall(
        r"\|\s*\d+\s*\|\s*([^|]+)\|\s*(\d{4})\s*\|\s*(https?://[^\s|]+)\s*\|",
        body,
    )
    for model_name, year, url in rows:
        model_name = model_name.strip()
        model_id = MODEL_LABEL.get(model_name.replace(" ", "").upper(), model_name.replace(" ", "").upper())
        # Reverse map for display model id
        if "MPV" in model_name.upper():
            model_id = "VFMPV7"
        year = int(year)
        c = {
            "id": "",
            "collection": "vivu_maintenance",
            "vector_version": None,
            "model_id": model_id,
            "edition_id": None,
            "category": "dat_lich_bao_duong",
            "section_path": ["Link bảo dưỡng theo model + năm"],
            "text": f"Lịch bảo dưỡng {model_name} năm {year}. Xem chi tiết hạng mục bảo dưỡng tại trang quản trị VinFast (om.vinfastauto.com).",
            "text_type": "link_list",
            "structured": {"maintenance_url": url, "year": year, "note": "Link năm mới nhất đã verify; link năm cũ = đổi year=, verify lại khi ingest"},
            "language": "vi",
            "tags": ["bao_duong", model_id.lower(), str(year)],
            "confidence": 1.0,
            "source_file": str(path.relative_to(REPO_ROOT)),
            "source_url": source_url,
            "source_type": "maintenance_link",
            "fetched_at": meta.get("fetched_at", ""),
            "ingested_at": "",
            "is_hot": False,
        }
        chunks.append(c)
    return chunks


def link_only_files() -> dict[str, list[str]]:
    """Collect URLs that should only be returned as links, never embedded."""
    result: dict[str, list[str]] = {
        "showroom_urls": [],
        "promotion_urls": [],
        "roadside_cost_urls": [],
    }

    showroom = DATA_DIR / "06_showroom_tram_sac" / "utility_links.md"
    if showroom.exists():
        txt = showroom.read_text(encoding="utf-8")
        result["showroom_urls"] = re.findall(r"https?://\S+", txt)

    roadside = DATA_DIR / "03_chi_phi_lan_banh" / "utility_links.md"
    if roadside.exists():
        txt = roadside.read_text(encoding="utf-8")
        result["roadside_cost_urls"] = re.findall(r"https?://\S+", txt)

    promo_dir = DATA_DIR / "07_khuyen_mai_uu_dai"
    if promo_dir.exists():
        for p in promo_dir.glob("*.md"):
            txt = p.read_text(encoding="utf-8")
            urls = re.findall(r"https?://\S+", txt)
            result["promotion_urls"].extend(urls)
        result["promotion_urls"] = sorted(set(result["promotion_urls"]))

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean raw markdown + specs JSON into intermediate JSONL.")
    ap.add_argument("--version", default="v1", help="Output version folder (default: v1)")
    ap.add_argument("--target", type=int, default=1000, help="Target chunk size")
    ap.add_argument("--hard", type=int, default=1500, help="Hard chunk size limit")
    args = ap.parse_args()

    version_dir = CLEAN_DIR / args.version
    intermediate_dir = version_dir / "intermediate"
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    all_vector: list[dict[str, Any]] = []
    all_hot: list[dict[str, Any]] = []

    ingested_at = now_iso()

    # ── 1. Product info markdowns ────────────────────────────────────────────
    product_dir = DATA_DIR / "01_thong_tin_san_pham"
    for md in sorted(product_dir.glob("*.md")):
        chunks = product_info_chunks(md)
        all_vector.extend(chunks)

    # ── 2. Specs JSON (split cold/hot) ───────────────────────────────────────
    specs_path = DATA_DIR / "02_thong_so_ky_thuat" / "model_specs.json"
    if specs_path.exists():
        v_chunks, hot_rows = specs_json_to_chunks(specs_path)
        all_vector.extend(v_chunks)
        all_hot.extend(hot_rows)

    # ── 3. Specs/brochure markdowns (OCR sources, lower confidence) ──────────
    specs_dir = DATA_DIR / "02_thong_so_ky_thuat"
    for md in sorted(specs_dir.glob("*.md")):
        if md.name == "model_specs.json" or md.stat().st_size == 0:
            continue
        chunks = brochure_chunks(md)
        all_vector.extend(chunks)

    # ── 4. FAQ markdowns ─────────────────────────────────────────────────────
    faq_dir = DATA_DIR / "04_ho_tro_mua_xe"
    for md in sorted(faq_dir.glob("*.md")):
        all_vector.extend(faq_chunks(md))

    # ── 5. Policy markdowns ─────────────────────────────────────────────────
    policy_dir = DATA_DIR / "05_chinh_sach_dich_vu"
    for md in sorted(policy_dir.glob("*.md")):
        if md.name == "dieu_khoan_phap_ly.md":
            all_vector.extend(policy_chunks(md))
        else:
            all_vector.extend(chunkify_markdown(md, "chinh_sach_dich_vu"))

    # ── 6. Maintenance link markdowns ───────────────────────────────────────
    maint_dir = DATA_DIR / "08_dat_lich_bao_duong"
    for md in sorted(maint_dir.glob("*.md")):
        all_vector.extend(maintenance_link_chunks(md))

    # Fill shared timestamps
    for c in all_vector:
        c["vector_version"] = args.version
        c["ingested_at"] = ingested_at
        if not c.get("fetched_at"):
            c["fetched_at"] = ingested_at

    for h in all_hot:
        h["updated_at"] = ingested_at

    # Write intermediate files
    vector_file = intermediate_dir / "vector.jsonl"
    hot_file = intermediate_dir / "hot.jsonl"

    with vector_file.open("w", encoding="utf-8") as f:
        for c in all_vector:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    with hot_file.open("w", encoding="utf-8") as f:
        for h in all_hot:
            f.write(json.dumps(h, ensure_ascii=False) + "\n")

    # Link-only manifest snippet
    link_only = link_only_files()
    link_file = intermediate_dir / "link_only.json"
    link_file.write_text(json.dumps(link_only, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[clean_to_jsonl] version={args.version}")
    print(f"  vector chunks: {len(all_vector)}")
    print(f"  hot rows:      {len(all_hot)}")
    print(f"  output dir:    {intermediate_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
