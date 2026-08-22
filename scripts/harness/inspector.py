#!/usr/bin/env python3
"""
inspector.py — PDF Inspector & Layout Signal Analyzer (No LLM).

Inspects each page in a PDF to collect structural signals:
- Text layer presence & quality
- Overlapping text ratio
- Vector drawings & table line detection
- Image presence / scan detection
- High-res page rendering (2x DPI)
- Page classification & extraction strategy recommendation
"""

from pathlib import Path
from typing import List, Tuple

import fitz  # PyMuPDF

from scripts.harness.config import OVERLAP_VISION_THRESHOLD, TEXT_QUALITY_THRESHOLD
from scripts.harness.schemas import PageSignals

# Keywords indicating technical specifications or table layouts
SPEC_KEYWORDS = [
    "thông số",
    "thong so",
    "kích thước",
    "kich thuoc",
    "chiều dài cơ sở",
    "công suất tối đa",
    "mô men xoắn",
    "dung lượng pin",
    "quãng đường",
    "động cơ",
    "hệ thống truyền động",
    "khung gầm",
    "tiện nghi",
    "an toàn",
    "dài x rộng x cao",
    "khoảng sáng gầm",
    "la-zăng",
    "túi khí",
]


class PDFInspector:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def inspect_pdf(self, pdf_path: Path, doc_id: str = "doc") -> Tuple[List[PageSignals], List[Path]]:
        """
        Inspect all pages of a PDF document.
        Returns:
            signals: list of PageSignals for each page (1-indexed)
            rendered_images: list of Path to rendered page images
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        pages_dir = self.output_dir / "artifacts" / doc_id / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)

        signals_list: List[PageSignals] = []
        rendered_images: List[Path] = []

        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = doc[page_idx]

            # 1. Render page image (2.0x zoom for high quality OCR/Vision)
            img_path = pages_dir / f"p_{page_num:03d}.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            pix.save(img_path)
            rendered_images.append(img_path)

            # 2. Extract structural elements
            blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
            words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
            images = page.get_images(full=True)
            drawings = page.get_drawings()

            text_blocks_count = len([b for b in blocks if b[6] == 0])  # type 0 = text
            words_count = len(words)
            images_count = len(images)
            drawings_count = len(drawings)

            # 3. Calculate text overlap ratio
            overlap_count = 0
            for i in range(len(words)):
                w1 = words[i]
                r1 = fitz.Rect(w1[0], w1[1], w1[2], w1[3])
                for j in range(i + 1, min(i + 15, len(words))):
                    w2 = words[j]
                    r2 = fitz.Rect(w2[0], w2[1], w2[2], w2[3])
                    intersect = r1.intersect(r2)
                    if not intersect.is_empty and intersect.get_area() > 0.4 * min(r1.get_area(), r2.get_area()):
                        overlap_count += 1
                        break
            overlap_ratio = round(overlap_count / max(1, words_count), 3)

            # 4. Detect scan / image-only
            is_scanned = words_count < 15 and images_count >= 1

            # 5. Detect table structure / technical specs
            full_text = page.get_text().lower()
            spec_matches = sum(1 for kw in SPEC_KEYWORDS if kw in full_text)
            has_table_structure = (
                spec_matches >= 3 or (drawings_count >= 8 and words_count > 30) or "thông số kỹ thuật" in full_text
            )

            # C2 fix: compute quality before strategy and use centralized thresholds
            text_layer_quality = round(max(0.0, 1.0 - (overlap_ratio * 1.5) - (0.5 if is_scanned else 0.0)), 2)

            # 6. Classify page type & recommended strategy (C2: planner is source of truth, inspector mirrors it)
            page_type = "prose"
            recommended_strategy = "pymupdf"

            if page_num == 1:
                page_type = "cover"
                recommended_strategy = "pymupdf"
            elif is_scanned:
                page_type = "mixed"
                recommended_strategy = "ocr"
            elif spec_matches >= 4 or "thông số kỹ thuật" in full_text:
                page_type = "spec_table"
                recommended_strategy = "vision_table"
            elif overlap_ratio > OVERLAP_VISION_THRESHOLD or text_layer_quality < TEXT_QUALITY_THRESHOLD:
                page_type = "mixed"
                recommended_strategy = "vision_prose"
            elif "bảng giá" in full_text or "giá bán" in full_text or "chi phí" in full_text:
                page_type = "pricing"
                recommended_strategy = "vision_table" if has_table_structure else "pymupdf"
            else:
                page_type = "prose"
                recommended_strategy = "pymupdf"

            signals = PageSignals(
                page_number=page_num,
                text_blocks_count=text_blocks_count,
                words_count=words_count,
                images_count=images_count,
                drawings_count=drawings_count,
                overlap_ratio=overlap_ratio,
                text_layer_quality=text_layer_quality,
                is_scanned=is_scanned,
                has_table_structure=has_table_structure,
                page_type=page_type,
                recommended_strategy=recommended_strategy,
            )
            signals_list.append(signals)

        doc.close()
        return signals_list, rendered_images
