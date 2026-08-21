#!/usr/bin/env python3
"""
postgres.py — Structured Specs Sink.

Exports normalized vehicle specifications with full provenance & BBox
to data_v2/structured/ for inspection & preview. (Safe test mode: no DB mutation).
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.harness.schemas import CanonicalDocument, SpecItem


class PostgresSpecsSink:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def export_preview(self, doc: CanonicalDocument) -> Tuple[Path, Path]:
        """
        Extract all SpecItems from CanonicalDocument and save structured preview
        to data_v2/structured/{doc_id}_specs.json and .csv.
        """
        struct_dir = self.output_dir / "structured"
        struct_dir.mkdir(parents=True, exist_ok=True)

        doc_id = doc.document.id
        model_code = doc.document.model_code
        source_url = doc.document.source_url or doc.document.source_file

        rows: List[Dict[str, Any]] = []

        for item in doc.get_all_spec_items():
            ev = item.evidence
            page_num = ev.page if ev else None
            bbox_list = ev.bbox.to_list() if ev and ev.bbox else None
            block_id = ev.source_block if ev else None
            conf = item.validation.confidence if item.validation else 1.0

            rows.append(
                {
                    "model_code": model_code,
                    "version_name": item.edition,  # e.g., "Eco", "Plus", or None
                    "spec_category": item.category,
                    "spec_key": item.spec_key or item.attribute,
                    "spec_value": str(item.value),
                    "spec_unit": item.unit or "",
                    "source_document": doc_id,
                    "source_url": source_url,
                    "source_page": page_num,
                    "source_bbox": bbox_list,
                    "source_block_id": block_id,
                    "confidence": conf,
                }
            )

        # 1. Save JSON preview
        json_path = struct_dir / f"{doc_id}_specs.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

        # 2. Save CSV preview (pipe-delimited)
        csv_path = struct_dir / f"{doc_id}_specs.csv"
        fieldnames = [
            "model_code", "version_name", "spec_category", "spec_key",
            "spec_value", "spec_unit", "source_document", "source_url",
            "source_page", "source_bbox", "source_block_id", "confidence"
        ]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="|")
            writer.writeheader()
            for r in rows:
                writer.writerow(
                    {
                        k: (json.dumps(r[k]) if isinstance(r[k], list) else ("" if r[k] is None else r[k]))
                        for k in fieldnames
                    }
                )

        return json_path, csv_path
