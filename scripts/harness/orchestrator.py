#!/usr/bin/env python3
"""
orchestrator.py — Master Orchestrator for Agentic Document Ingestion Harness.

Coordinates:
1. Inspection & Page Signal Analysis (PDFInspector)
2. Strategy Planning (ExtractionPlanner)
3. Specialized Extraction (PyMuPDF, Vision Extractor)
4. Normalization (TableNormalizer)
5. Evidence Cropping (CropGenerator)
6. Multi-Layer Validation (MultiLayerValidator)
7. Canonical Document Assembly & Saving (data_v2/canonical/{doc_id}.json)
8. Downstream Preview Export (data_v2/structured/ & data_v2/retrieval/)

Usage:
    python -m scripts.harness.orchestrator --pdf data_v2/raw_pdf/vf6_brochure.pdf --doc-id vf6_brochure --model-code "VF 6" --output-dir data_v2
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import fitz

from scripts.harness.crop_generator import CropGenerator
from scripts.harness.extractors.pymupdf import PyMuPDFExtractor
from scripts.harness.extractors.vision import VisionExtractor
from scripts.harness.inspector import PDFInspector
from scripts.harness.normalizers.table import TableNormalizer
from scripts.harness.planner import ExtractionPlanner
from scripts.harness.schemas import (
    CanonicalBlock,
    CanonicalDocument,
    CanonicalPage,
    DocumentMetadata,
)
from scripts.harness.sinks.postgres import PostgresSpecsSink
from scripts.harness.sinks.qdrant import QdrantChunksSink
from scripts.harness.validators.multi_layer import MultiLayerValidator


class DocumentHarnessOrchestrator:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.inspector = PDFInspector(self.output_dir)
        self.planner = ExtractionPlanner()
        self.crop_generator = CropGenerator(self.output_dir)
        self.validator = MultiLayerValidator()
        self.normalizer = TableNormalizer()
        self.postgres_sink = PostgresSpecsSink(self.output_dir)
        self.qdrant_sink = QdrantChunksSink(self.output_dir)

    def process_pdf(
        self,
        pdf_path: Path,
        doc_id: str = "vf6_brochure",
        model_code: str = "VF 6",
        source_url: str = "",
        page_range: Optional[List[int]] = None,
    ) -> CanonicalDocument:
        """
        Execute the full ingestion harness on a PDF document.
        """
        t0 = time.time()
        pdf_path = Path(pdf_path)
        print(f"\n{'='*72}\n[HARNESS] INGESTION START: {pdf_path.name} (model: {model_code})\n{'='*72}")

        # 1. Inspection & Rendering
        print("\n[Step 1/6] Inspecting PDF & Rendering high-resolution page images...")
        signals_list, rendered_images = self.inspector.inspect_pdf(pdf_path, doc_id=doc_id)
        print(f"  -> Analyzed {len(signals_list)} pages, rendered images saved to data_v2/artifacts/{doc_id}/pages/")

        # 2. Strategy Planning
        print("\n[Step 2/6] Planning extraction strategies per page...")
        plan = self.planner.plan_document(signals_list)
        for p_num, strat in sorted(plan.items()):
            sig = signals_list[p_num - 1]
            print(f"  Page {p_num:02d}: type={sig.page_type:<15} overlap={sig.overlap_ratio:.2f} -> Strategy: {strat}")

        # 3. Execution
        print("\n[Step 3/6] Extracting blocks using specialized extractors...")
        doc_fitz = fitz.open(pdf_path)
        pymupdf_ext = PyMuPDFExtractor(doc_id=doc_id)
        vision_ext = VisionExtractor(doc_id=doc_id)

        canonical_pages: List[CanonicalPage] = []
        pages_to_process = page_range if page_range else list(range(1, len(doc_fitz) + 1))

        for p_num in pages_to_process:
            page_idx = p_num - 1
            fitz_page = doc_fitz[page_idx]
            rect = fitz_page.rect
            page_size = {"width": float(rect.width), "height": float(rect.height)}
            img_path = rendered_images[page_idx]
            strategy = plan.get(p_num, "pymupdf")
            signals = signals_list[page_idx]

            print(f"  Processing Page {p_num:02d} ({strategy})...", end="", flush=True)

            blocks: List[CanonicalBlock] = []
            if strategy in ("vision_table", "vision_prose"):
                blocks = vision_ext.extract_page(
                    image_path=img_path,
                    page_num=p_num,
                    page_size=page_size,
                    source_url=source_url,
                )
                # Fallback to PyMuPDF if Vision returned empty
                if not blocks:
                    print(" (Vision empty -> fallback PyMuPDF)", end="", flush=True)
                    blocks = pymupdf_ext.extract_page(
                        page=fitz_page,
                        page_num=p_num,
                        source_url=source_url,
                    )
            else:
                blocks = pymupdf_ext.extract_page(
                    page=fitz_page,
                    page_num=p_num,
                    source_url=source_url,
                )

            # 4. Normalization of table specs
            for b in blocks:
                if b.items:
                    normalized_items = []
                    for item in b.items:
                        normalized_items.extend(self.normalizer.normalize_spec_item(item))
                    b.items = normalized_items

            # 5. Crop visual evidence
            for b in blocks:
                if b.evidence and b.evidence.bbox:
                    crop_path = self.crop_generator.crop_block(
                        page_image_path=img_path,
                        bbox=b.evidence.bbox,
                        doc_id=doc_id,
                        block_id=b.block_id,
                    )
                    if crop_path:
                        b.evidence.crop_path = str(crop_path.as_posix())

            # 6. Validation
            canonical_page = CanonicalPage(
                page_number=p_num,
                page_size=page_size,
                image_path=str(img_path.as_posix()),
                signals=signals,
                blocks=blocks,
            )
            canonical_page = self.validator.validate_page(canonical_page)
            canonical_pages.append(canonical_page)
            print(f" -> Extracted {len(blocks)} blocks")

        doc_fitz.close()

        # 7. Assemble Master Canonical Document
        meta = DocumentMetadata(
            id=doc_id,
            source_file=str(pdf_path.name),
            source_url=source_url,
            model_code=model_code,
            total_pages=len(signals_list),
        )
        canonical_doc = CanonicalDocument(document=meta, pages=canonical_pages)

        # Save Canonical JSON
        canonical_dir = self.output_dir / "canonical"
        canonical_dir.mkdir(parents=True, exist_ok=True)
        canonical_path = canonical_dir / f"{doc_id}.json"
        with open(canonical_path, "w", encoding="utf-8") as f:
            f.write(canonical_doc.model_dump_json(indent=2))

        print(f"\n[Step 4/6] Saved Canonical Document: {canonical_path}")

        # 8. Export Structured Specs & Retrieval Chunks Previews
        print("\n[Step 5/6] Exporting Downstream Previews (Postgres Specs & Qdrant Chunks)...")
        json_spec, csv_spec = self.postgres_sink.export_preview(canonical_doc)
        chunk_jsonl = self.qdrant_sink.export_preview(canonical_doc)
        print(f"  -> Structured Specs: {json_spec} and {csv_spec}")
        print(f"  -> Retrieval Chunks: {chunk_jsonl}")

        # 9. Summary Report
        all_blocks = canonical_doc.get_all_blocks()
        all_specs = canonical_doc.get_all_spec_items()
        dt = time.time() - t0

        print(f"\n{'='*72}\n[HARNESS] EXECUTION FINISHED in {dt:.1f}s")
        print(f"  • Total Pages: {len(canonical_pages)}")
        print(f"  • Total Blocks: {len(all_blocks)}")
        print(f"  • Total Spec Items Extracted: {len(all_specs)}")
        print(f"{'='*72}\n")

        return canonical_doc


def main():
    parser = argparse.ArgumentParser(description="Agentic Document Ingestion Harness")
    parser.add_argument("--pdf", default="data_v2/raw_pdf/vf6_brochure.pdf", help="Path to PDF file")
    parser.add_argument("--doc-id", default="vf6_brochure", help="Document ID")
    parser.add_argument("--model-code", default="VF 6", help="Model code (e.g. VF 6)")
    parser.add_argument(
        "--source-url",
        default="https://xeotovinfast.com.vn/wp-content/uploads/2024/03/VF6_Brochure_VN.pdf",
        help="Source PDF URL for citations",
    )
    parser.add_argument("--output-dir", default="data_v2", help="Target output folder")
    parser.add_argument("--pages", default=None, help="Comma-separated page numbers or range (e.g. 1-20 or 12)")
    args = parser.parse_args()

    page_range = None
    if args.pages:
        if "-" in args.pages:
            start, end = args.pages.split("-")
            page_range = list(range(int(start), int(end) + 1))
        else:
            page_range = [int(p.strip()) for p in args.pages.split(",")]

    orchestrator = DocumentHarnessOrchestrator(output_dir=Path(args.output_dir))
    orchestrator.process_pdf(
        pdf_path=Path(args.pdf),
        doc_id=args.doc_id,
        model_code=args.model_code,
        source_url=args.source_url,
        page_range=page_range,
    )


if __name__ == "__main__":
    main()
