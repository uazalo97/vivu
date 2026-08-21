#!/usr/bin/env python3
"""
table.py — Normalizer for Vehicle Specifications.

Maps Vietnamese specification attributes to standardized English keys,
normalizes numbers (thousands dots, decimal commas), units, and editions.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from scripts.harness.schemas import SpecItem


def no_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm_label(s: str) -> str:
    s = no_diacritics(s).lower().replace("đ", "d")
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(":|-–— \t")


# Label alias mapping to (spec_key, default_unit, category_en)
LABEL_MAPPING: Dict[str, Tuple[str, str, str]] = {
    # Powertrain & Battery
    "cong suat toi da": ("power_kw", "kW", "powertrain"),
    "cong suat": ("power_kw", "kW", "powertrain"),
    "mo men xoan cuc dai": ("torque_nm", "Nm", "powertrain"),
    "mo men xoan": ("torque_nm", "Nm", "powertrain"),
    "dung luong pin kha dung": ("battery_kwh", "kWh", "battery"),
    "dung luong pin": ("battery_kwh", "kWh", "battery"),
    "loai pin": ("battery_type", "", "battery"),
    "quang duong di chuyen": ("range_km", "km", "powertrain"),
    "quang duong chay mot lan sac day": ("range_km", "km", "powertrain"),
    "quang duong chay": ("range_km", "km", "powertrain"),
    "quang duong": ("range_km", "km", "powertrain"),
    "dan dong": ("drivetrain", "", "powertrain"),
    "he dan dong": ("drivetrain", "", "powertrain"),
    "thoi gian nap pin nhanh nhat": ("fast_charge_min", "phút", "battery"),
    "thoi gian sac nhanh": ("fast_charge_min", "phút", "battery"),
    "toc do toi da": ("top_speed_kmh", "km/h", "powertrain"),
    "tang toc 0-100 km/h": ("acceleration_0_100_s", "s", "powertrain"),
    
    # Dimensions
    "dai x rong x cao": ("dimension_triple", "mm", "dimension"),
    "kich thuoc": ("dimension_triple", "mm", "dimension"),
    "chieu dai co so": ("wheelbase_mm", "mm", "dimension"),
    "khoang sang gam xe": ("ground_clearance_mm", "mm", "dimension"),
    "khoang sang gam": ("ground_clearance_mm", "mm", "dimension"),
    
    # Interior & Exterior
    "so cho ngoi": ("seats", "", "interior"),
    "so ghe ngoi": ("seats", "", "interior"),
    "kich thuoc la-zang": ("wheel_size_inch", "inch", "exterior"),
    "kich thuoc mam xe": ("wheel_size_inch", "inch", "exterior"),
    "man hinh giai tri cam ung": ("display_inch", "inch", "interior"),
    "so luong tui khi": ("airbags", "", "safety"),
    "tui khi": ("airbags", "", "safety"),
}

ALIASES_BY_LEN = sorted(LABEL_MAPPING.keys(), key=len, reverse=True)


class TableNormalizer:
    def map_attribute(self, raw_attr: str) -> Optional[Tuple[str, str, str]]:
        """Map raw Vietnamese attribute string to (spec_key, unit, category)."""
        na = norm_label(raw_attr)
        if na in LABEL_MAPPING:
            return LABEL_MAPPING[na]
        for a in ALIASES_BY_LEN:
            if a in na or na.startswith(a):
                return LABEL_MAPPING[a]
        return None

    def normalize_number(self, val_str: str) -> Tuple[Optional[float], str]:
        """Normalize Vietnamese number formats (e.g. 2.730 -> 2730, 59,6 -> 59.6)."""
        s = str(val_str).strip()
        m = re.search(r"[\d][\d.,]*", s)
        if not m:
            return None, s
        tok = m.group(0)
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", tok):
            tok = tok.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d+,\d+", tok):
            tok = tok.replace(",", ".")
        try:
            val = float(tok)
            canon = str(int(val)) if val.is_integer() else f"{val:g}"
            return val, canon
        except ValueError:
            return None, s

    def normalize_spec_item(self, item: SpecItem) -> List[SpecItem]:
        """
        Normalize a SpecItem:
        - Maps spec_key
        - If attribute is dimension_triple ("4238 x 1820 x 1594"), splits into 3 items (length, width, height)
        """
        mapping = self.map_attribute(item.attribute)
        if not mapping:
            return [item]

        spec_key, default_unit, category_en = mapping
        unit = item.unit or default_unit

        if spec_key == "dimension_triple":
            val_str = str(item.value)
            parts = re.split(r"\s*[xX×]\s*", val_str)
            sub_items = []
            dim_keys = [("length_mm", "Chiều dài"), ("width_mm", "Chiều rộng"), ("height_mm", "Chiều cao")]
            for idx, (sub_k, sub_name) in enumerate(dim_keys):
                if idx < len(parts):
                    _, canon = self.normalize_number(parts[idx])
                    sub_items.append(
                        SpecItem(
                            category="Kích thước",
                            attribute=f"{item.attribute} ({sub_name})",
                            value=canon,
                            unit="mm",
                            edition=item.edition,
                            spec_key=sub_k,
                            evidence=item.evidence,
                            validation=item.validation,
                            provenance=item.provenance,
                        )
                    )
            return sub_items if sub_items else [item]

        # Standard numeric / text normalization
        _, canon = self.normalize_number(str(item.value))
        item.spec_key = spec_key
        item.unit = unit
        if canon:
            item.value = canon

        return [item]
