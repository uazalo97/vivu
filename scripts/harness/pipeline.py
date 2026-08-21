#!/usr/bin/env python3
"""
pipeline.py — Master Execution Pipeline for Unified Ingestion Harness.
Single entrypoint to extract, normalize, chunk, and ingest all VinFast data into PostgreSQL & Qdrant.

Usage:
    python -m scripts.harness.pipeline --version v3 --recreate
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scripts.harness.batch_runner import run_brochure_batch
from scripts.harness.config import DATA_V2_DIR, PG_DSN, QDRANT_URL, RETRIEVAL_DIR, STRUCTURED_DIR
from scripts.harness.extractors.configurator import ConfiguratorExtractor
from scripts.harness.extractors.web_text import WebTextExtractor
from scripts.harness.sinks.postgres import PostgresSink
from scripts.harness.sinks.qdrant import QdrantSink


def _banner(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def run_pipeline(
    version: str = "v3",
    recreate: bool = False,
    skip_brochures: bool = False,
    skip_configurator: bool = False,
    skip_web: bool = False,
    no_ingest_db: bool = False,
    force: bool = False,
) -> int:
    t_start = time.time()
    _banner(f"UNIFIED INGESTION HARNESS — RUN PIPELINE (VERSION: {version})")
    print(f"Target Version:    {version} (Safe test mode: is_current = False)")
    print(f"Recreate DB/Vec:   {recreate}")
    print(f"PostgreSQL DSN:    {PG_DSN}")
    print(f"Qdrant URL:        {QDRANT_URL}")

    # Initialize Sinks
    postgres_sink = PostgresSink(output_dir=STRUCTURED_DIR, dsn=PG_DSN)
    qdrant_sink = QdrantSink(output_dir=RETRIEVAL_DIR, url=QDRANT_URL)

    # ── Phase 1: Configurator Data (Editions, Prices, Colors, Options) ──────
    if not skip_configurator:
        _banner("[Phase 1/5] Extracting & Normalizing Car Configurator Data...")
        conf_ext = ConfiguratorExtractor()
        editions, prices, colors, options = conf_ext.extract_and_normalize()
        print(f"  ✓ Processed {len(editions)} editions, {len(prices)} price rows, {len(colors)} colors, {len(options)} options.")
    else:
        print("\n>>> Skipping Phase 1 (Configurator Data).")

    # ── Phase 2: PDF Brochures Extraction (9 Vehicle Models) ────────────────
    if not skip_brochures:
        _banner("[Phase 2/5] Processing PDF Brochures through Document Harness...")
        brochure_res = run_brochure_batch(data_dir=DATA_V2_DIR, skip_existing=not force, force=force)
        print(f"  ✓ Brochure Ingestion complete ({brochure_res.get('duration', 0):.1f}s).")
    else:
        print("\n>>> Skipping Phase 2 (PDF Brochures).")

    # ── Phase 3: Web Articles & Policy Text Extraction ──────────────────────
    web_chunks = []
    if not skip_web:
        _banner("[Phase 3/5] Extracting Web Policies, Maintenance & FAQ texts...")
        web_ext = WebTextExtractor()
        web_chunks = web_ext.extract_all_web_chunks()
        print(f"  ✓ Extracted {len(web_chunks)} semantic chunks from web/policy files.")
    else:
        print("\n>>> Skipping Phase 3 (Web Policies).")

    # ── Phase 4: Consolidating Retrieval Datasets ───────────────────────────
    _banner("[Phase 4/5] Consolidating Retrieval Datasets & Manifest...")
    chunk_files = qdrant_sink.consolidate_all_chunks(web_chunks)
    for col, p in chunk_files.items():
        print(f"  ✓ Collection {col}: {p}")

    master_json, master_csv = postgres_sink.consolidate_all_specs()
    print(f"  ✓ Master Specs Dataset: {master_json} and {master_csv}")

    # ── Phase 5: Database & Vector Ingestion ────────────────────────────────
    if not no_ingest_db:
        _banner(f"[Phase 5/5] Ingesting to PostgreSQL & Qdrant for Version '{version}'...")

        print("\n[5.1] Ingesting Structured Data to PostgreSQL...")
        pg_stats = postgres_sink.ingest_to_postgres(version=version)
        for tbl, count in pg_stats.items():
            print(f"  ✓ PostgreSQL Table '{tbl}': {count} rows upserted.")

        print("\n[5.2] Embedding & Ingesting Chunks to Qdrant...")
        qdrant_stats = qdrant_sink.ingest_to_qdrant(version=version, recreate=recreate)
        for col, count in qdrant_stats.items():
            print(f"  ✓ Qdrant Collection '{col}': {count} points ingested.")
    else:
        print("\n>>> Skipping Phase 5 (Database Ingestion - Preview Only).")

    # ── Final Summary ───────────────────────────────────────────────────────
    total_dt = time.time() - t_start
    _banner(f"PIPELINE COMPLETED SUCCESSFULLY in {total_dt:.1f}s (Version: {version})")
    print(f"  • Safe Mode: Version '{version}' ingested with is_current=False (Active version remains unchanged).")
    print(f"  • To check status: python scripts/version_manager.py status")
    print(f"  • To activate:     python scripts/version_manager.py promote --version {version}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Unified Ingestion Harness Pipeline")
    parser.add_argument("--version", default="v3", help="Target version identifier (default: v3)")
    parser.add_argument("--recreate", action="store_true", help="Recreate Qdrant collections cleanly")
    parser.add_argument("--skip-brochures", action="store_true", help="Skip brochure extraction")
    parser.add_argument("--skip-configurator", action="store_true", help="Skip configurator extraction")
    parser.add_argument("--skip-web", action="store_true", help="Skip web/policy text extraction")
    parser.add_argument("--no-ingest-db", action="store_true", help="Skip database ingestion (preview only)")
    parser.add_argument("--force", action="store_true", help="Force re-extraction of brochures")
    args = parser.parse_args()

    sys.exit(
        run_pipeline(
            version=args.version,
            recreate=args.recreate,
            skip_brochures=args.skip_brochures,
            skip_configurator=args.skip_configurator,
            skip_web=args.skip_web,
            no_ingest_db=args.no_ingest_db,
            force=args.force,
        )
    )


if __name__ == "__main__":
    main()
