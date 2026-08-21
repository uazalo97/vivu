#!/usr/bin/env python3
"""
batch_runner.py — Batch Runner for Agentic Document Ingestion Harness across all VinFast models.

Downloads and processes 9 VinFast brochure PDFs into data_v2/:
- VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 8 All New, VF 9, VF MPV 7
Consolidates all structured specs and retrieval chunks into unified datasets.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from scripts.harness.orchestrator import DocumentHarnessOrchestrator
from scripts.harness.schemas import CanonicalDocument

BROCHURE_CATALOG = [
    {
        "model_code": "VF 2",
        "doc_id": "vf2_brochure",
        "url": "https://static-cms-prod.vinfastauto.com/brochure_vf_2.pdf",
    },
    {
        "model_code": "VF 3",
        "doc_id": "vf3_brochure",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/29012026/VFVN_VF%203_Brochure%20280126.pdf",
    },
    {
        "model_code": "VF 5",
        "doc_id": "vf5_brochure",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/09042026/VFVN_VF%205_Brochure%20B%E1%BA%A3n%20s%E1%BB%ADa%20290126_1333PM.pdf",
    },
    {
        "model_code": "VF 6",
        "doc_id": "vf6_brochure",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/14052026/VF%206_Brochure_Final_130526%20(12AM)_compressed.pdf",
    },
    {
        "model_code": "VF 7",
        "doc_id": "vf7_brochure",
        "url": "https://vinfastnamtuliem.vn/wp-content/uploads/2025/02/VF7_Brochure_T062025.pdf",
    },
    {
        "model_code": "VF 8",
        "doc_id": "vf8_brochure",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/VF8_Brochure_03022026.pdf",
    },
    {
        "model_code": "VF 8 All New",
        "doc_id": "vf8_all_new_brochure",
        "url": "https://static-cms-prod.vinfastauto.com/brochure/26052026/VF%208%20The%20he%20moi_Brochure_final%2020.05.pdf",
    },
    {
        "model_code": "VF 9",
        "doc_id": "vf9_brochure",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/VF%209_%20Brochure.pdf",
    },
    {
        "model_code": "VF MPV 7",
        "doc_id": "vf_mpv7_brochure",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/VF_MPV%207_Brochure_2026.02.03.pdf",
    },
]


def download_file(url: str, dest_path: Path) -> bool:
    """Download a PDF brochure file if not already present."""
    if dest_path.exists() and dest_path.stat().st_size > 1000:
        return True
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {url} -> {dest_path.name}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
        print(f"  [OK] Downloaded {dest_path.stat().st_size} bytes")
        return True
    except Exception as e:
        print(f"  [ERROR] Download failed: {e}")
        return False


def run_batch(
    output_dir: str = "data_v2",
    models_filter: Optional[List[str]] = None,
    skip_existing: bool = True,
    force: bool = False,
) -> None:
    t_start = time.time()
    out_dir = Path(output_dir)
    raw_pdf_dir = out_dir / "raw_pdf"
    canonical_dir = out_dir / "canonical"
    raw_pdf_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir.mkdir(parents=True, exist_ok=True)

    orchestrator = DocumentHarnessOrchestrator(output_dir=out_dir)

    all_specs_rows: List[Dict[str, Any]] = []
    all_chunks_lines: List[str] = []
    summary_stats = []

    print("\n" + "=" * 80)
    print("AGENTIC DOCUMENT INGESTION HARNESS — BATCH RUNNER")
    if models_filter:
        print(f"Target Models Filter: {', '.join(models_filter)}")
    print(f"Skip Existing: {skip_existing} (Force: {force})")
    print("=" * 80)

    for item in BROCHURE_CATALOG:
        m_code = item["model_code"]
        doc_id = item["doc_id"]
        url = item["url"]
        pdf_path = raw_pdf_dir / f"{doc_id}.pdf"
        canonical_path = canonical_dir / f"{doc_id}.json"

        # Check if filter applied
        if models_filter:
            m_filter_lower = [f.strip().lower() for f in models_filter]
            doc_matches = any(
                f in doc_id.lower() or f in m_code.lower() or f == doc_id.replace("_brochure", "").lower()
                for f in m_filter_lower
            )
            if not doc_matches:
                # Still load existing specs/chunks for master consolidation if available
                json_spec_path = out_dir / "structured" / f"{doc_id}_specs.json"
                if json_spec_path.exists():
                    with open(json_spec_path, "r", encoding="utf-8") as f:
                        all_specs_rows.extend(json.load(f))
                chunks_path = out_dir / "retrieval" / f"{doc_id}_chunks.jsonl"
                if chunks_path.exists():
                    with open(chunks_path, "r", encoding="utf-8") as f:
                        all_chunks_lines.extend([line.strip() for line in f if line.strip()])
                continue

        # Check if already processed
        if skip_existing and not force and canonical_path.exists() and canonical_path.stat().st_size > 100:
            print(f"\n>>> [SKIPPED - ALREADY EXISTS] {m_code} ({doc_id})")
            json_spec_path = out_dir / "structured" / f"{doc_id}_specs.json"
            spec_count = 0
            if json_spec_path.exists():
                with open(json_spec_path, "r", encoding="utf-8") as f:
                    specs = json.load(f)
                    spec_count = len(specs)
                    all_specs_rows.extend(specs)

            chunks_path = out_dir / "retrieval" / f"{doc_id}_chunks.jsonl"
            if chunks_path.exists():
                with open(chunks_path, "r", encoding="utf-8") as f:
                    all_chunks_lines.extend([line.strip() for line in f if line.strip()])

            try:
                with open(canonical_path, "r", encoding="utf-8") as f:
                    c_doc = json.load(f)
                    page_count = len(c_doc.get("pages", []))
            except Exception:
                page_count = 0

            summary_stats.append(
                {"model": m_code, "status": "ALREADY_EXISTS", "pages": page_count, "specs": spec_count}
            )
            continue

        print(f"\n>>> PROCESSING: {m_code} ({doc_id})")

        # 1. Download PDF
        if not download_file(url, pdf_path):
            print(f"Skipping {m_code} due to download error.")
            summary_stats.append({"model": m_code, "status": "DOWNLOAD_FAILED", "pages": 0, "specs": 0})
            continue

        # 2. Run Ingestion Harness
        try:
            canonical_doc = orchestrator.process_pdf(
                pdf_path=pdf_path,
                doc_id=doc_id,
                model_code=m_code,
                source_url=url,
            )

            # Collect specs preview rows
            json_spec_path = out_dir / "structured" / f"{doc_id}_specs.json"
            if json_spec_path.exists():
                with open(json_spec_path, "r", encoding="utf-8") as f:
                    all_specs_rows.extend(json.load(f))

            # Collect retrieval chunks
            chunks_path = out_dir / "retrieval" / f"{doc_id}_chunks.jsonl"
            if chunks_path.exists():
                with open(chunks_path, "r", encoding="utf-8") as f:
                    all_chunks_lines.extend([line.strip() for line in f if line.strip()])

            n_pages = len(canonical_doc.pages)
            n_specs = len(canonical_doc.get_all_spec_items())
            summary_stats.append({"model": m_code, "status": "SUCCESS", "pages": n_pages, "specs": n_specs})

        except Exception as exc:
            print(f"[ERROR] Failed processing {m_code}: {exc}")
            summary_stats.append({"model": m_code, "status": f"FAILED: {exc}", "pages": 0, "specs": 0})

    # 3. Consolidate Master Datasets
    print("\n" + "=" * 80)
    print("CONSOLIDATING ALL-MODELS MASTER DATASETS IN data_v2/")
    print("=" * 80)

    # Master Specs JSON
    master_specs_json = out_dir / "structured" / "all_models_specs.json"
    with open(master_specs_json, "w", encoding="utf-8") as f:
        json.dump(all_specs_rows, f, ensure_ascii=False, indent=2)

    # Master Specs CSV
    master_specs_csv = out_dir / "structured" / "all_models_specs.csv"
    if all_specs_rows:
        fieldnames = [
            "model_code",
            "version_name",
            "spec_category",
            "spec_key",
            "spec_value",
            "spec_unit",
            "source_document",
            "source_url",
            "source_page",
            "source_bbox",
            "source_block_id",
            "confidence",
        ]
        with open(master_specs_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="|")
            writer.writeheader()
            for r in all_specs_rows:
                writer.writerow(
                    {
                        k: (json.dumps(r[k]) if isinstance(r[k], list) else ("" if r[k] is None else r[k]))
                        for k in fieldnames
                    }
                )

    # Master Chunks JSONL
    master_chunks_jsonl = out_dir / "retrieval" / "all_models_chunks.jsonl"
    with open(master_chunks_jsonl, "w", encoding="utf-8") as f:
        for line in all_chunks_lines:
            f.write(line + "\n")

    print(f"  [OK] Master Specs JSON: {master_specs_json} ({len(all_specs_rows)} total rows)")
    print(f"  [OK] Master Specs CSV:  {master_specs_csv}")
    print(f"  [OK] Master Chunks JSONL: {master_chunks_jsonl} ({len(all_chunks_lines)} total chunks)")

    dt = time.time() - t_start
    print("\n" + "=" * 80)
    print(f"BATCH INGESTION COMPLETE in {dt:.1f}s")
    print("=" * 80)
    print(f"{'MODEL':<18} | {'STATUS':<15} | {'PAGES':<8} | {'SPECS EXTRACTED':<15}")
    print("-" * 65)
    for s in summary_stats:
        print(f"{s['model']:<18} | {s['status']:<15} | {s['pages']:<8} | {s['specs']:<15}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Batch Runner for Ingestion Harness")
    parser.add_argument("--output-dir", default="data_v2", help="Target output directory")
    parser.add_argument(
        "--models",
        default=None,
        help="Comma-separated model names or doc_ids to process (e.g. 'vf5,vf7,vf8,vf8_all_new,vf9,vf_mpv7')",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip models whose canonical data already exists in data_v2/canonical/",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-extraction even if canonical files exist",
    )
    args = parser.parse_args()

    models_filter = [m.strip() for m in args.models.split(",")] if args.models else None
    run_batch(
        output_dir=args.output_dir,
        models_filter=models_filter,
        skip_existing=args.skip_existing,
        force=args.force,
    )


if __name__ == "__main__":
    main()
