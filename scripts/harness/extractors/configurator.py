#!/usr/bin/env python3
"""
configurator.py — Extractor & Normalizer for VinFast Car Configurator data.
Processes window.carDeposit CSVs into clean PostgreSQL datasets:
- edition.csv
- price_list.csv
- car_colors.csv
- car_options.csv
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.harness.config import CONFIGURATOR_DIR, STRUCTURED_DIR

MODEL_LABEL = {
    "VF2": "VF 2",
    "VF3": "VF 3",
    "VF5": "VF 5",
    "VF6": "VF 6",
    "VF7": "VF 7",
    "VF8": "VF 8",
    "VF8NEW": "VF 8 All New",
    "VF9": "VF 9",
    "VFMPV7": "VF MPV 7",
}

EDITION_ALIAS = {
    "Tiêu chuẩn": "TieuChuan",
    "The All New": "The All New",
    "The New": "The All New",
    "Eco": "Eco",
    "Plus": "Plus",
    "Plus 2 động cơ": "Plus",
    "Plus tùy chọn ghế cơ trưởng": "PlusCaptain",
    "Plus_AWD": "Plus_AWD",
    "Plus_AWD_PanoramicRoof": "Plus_AWD_PanoramicRoof",
    "Base": "Base",
}


def _norm_edition(raw_ed: str) -> str:
    raw_ed = (raw_ed or "").strip()
    return EDITION_ALIAS.get(raw_ed, raw_ed)


class ConfiguratorExtractor:
    def __init__(self, raw_dir: Path = CONFIGURATOR_DIR, out_dir: Path = STRUCTURED_DIR):
        self.raw_dir = Path(raw_dir)
        self.out_dir = Path(out_dir)

    def extract_and_normalize(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Reads raw configurator CSVs and normalizes into 4 structured datasets.
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)

        editions_out: List[Dict[str, Any]] = []
        prices_out: List[Dict[str, Any]] = []
        colors_out: List[Dict[str, Any]] = []
        options_out: List[Dict[str, Any]] = []

        # 1. Process edition.csv & price_list.csv
        raw_price_file = self.raw_dir / "price_list.csv"
        if raw_price_file.exists():
            with open(raw_price_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="|")
                for row in reader:
                    m_id = row["model_id"]
                    ed_id = _norm_edition(row["edition_id"])
                    p_vnd = int(row["price_list_vnd"]) if row.get("price_list_vnd") else 0
                    p_promo = int(row["price_promo_vnd"]) if row.get("price_promo_vnd") else None
                    src_url = row.get("source_url") or f"https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-{m_id}"

                    editions_out.append({
                        "model_id": m_id,
                        "edition_id": ed_id,
                        "model_label": MODEL_LABEL.get(m_id, m_id),
                        "edition_label": ed_id,
                        "year_range": "2026",
                        "is_active": True,
                    })

                    prices_out.append({
                        "model_id": m_id,
                        "edition_id": ed_id,
                        "price_list_vnd": p_vnd,
                        "price_promo_vnd": p_promo,
                        "promo_label": row.get("promo_label") or "",
                        "vat_included": True,
                        "battery_included": True,
                        "valid_from": row.get("valid_from") or "2026-07-01",
                        "valid_to": row.get("valid_to") or None,
                        "source_url": src_url,
                    })

        # Deduplicate editions
        seen_ed = set()
        dedup_editions = []
        for e in editions_out:
            k = (e["model_id"], e["edition_id"])
            if k not in seen_ed:
                seen_ed.add(k)
                dedup_editions.append(e)
        editions_out = dedup_editions

        # 2. Process colors.csv
        raw_colors_file = self.raw_dir / "colors.csv"
        if raw_colors_file.exists():
            with open(raw_colors_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="|")
                for row in reader:
                    m_id = row["model_id"]
                    fee = int(row.get("price_extra_vnd") or 0)
                    c_type = "Nâng cao" if fee > 0 else "Cơ bản"
                    src_url = f"https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-{m_id}"
                    
                    colors_out.append({
                        "model_id": m_id,
                        "version_code": row.get("variant_code") or "",
                        "version_name": _norm_edition(row.get("edition_id")),
                        "color_code": row.get("color_code") or "",
                        "color_name": row.get("color_name") or "",
                        "color_type": c_type,
                        "color_fee_vnd": fee,
                        "interior_code": row.get("interior_code") or "",
                        "interior_name": row.get("interior_name") or ("Grey" if m_id == "VF2" else ""),
                        "source_url": src_url,
                    })

        # 3. Process options.csv
        raw_options_file = self.raw_dir / "options.csv"
        if raw_options_file.exists():
            with open(raw_options_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="|")
                for row in reader:
                    m_id = row["model_id"]
                    fee = int(row.get("price_extra_vnd") or 0)
                    # if fee in raw options is in thousands (e.g. 10000 = 10tr), adjust
                    if 0 < fee < 100000:
                        fee *= 1000
                    src_url = f"https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-{m_id}"

                    options_out.append({
                        "model_id": m_id,
                        "version_code": row.get("edition_code") or "",
                        "version_name": _norm_edition(row.get("edition_code")),
                        "option_group": row.get("option_id") or row.get("option_group") or "options",
                        "option_name": row.get("option_name") or "Tùy Chọn",
                        "value_id": row.get("value_id") or "",
                        "value_name": row.get("value_name") or "",
                        "price_extra_vnd": fee,
                        "source_url": src_url,
                    })

        # Write clean CSVs into structured/
        self._write_csv(self.out_dir / "edition.csv", ["model_id", "edition_id", "model_label", "edition_label", "year_range", "is_active"], editions_out)
        self._write_csv(self.out_dir / "price_list.csv", ["model_id", "edition_id", "price_list_vnd", "price_promo_vnd", "promo_label", "vat_included", "battery_included", "valid_from", "valid_to", "source_url"], prices_out)
        self._write_csv(self.out_dir / "car_colors.csv", ["model_id", "version_code", "version_name", "color_code", "color_name", "color_type", "color_fee_vnd", "interior_code", "interior_name", "source_url"], colors_out)
        self._write_csv(self.out_dir / "car_options.csv", ["model_id", "version_code", "version_name", "option_group", "option_name", "value_id", "value_name", "price_extra_vnd", "source_url"], options_out)

        return editions_out, prices_out, colors_out, options_out

    def _write_csv(self, path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="|")
            writer.writeheader()
            for r in rows:
                writer.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
