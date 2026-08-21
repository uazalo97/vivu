#!/usr/bin/env python3
"""
text.py — Text normalization and noise cleaning for web/prose data.
"""

import re
import unicodedata

# Regex for price stripping in vector prose
PRICE_REGEXES = [
    re.compile(r"\b\d{1,3}(?:\.\d{3})+(?:\s*(?:VNĐ|VND|đồng|đ))\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:,\d+)?\s*(?:tỷ|triệu|tr)\s*(?:đồng|VNĐ|VND|đ)?\b", re.IGNORECASE),
    re.compile(r"\b\d{3,4}\s*(?:triệu|tr)\b", re.IGNORECASE),
]

# Regex for page markers & noise
PAGE_MARKER_RE = re.compile(r"^[-—\s]*Trang\s+\d+[/–—-]?\d*[-—\s]*$", re.IGNORECASE | re.MULTILINE)
BOILERPLATE_RE = re.compile(
    r"^\s*(\*|\*\*|\*\*\*)\s*Hình ảnh chỉ mang tính chất minh họa.*$", re.IGNORECASE | re.MULTILINE
)


def normalize_unicode_spacing(text: str) -> str:
    """Normalize Unicode (NFC), collapse whitespace, fix broken punctuation spacing."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    # Fix broken Vietnamese diacritics spacing (e.g. "V inFast" -> "VinFast" if known, or extra spaces before commas)
    text = re.sub(r"\s+([,.:;?!])", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def strip_prices_for_vector(text: str) -> str:
    """Strip exact VND prices from prose text to avoid hallucinated pricing in embeddings."""
    out = text
    for rx in PRICE_REGEXES:
        out = rx.sub("[GIÁ LIÊN HỆ ĐẠI LÝ]", out)
    return out


def clean_prose_block(text: str) -> str:
    """Clean a paragraph or block of prose text."""
    if not text:
        return ""
    text = PAGE_MARKER_RE.sub("", text)
    text = BOILERPLATE_RE.sub("", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = " ".join(lines)
    return normalize_unicode_spacing(cleaned)
