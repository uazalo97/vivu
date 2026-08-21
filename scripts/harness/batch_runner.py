#!/usr/bin/env python3
"""
batch_runner.py — Batch Runner for Brochure Ingestion across all 9 VinFast models.
"""

import argparse
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scripts.harness.config import BROCHURE_CATALOG, DATA_V2_DIR
from scripts.harness.orchestrator import DocumentHarnessOrchestrator
from scripts.harness.sinks.postgres import PostgresSink


def download_file(url: str, dest_path: Path) -> bool:
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


def run_brochure_batch(
    data_dir: Path = DATA_V2_DIR,
    models_filter: Optional[List[str]] = None,
    skip_existing: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    t_start = time.time()
    raw_pdf_dir = data_dir / "raw" / "pdf"
    canonical_dir = data_dir / "canonical"
    raw_pdf_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir.mkdir(parents=True, exist_ok=True)

    orchestrator = DocumentHarnessOrchestrator(output_dir=data_dir)
    postgres_sink = PostgresSink(output_dir=data_dir / "structured")

    print("\n" + "=" * 80)
    print("AGENTIC DOCUMENT INGESTION HARNESS — BROCHURE BATCH RUNNER")
    if models_filter:
        print(f"Target Models Filter: {', '.join(models_filter)}")
    print(f"Skip Existing: {skip_existing} (Force: {force})")
    print("=" * 80)

    stats = []

    for item in BROCHURE_CATALOG:
        m_code = item["model_code"]
        doc_id = item["doc_id"]
        url = item["url"]
        pdf_name = item.get("pdf_name", f"{doc_id}.pdf")
        pdf_path = raw_pdf_dir / pdf_name
        canonical_path = canonical_dir / f"{doc_id}.json"

        if models_filter:
            m_filter_lower = [f.strip().lower() for f in models_filter]
            doc_matches = any(
                f in doc_id.lower() or f in m_code.lower() or f == doc_id.replace("_brochure", "").lower()
                for f in m_filter_lower
            )
            if not doc_matches:
                continue

        if skip_existing and not force and canonical_path.exists() and canonical_path.stat().st_size > 100:
            print(f"\n>>> [SKIPPED - ALREADY EXISTS] {m_code} ({doc_id})")
            stats.append({"model": m_code, "status": "ALREADY_EXISTS"})
            continue

        print(f"\n>>> PROCESSING BROCHURE: {m_code} ({doc_id})")
        if not download_file(url, pdf_path):
            print(f"Skipping {m_code} due to download error.")
            stats.append({"model": m_code, "status": "DOWNLOAD_FAILED"})
            continue

        try:
            canonical_doc = orchestrator.process_pdf(
                pdf_path=pdf_path,
                doc_id=doc_id,
                model_code=m_code,
                source_url=url,
            )
            stats.append(
                {
                    "model": m_code,
                    "status": "SUCCESS",
                    "pages": len(canonical_doc.pages),
                    "specs": len(canonical_doc.get_all_spec_items()),
                }
            )
        except Exception as e:
            print(f"[ERROR] Failed processing {m_code}: {e}")
            stats.append({"model": m_code, "status": "ERROR", "error": str(e)})

    # Consolidate all specs
    master_json, master_csv = postgres_sink.consolidate_all_specs()
    print(f"\n[Consolidation] Saved Master Specs: {master_json} and {master_csv}")

    total_time = time.time() - t_start
    print(f"\nBrochure Batch finished in {total_time:.1f}s")
    return {"status": "DONE", "duration": total_time, "stats": stats}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--filter", nargs="+", help="Filter models (e.g. vf3 vf6)")
    parser.add_argument("--force", action="store_true", help="Force re-extraction")
    args = parser.parse_args()
    run_brochure_batch(models_filter=args.filter, skip_existing=not args.force, force=args.force)
