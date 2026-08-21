#!/usr/bin/env python3
"""
pymupdf.py — PyMuPDF Text & Spatial Layout Extractor.

Extracts text blocks from standard vector PDF pages, classifying them into
headings, paragraphs, footnotes, and lists with bounding boxes in PDF points.
"""

import re
from typing import List

import fitz

from scripts.harness.schemas import BBox, CanonicalBlock, Evidence, Provenance


class PyMuPDFExtractor:
    def __init__(self, doc_id: str):
        self.doc_id = doc_id

    def extract_page(
        self,
        page: fitz.Page,
        page_num: int,
        source_url: str = "",
    ) -> List[CanonicalBlock]:
        """
        Extract canonical blocks from a PyMuPDF page.
        """
        rect = page.rect
        page_size = {"width": float(rect.width), "height": float(rect.height)}
        raw_blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)

        canonical_blocks: List[CanonicalBlock] = []
        block_idx = 1
        current_section = None

        for b in raw_blocks:
            x0, y0, x1, y1, text, b_no, b_type = b
            if b_type != 0:  # Skip image blocks (handled separately)
                continue

            text = text.strip()
            if not text:
                continue

            # Clean duplicate whitespace
            text = re.sub(r"[ \t]+", " ", text)
            block_id = f"p{page_num:02d}_b{block_idx:02d}"

            bbox = BBox(
                x1=round(x0, 1),
                y1=round(y0, 1),
                x2=round(x1, 1),
                y2=round(y1, 1),
                page_size=page_size,
            )

            # Heuristics for block type
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            first_line = lines[0] if lines else text
            is_all_caps = first_line.isupper() and len(first_line) > 3

            # Detect block type
            if y0 > rect.height * 0.85 and (len(text) < 150 or text.startswith("*")):
                b_type_str = "footnote"
            elif (len(lines) <= 2 and (len(text) < 80 or is_all_caps)) or text.startswith("#"):
                b_type_str = "heading"
                current_section = text.lstrip("#").strip()
            elif any(line.startswith(("-", "•", "*", "1.", "2.", "3.")) for line in lines):
                b_type_str = "list"
            else:
                b_type_str = "paragraph"

            evidence = Evidence(
                document_id=self.doc_id,
                page=page_num,
                bbox=bbox,
                source_block=block_id,
                deep_link=f"{source_url}#page={page_num}" if source_url else None,
            )

            provenance = Provenance(
                method="pymupdf_text",
                model="pymupdf_1.24",
                confidence=0.98 if b_type_str != "footnote" else 0.92,
            )

            block = CanonicalBlock(
                block_id=block_id,
                type=b_type_str,
                text=text,
                section=current_section,
                evidence=evidence,
                extraction=provenance,
            )
            canonical_blocks.append(block)
            block_idx += 1

        return canonical_blocks
