#!/usr/bin/env python3
"""
web_text.py — Extractor for web articles, policy documents, and maintenance texts.
Reads from data_v2/raw/web_policies/ and data_v2/raw/web_deposit/
Normalizes and routes chunks into collections:
- vivu_policy
- vivu_maintenance
- vivu_product_info
- vivu_faq
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.harness.config import RAW_DEPOSIT_DIR, RAW_POLICIES_DIR
from scripts.harness.normalizers.text import clean_prose_block, strip_prices_for_vector
from scripts.harness.schemas import RetrievalChunk


def infer_model_from_name(name: str) -> str | None:
    n = name.lower()
    for m in ["vf 8 all new", "vf8_2026", "the-all-new"]:
        if m in n:
            return "VF8NEW"
    for m in ["vf mpv 7", "vf-mpv7", "mpv7"]:
        if m in n:
            return "VFMPV7"
    for m in ["vf2", "vf3", "vf5", "vf6", "vf7", "vf8", "vf9"]:
        if m in n:
            return m.upper()
    return None


class WebTextExtractor:
    def __init__(self, policies_dir: Path = RAW_POLICIES_DIR, deposit_dir: Path = RAW_DEPOSIT_DIR, max_chunk_chars: int = 800):
        self.policies_dir = Path(policies_dir)
        self.deposit_dir = Path(deposit_dir)
        self.max_chunk_chars = max_chunk_chars

    def extract_all_web_chunks(self) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []

        # 1. Process policies
        if self.policies_dir.exists():
            for f in sorted(self.policies_dir.glob("*.*")):
                if f.is_file():
                    chunks.extend(self._process_file(f))

        # 2. Process deposit web text dumps
        if self.deposit_dir.exists():
            for f in sorted(self.deposit_dir.glob("*.txt")):
                if f.is_file():
                    chunks.extend(self._process_file(f))

        return chunks

    def _process_file(self, path: Path) -> List[Dict[str, Any]]:
        name = path.stem.lower()
        content = path.read_text(encoding="utf-8", errors="replace")

        # Routing collection & category
        collection = "vivu_product_info"
        category = "thong_tin_san_pham"

        if any(k in name for k in ["bao-duong", "sua-chua", "maintenance"]):
            collection = "vivu_maintenance"
            category = "dat_lich_bao_duong"
        elif any(k in name for k in ["bao-hanh", "pin", "cuu-ho", "chinh-sach", "phap-ly", "ky-thuat"]):
            collection = "vivu_policy"
            category = "chinh_sach_dich_vu"
        elif any(k in name for k in ["ban-hang", "ho-tro", "faq"]):
            collection = "vivu_policy"
            category = "ho_tro_mua_xe"
        elif any(k in name for k in ["khuyen_mai", "promotions", "uu_dai"]):
            collection = "vivu_policy"
            category = "khuyen_mai_uu_dai"

        model_id = infer_model_from_name(name)

        # Extract source url if header present
        source_url = ""
        m_url = re.search(r"^(?:url|Nguồn|source):\s*([^\r\n]+)", content, re.IGNORECASE | re.MULTILINE)
        if m_url:
            source_url = m_url.group(1).strip()
        elif "chinh-sach-bao-hanh" in name:
            source_url = "https://vinfastauto.com/vn_vi/chinh-sach-bao-hanh"
        elif "dich-vu-pin" in name:
            source_url = "https://vinfastauto.com/vn_vi/dich-vu-pin-oto-dien"
        elif "dich-vu-bao-duong" in name:
            source_url = "https://vinfastauto.com/vn_vi/dich-vu-bao-duong-oto"
        elif "cuu-ho" in name:
            source_url = "https://vinfastauto.com/vn_vi/thong-tin-cuu-ho-oto"
        elif "chinh_sach_ban_hang" in name:
            source_url = "https://vinfastauto.com/vn_vi/chinh-sach-ban-hang"
        elif "dat-coc-xe" in name and model_id:
            source_url = f"https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-{model_id}"

        # Heading-based & paragraph chunking
        sections = self._split_into_sections(content)
        file_chunks = []

        for sec_title, sec_text in sections:
            cleaned = clean_prose_block(sec_text)
            if not cleaned or len(cleaned) < 30:
                continue

            # Strip exact money numbers for vector embedding
            vec_text = strip_prices_for_vector(cleaned)
            full_text = f"{sec_title}: {vec_text}" if sec_title else vec_text

            chunk_id = f"{collection}:{path.stem[:30]}_{len(file_chunks)+1:03d}"
            file_chunks.append({
                "id": chunk_id,
                "text": full_text,
                "collection": collection,
                "metadata": {
                    "collection": collection,
                    "category": category,
                    "model_id": model_id,
                    "edition_id": None,
                    "section_path": [category, sec_title] if sec_title else [category],
                    "text_type": "prose",
                    "confidence": 1.0,
                    "source_file": f"data_v2/raw/{path.parent.name}/{path.name}",
                    "source_url": source_url,
                    "source_type": "markdown" if path.suffix == ".md" else "raw_html",
                }
            })

        return file_chunks

    def _split_into_sections(self, text: str) -> List[Tuple[str, str]]:
        lines = text.splitlines()
        sections: List[Tuple[str, str]] = []
        current_title = ""
        current_lines: List[str] = []

        for line in lines:
            line_str = line.strip()
            # Markdown heading or uppercase title
            if line_str.startswith("#") or (len(line_str) > 3 and line_str.isupper() and len(line_str) < 80):
                if current_lines:
                    sections.append((current_title, "\n".join(current_lines)))
                    current_lines = []
                current_title = line_str.lstrip("#").strip()
            else:
                if line_str:
                    current_lines.append(line_str)
                    if sum(len(l) for l in current_lines) > self.max_chunk_chars:
                        sections.append((current_title, "\n".join(current_lines)))
                        current_lines = []

        if current_lines:
            sections.append((current_title, "\n".join(current_lines)))

        return sections
