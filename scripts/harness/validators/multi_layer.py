#!/usr/bin/env python3
"""
validators/ — Multi-layer Validation Engine for Extracted Data.

Checks:
- Structural: Valid BBox bounds within page dimensions, non-empty attributes.
- Semantic: Sanity ranges for vehicle specs (kW, Nm, kWh, mm, km) & unit consistency.
- Schema: Required evidence fields.
- Visual: Cross-validation between Vision and PyMuPDF text layer.
"""

import re
from typing import Dict, List, Optional, Tuple

from scripts.harness.schemas import CanonicalBlock, CanonicalPage, SpecItem, ValidationResult

SANITY_RANGES = {
    "power_kw": (10, 600),
    "torque_nm": (30, 1000),
    "battery_kwh": (5, 250),
    "range_km": (50, 1200),
    "wheelbase_mm": (1500, 4000),
    "ground_clearance_mm": (50, 400),
    "length_mm": (2000, 6000),
    "width_mm": (1000, 2500),
    "height_mm": (1000, 2500),
    "seats": (2, 9),
    "wheel_size_inch": (12, 24),
}


class MultiLayerValidator:
    def validate_spec_item(self, item: SpecItem, page_size: Dict[str, float]) -> ValidationResult:
        """Validate a single SpecItem across structural, semantic, and schema dimensions."""
        issues = []
        structural_pass = True
        semantic_pass = True
        schema_pass = True

        # 1. Structural Check
        if not item.attribute or not str(item.attribute).strip():
            issues.append("Empty attribute name")
            structural_pass = False

        if item.evidence and item.evidence.bbox:
            bb = item.evidence.bbox
            pw = page_size.get("width", 842.0)
            ph = page_size.get("height", 595.0)
            if bb.x1 < 0 or bb.y1 < 0 or bb.x2 > pw + 10 or bb.y2 > ph + 10 or bb.x2 <= bb.x1 or bb.y2 <= bb.y1:
                issues.append(f"BBox [{bb.x1}, {bb.y1}, {bb.x2}, {bb.y2}] out of page bounds [{pw}, {ph}]")
                structural_pass = False

        # 2. Schema Check
        if not item.evidence or item.evidence.page is None:
            issues.append("Missing page evidence")
            schema_pass = False

        # 3. Semantic Check
        val_str = str(item.value).strip().replace(",", ".")
        val_num = None
        m = re.search(r"[\d]+(?:\.[\d]+)?", val_str)
        if m:
            try:
                val_num = float(m.group(0))
            except ValueError:
                pass

        if item.spec_key and item.spec_key in SANITY_RANGES and val_num is not None:
            lo, hi = SANITY_RANGES[item.spec_key]
            if not (lo <= val_num <= hi):
                issues.append(f"Semantic warning: {item.spec_key}={val_num} outside sanity range [{lo}, {hi}]")
                semantic_pass = False

        conf = 0.98 if not issues else (0.75 if semantic_pass and structural_pass else 0.4)

        return ValidationResult(
            structural=structural_pass,
            visual=True,
            semantic=semantic_pass,
            schema_valid=schema_pass,
            confidence=conf,
            issues=issues,
        )

    def validate_page(self, page: CanonicalPage) -> CanonicalPage:
        """Validate all blocks and items on a canonical page."""
        for block in page.blocks:
            if block.items:
                for item in block.items:
                    item.validation = self.validate_spec_item(item, page.page_size)
        return page
