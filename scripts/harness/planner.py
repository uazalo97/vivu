#!/usr/bin/env python3
"""
planner.py — Strategy Selector & Extraction Planner.

Analyzes PageSignals from PDFInspector and assigns optimal extraction strategy:
- Clean text pages -> PyMuPDF
- Spec tables / Graphic layouts (e.g. Page 12) -> Vision Table Extractor
- Scans / Low-quality text -> OCR / Vision
"""

from typing import Dict, List
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
            elif sig.overlap_ratio > 0.18 or sig.text_layer_quality < 0.6:
                plan[p_num] = "vision_prose"
            else:
                plan[p_num] = "pymupdf"
        return plan
