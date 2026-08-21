#!/usr/bin/env python3
"""
crop_generator.py — Visual Evidence Crop Generator.

Takes rendered high-res page images and BBox coordinates in PDF points,
transforms them into pixel coordinates, and crops the visual evidence block.
"""

from pathlib import Path
from typing import Optional
from PIL import Image

from scripts.harness.schemas import BBox


class CropGenerator:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def crop_block(
        self,
        page_image_path: Path,
        bbox: BBox,
        doc_id: str,
        block_id: str,
        padding_px: int = 10,
    ) -> Optional[Path]:
        """
        Crop a sub-region of a rendered page image corresponding to a bounding box.
        Returns:
            Path to the saved crop image, or None if failed.
        """
        page_image_path = Path(page_image_path)
        if not page_image_path.exists():
            return None

        crops_dir = self.output_dir / "artifacts" / doc_id / "crops"
        crops_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crops_dir / f"{block_id}.png"

        try:
            with Image.open(page_image_path) as img:
                img_width, img_height = img.size

                # Get original page size in PDF points (default standard letter/A4 if not set)
                page_w = bbox.page_size.get("width", 842.0) if bbox.page_size else 842.0
                page_h = bbox.page_size.get("height", 595.0) if bbox.page_size else 595.0

                scale_x = img_width / max(1.0, page_w)
                scale_y = img_height / max(1.0, page_h)

                # Transform PDF points to image pixels
                px_x1 = max(0, int(bbox.x1 * scale_x) - padding_px)
                px_y1 = max(0, int(bbox.y1 * scale_y) - padding_px)
                px_x2 = min(img_width, int(bbox.x2 * scale_x) + padding_px)
                px_y2 = min(img_height, int(bbox.y2 * scale_y) + padding_px)

                if px_x2 <= px_x1 or px_y2 <= px_y1:
                    return None

                cropped = img.crop((px_x1, px_y1, px_x2, px_y2))
                cropped.save(crop_path, format="PNG")
                return crop_path
        except Exception as e:
            print(f"[CropGenerator] Error cropping {block_id}: {e}")
            return None
