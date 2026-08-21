#!/usr/bin/env python3
"""
vision.py — Multimodal Vision Extractor for Complex Table & Graphic Layouts.

Uses Multimodal LLMs (gpt-5.6-luna) on rendered high-resolution page images
to extract technical specifications, table cells, editions, and bounding boxes.
"""

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from scripts.harness.schemas import (
    BBox,
    CanonicalBlock,
    Evidence,
    Provenance,
    SpecItem,
    ValidationResult,
)

load_dotenv()


VISION_SYSTEM_PROMPT = """You are a precision Vision Data Extractor for VinFast vehicle brochure technical specification pages.
Your job is to accurately read the rendered page image and extract structured blocks and technical specifications.

For each technical specification table or card found on the page:
1. Extract the section/heading title.
2. For each row in the specification table:
   - "category": e.g. "Kích thước & Trọng lượng", "Động cơ & Vận hành", "Pin & Sạc", "Ngoại thất", "Nội thất & Tiện nghi", "An toàn & An ninh", "Hệ thống hỗ trợ lái nâng cao ADAS".
   - "attribute": Exact name in Vietnamese (e.g. "Chiều dài cơ sở", "Dài x Rộng x Cao", "Công suất tối đa", "Mô men xoắn cực đại", "Dung lượng pin khả dụng", "Quãng đường di chuyển").
   - "value": The extracted numeric or qualitative value (e.g. "2730", "4238 x 1820 x 1594", "150", "310", "59.6", "381", "LFP", "Có").
   - "unit": The unit of measurement if present (e.g. "mm", "kW", "Nm", "kWh", "km", "inch", "L", or null).
   - "edition": If the column is for a specific version ("Eco", "Plus", "PlusCaptain", "Base"), specify it. If it applies to all or there is only 1 version column, set to null.
   - "bbox": Approximate bounding box of this table/card [ymin, xmin, ymax, xmax] scaled 0 to 1000 relative to the image dimensions.

3. For footnotes, disclaimers, or notes (e.g. NEDC / WLTP notes):
   - Extract type as "footnote" with the exact text and bbox.

Output strictly valid JSON with this format:
{
  "heading": "THÔNG SỐ KỸ THUẬT VINFAST VF 6",
  "heading_bbox": [50, 50, 100, 950],
  "specs": [
    {
      "category": "Kích thước",
      "attribute": "Chiều dài cơ sở",
      "value": "2730",
      "unit": "mm",
      "edition": null,
      "bbox": [150, 50, 200, 950]
    },
    {
      "category": "Động cơ",
      "attribute": "Công suất tối đa",
      "value": "150",
      "unit": "kW",
      "edition": "Plus",
      "bbox": [280, 50, 320, 950]
    }
  ],
  "footnotes": [
    {
      "text": "(*) Quãng đường di chuyển theo chuẩn NEDC / WLTP được đo trong điều kiện thử nghiệm tiêu chuẩn.",
      "bbox": [900, 50, 980, 950]
    }
  ]
}
"""


class VisionExtractor:
    def __init__(self, doc_id: str, model: Optional[str] = None):
        self.doc_id = doc_id
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        # Use gpt-5.6-luna for multimodal vision tasks
        if model:
            raw_model = model
        else:
            raw_model = (
                os.environ.get("VISION_LLM_MODEL")
                or os.environ.get("LLM_MODEL")
                or os.environ.get("OPENAI_CHAT_MODEL")
                or "gpt-5.6-luna"
            )
        self.model = raw_model.split("/")[-1] if "/" in raw_model else raw_model
        if "mini" in self.model:
            self.model = "gpt-5.6-luna"  # ensure full vision fidelity for technical specs

    def _encode_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _convert_bbox_1000(self, box_1000: List[float], page_size: Dict[str, float]) -> BBox:
        """Convert [ymin, xmin, ymax, xmax] on 0-1000 scale to PDF points BBox."""
        if not box_1000 or len(box_1000) != 4:
            return BBox(x1=0, y1=0, x2=page_size["width"], y2=page_size["height"], page_size=page_size)

        ymin, xmin, ymax, xmax = box_1000
        pw = page_size["width"]
        ph = page_size["height"]

        x1 = max(0.0, min(pw, (xmin / 1000.0) * pw))
        y1 = max(0.0, min(ph, (ymin / 1000.0) * ph))
        x2 = max(0.0, min(pw, (xmax / 1000.0) * pw))
        y2 = max(0.0, min(ph, (ymax / 1000.0) * ph))

        return BBox(x1=round(x1, 1), y1=round(y1, 1), x2=round(x2, 1), y2=round(y2, 1), page_size=page_size)

    def extract_page(
        self,
        image_path: Path,
        page_num: int,
        page_size: Dict[str, float],
        source_url: str = "",
    ) -> List[CanonicalBlock]:
        """
        Send page image to Multimodal Vision LLM and assemble CanonicalBlocks.
        """
        if not self.api_key:
            print("[VisionExtractor] Warning: OPENAI_API_KEY not set, skipping Vision extraction.")
            return []

        base64_image = self._encode_image(image_path)
        messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Extract all technical specifications, table cells, and footnotes from Page {page_num} of VinFast brochure.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            },
        ]

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        # Reasoning models (gpt-5.6-luna, o1, o3, etc.) reject temperature != 1.0
        _model_lower = self.model.lower()
        if not any(k in _model_lower for k in ("luna", "o1", "o3", "reasoning", "gpt-5")):
            payload["temperature"] = 0.0

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
            if resp.status_code != 200:
                print(f"[VisionExtractor] API call HTTP {resp.status_code} on page {page_num}: {resp.text[:200]}")
            resp.raise_for_status()
            data = resp.json()["choices"][0]["message"]["content"]
            cleaned_data = data.strip()
            if "```json" in cleaned_data:
                cleaned_data = cleaned_data.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned_data:
                cleaned_data = cleaned_data.split("```")[1].split("```")[0].strip()
            parsed = json.loads(cleaned_data)
        except Exception as e:
            print(f"[VisionExtractor] API call failed on page {page_num}: {e}")
            return []

        blocks: List[CanonicalBlock] = []
        block_idx = 1

        # 1. Heading block
        heading_text = parsed.get("heading")
        if heading_text:
            h_bbox = self._convert_bbox_1000(parsed.get("heading_bbox", [50, 50, 100, 950]), page_size)
            h_block_id = f"p{page_num:02d}_b{block_idx:02d}"
            blocks.append(
                CanonicalBlock(
                    block_id=h_block_id,
                    type="heading",
                    text=heading_text,
                    section=heading_text,
                    evidence=Evidence(
                        document_id=self.doc_id,
                        page=page_num,
                        bbox=h_bbox,
                        source_block=h_block_id,
                        deep_link=f"{source_url}#page={page_num}" if source_url else None,
                    ),
                    extraction=Provenance(
                        method="vision_table",
                        model=self.model,
                        confidence=0.98,
                    ),
                )
            )
            block_idx += 1

        # 2. Specs Table block
        raw_specs = parsed.get("specs", [])
        if raw_specs:
            t_block_id = f"p{page_num:02d}_b{block_idx:02d}"
            spec_items: List[SpecItem] = []

            # Compute overall table bounding box from individual item bboxes
            all_x1, all_y1, all_x2, all_y2 = [], [], [], []

            for item in raw_specs:
                item_bbox = self._convert_bbox_1000(item.get("bbox", []), page_size)
                all_x1.append(item_bbox.x1)
                all_y1.append(item_bbox.y1)
                all_x2.append(item_bbox.x2)
                all_y2.append(item_bbox.y2)

                cat = str(item.get("category") or "Thông số chung").strip()
                attr = str(item.get("attribute") or "").strip()
                val = item.get("value")
                unit = item.get("unit")
                edition = item.get("edition")

                if not attr or val is None:
                    continue

                spec_items.append(
                    SpecItem(
                        category=cat,
                        attribute=attr,
                        value=val,
                        unit=unit if unit else None,
                        edition=edition if edition else None,
                        evidence=Evidence(
                            document_id=self.doc_id,
                            page=page_num,
                            bbox=item_bbox,
                            source_block=t_block_id,
                            deep_link=f"{source_url}#page={page_num}" if source_url else None,
                        ),
                        validation=ValidationResult(
                            structural=True,
                            visual=True,
                            semantic=True,
                            confidence=0.96,
                        ),
                        provenance=Provenance(
                            method="vision_table",
                            model=self.model,
                            confidence=0.96,
                        ),
                    )
                )

            table_bbox = BBox(
                x1=min(all_x1) if all_x1 else 50.0,
                y1=min(all_y1) if all_y1 else 100.0,
                x2=max(all_x2) if all_x2 else page_size["width"] - 50.0,
                y2=max(all_y2) if all_y2 else page_size["height"] - 100.0,
                page_size=page_size,
            )

            blocks.append(
                CanonicalBlock(
                    block_id=t_block_id,
                    type="table",
                    items=spec_items,
                    section=heading_text,
                    evidence=Evidence(
                        document_id=self.doc_id,
                        page=page_num,
                        bbox=table_bbox,
                        source_block=t_block_id,
                        deep_link=f"{source_url}#page={page_num}" if source_url else None,
                    ),
                    extraction=Provenance(
                        method="vision_table",
                        model=self.model,
                        confidence=0.96,
                    ),
                )
            )
            block_idx += 1

        # 3. Footnotes
        for fn in parsed.get("footnotes", []):
            fn_text = fn.get("text", "").strip()
            if not fn_text:
                continue
            fn_block_id = f"p{page_num:02d}_b{block_idx:02d}"
            fn_bbox = self._convert_bbox_1000(fn.get("bbox", [900, 50, 980, 950]), page_size)
            blocks.append(
                CanonicalBlock(
                    block_id=fn_block_id,
                    type="footnote",
                    text=fn_text,
                    section=heading_text,
                    evidence=Evidence(
                        document_id=self.doc_id,
                        page=page_num,
                        bbox=fn_bbox,
                        source_block=fn_block_id,
                        deep_link=f"{source_url}#page={page_num}" if source_url else None,
                    ),
                    extraction=Provenance(
                        method="vision_table",
                        model=self.model,
                        confidence=0.92,
                    ),
                )
            )
            block_idx += 1

        return blocks
