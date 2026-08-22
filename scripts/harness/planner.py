#!/usr/bin/env python3
"""
planner.py — Strategy Selector & Extraction Planner.

Analyzes PageSignals from PDFInspector and assigns optimal extraction strategy:
- Clean text pages -> PyMuPDF
- Spec tables / Graphic layouts (e.g. Page 12) -> Vision Table Extractor
- Scans / Low-quality text -> OCR / Vision
"""

from typing import Dict, List
from scripts.harness.config import OVERLAP_VISION_THRESHOLD, TEXT_QUALITY_THRESHOLD
from scripts.harness.schemas import PageSignals


class ExtractionPlanner:
    def plan_document(self, signals_list: List[PageSignals]) -> Dict[int, str]:
        """
        Produce a plan mapping page_number -> strategy.
        Strategies: "pymupdf", "vision_table", "vision_prose", "ocr"
        """
        plan: Dict[int, str] = {}
        for sig in signals_list:
            p_num = sig.page_number
            if sig.is_scanned:
                plan[p_num] = "ocr"
            elif sig.page_type == "spec_table" or sig.has_table_structure:
                plan[p_num] = "vision_table"
            elif sig.page_type == "pricing":
                # C2 fix: explicit pricing handling to match inspector
                plan[p_num] = "vision_table" if sig.has_table_structure else "pymupdf"
            elif sig.overlap_ratio > OVERLAP_VISION_THRESHOLD or sig.text_layer_quality < TEXT_QUALITY_THRESHOLD:
                plan[p_num] = "vision_prose"
            else:
                plan[p_num] = "pymupdf"
        return plan
