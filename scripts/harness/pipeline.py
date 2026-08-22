#!/usr/bin/env python3
"""
pipeline.py — Master Execution Pipeline for Unified Ingestion Harness.
Single entrypoint to extract, normalize, chunk, and ingest all VinFast data into PostgreSQL & Qdrant.

Usage:
    python -m scripts.harness.pipeline --version v3 --recreate
    python -m scripts.harness.pipeline --version v3 --resume
"""

import argparse
import json
import sys
import time

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
    resume: bool = False,
) -> int:
    t_start = time.time()
    _banner(f"UNIFIED INGESTION HARNESS — RUN PIPELINE (VERSION: {version})")
    print(f"Target Version:    {version} (Safe test mode: is_current = False)")
    print(f"Recreate DB/Vec:   {recreate} Resume: {resume}")
    print(f"PostgreSQL DSN:    {PG_DSN}")
    print(f"Qdrant URL:        {QDRANT_URL}")

    # C7 fix: phase status tracking for resume and error isolation
    phase_status = {}
    status_file = DATA_V2_DIR / f"phase_status__{version}.json"
    if resume and status_file.exists():
        try:
            phase_status = json.loads(status_file.read_text(encoding="utf-8"))
            print(f"[RESUME] Loaded previous phase status: {phase_status}")
        except Exception:
            phase_status = {}

    def _save_status():
        try:
            status_file.parent.mkdir(parents=True, exist_ok=True)
            status_file.write_text(json.dumps(phase_status, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[WARN] Failed to save phase status: {e}")

    def _should_run(phase: str) -> bool:
        if not resume:
            return True
        return phase_status.get(phase) != "success"

    # Initialize Sinks
    postgres_sink = PostgresSink(output_dir=STRUCTURED_DIR, dsn=PG_DSN)
    qdrant_sink = QdrantSink(output_dir=RETRIEVAL_DIR, url=QDRANT_URL)

    # ── Phase 1: Configurator Data (Editions, Prices, Colors, Options) ──────
    if not skip_configurator:
        if not _should_run("phase1_configurator"):
            print("\n[Phase 1/5] Skipped (already success, --resume)")
            phase_status["phase1_configurator"] = "skipped_resume"
        else:
            _banner("[Phase 1/5] Extracting & Normalizing Car Configurator Data...")
            try:
                conf_ext = ConfiguratorExtractor()
                editions, prices, colors, options = conf_ext.extract_and_normalize()
                print(
                    f"  ✓ Processed {len(editions)} editions, {len(prices)} price rows, {len(colors)} colors, {len(options)} options."
                )
                phase_status["phase1_configurator"] = "success"
            except Exception as e:
                print(f"  [ERROR] Phase 1 failed: {e}")
                import traceback

                traceback.print_exc()
                phase_status["phase1_configurator"] = f"failed: {e}"
            _save_status()
    else:
        print("\n>>> Skipping Phase 1 (Configurator Data).")
        phase_status["phase1_configurator"] = "skipped"

    # ── Phase 2: PDF Brochures Extraction (9 Vehicle Models) ────────────────
    if not skip_brochures:
        if not _should_run("phase2_brochures"):
            print("\n[Phase 2/5] Skipped (already success, --resume)")
            phase_status["phase2_brochures"] = "skipped_resume"
        else:
            _banner("[Phase 2/5] Processing PDF Brochures through Document Harness...")
            try:
                brochure_res = run_brochure_batch(data_dir=DATA_V2_DIR, skip_existing=not force, force=force)
                print(f"  ✓ Brochure Ingestion complete ({brochure_res.get('duration', 0):.1f}s).")
                phase_status["phase2_brochures"] = "success"
            except Exception as e:
                print(f"  [ERROR] Phase 2 failed: {e}")
                import traceback

                traceback.print_exc()
                phase_status["phase2_brochures"] = f"failed: {e}"
            _save_status()
    else:
        print("\n>>> Skipping Phase 2 (PDF Brochures).")
        phase_status["phase2_brochures"] = "skipped"

    # ── Phase 3: Web Articles & Policy Text Extraction ──────────────────────
    web_chunks = []
    if not skip_web:
        if not _should_run("phase3_web"):
            print(
                "\n[Phase 3/5] Skipped (already success, --resume) - loading cached web chunks from previous run is not persisted, will re-extract"
            )
            # still need to re-extract for consolidate; mark as success but re-run extraction
            # We choose to re-run web extraction even on resume because web_chunks not persisted
            _banner("[Phase 3/5] Extracting Web Policies, Maintenance & FAQ texts... (resume re-extract)")
            try:
                web_ext = WebTextExtractor()
                web_chunks = web_ext.extract_all_web_chunks()
                print(f"  ✓ Extracted {len(web_chunks)} semantic chunks from web/policy files.")
                phase_status["phase3_web"] = "success"
            except Exception as e:
                print(f"  [ERROR] Phase 3 failed: {e}")
                import traceback

                traceback.print_exc()
                phase_status["phase3_web"] = f"failed: {e}"
            _save_status()
        else:
            _banner("[Phase 3/5] Extracting Web Policies, Maintenance & FAQ texts...")
            try:
                web_ext = WebTextExtractor()
                web_chunks = web_ext.extract_all_web_chunks()
                print(f"  ✓ Extracted {len(web_chunks)} semantic chunks from web/policy files.")
                phase_status["phase3_web"] = "success"
            except Exception as e:
                print(f"  [ERROR] Phase 3 failed: {e}")
                import traceback

                traceback.print_exc()
                phase_status["phase3_web"] = f"failed: {e}"
                web_chunks = []
            _save_status()
    else:
        print("\n>>> Skipping Phase 3 (Web Policies).")
        phase_status["phase3_web"] = "skipped"
        _save_status()

    # ── Phase 4: Consolidating Retrieval Datasets ───────────────────────────
    _banner("[Phase 4/5] Consolidating Retrieval Datasets & Manifest...")
    try:
        chunk_files = qdrant_sink.consolidate_all_chunks(web_chunks)
        for col, p in chunk_files.items():
            print(f"  ✓ Collection {col}: {p}")

        master_json, master_csv = postgres_sink.consolidate_all_specs()
        print(f"  ✓ Master Specs Dataset: {master_json} and {master_csv}")
        phase_status["phase4_consolidate"] = "success"
    except Exception as e:
        print(f"  [ERROR] Phase 4 failed: {e}")
        import traceback

        traceback.print_exc()
        phase_status["phase4_consolidate"] = f"failed: {e}"
    _save_status()

    # ── Phase 5: Database & Vector Ingestion ────────────────────────────────
    if not no_ingest_db:
        _banner(f"[Phase 5/5] Ingesting to PostgreSQL & Qdrant for Version '{version}'...")

        # 5.1 PostgreSQL
        if not _should_run("phase5_postgres"):
            print("\n[5.1] Skipped PostgreSQL (already success, --resume)")
        else:
            print("\n[5.1] Ingesting Structured Data to PostgreSQL...")
            try:
                pg_stats = postgres_sink.ingest_to_postgres(version=version)
                for tbl, count in pg_stats.items():
                    print(f"  ✓ PostgreSQL Table '{tbl}': {count} rows upserted.")
                phase_status["phase5_postgres"] = "success"
            except Exception as e:
                print(f"  [ERROR] PostgreSQL ingestion failed: {e}")
                import traceback

                traceback.print_exc()
                phase_status["phase5_postgres"] = f"failed: {e}"
            _save_status()

        # 5.2 Qdrant
        if not _should_run("phase5_qdrant"):
            print("\n[5.2] Skipped Qdrant (already success, --resume)")
        else:
            print("\n[5.2] Embedding & Ingesting Chunks to Qdrant...")
            try:
                qdrant_stats = qdrant_sink.ingest_to_qdrant(version=version, recreate=recreate)
                for col, count in qdrant_stats.items():
                    print(f"  ✓ Qdrant Collection '{col}': {count} points ingested.")
                phase_status["phase5_qdrant"] = "success"
            except Exception as e:
                print(f"  [ERROR] Qdrant ingestion failed: {e}")
                import traceback

                traceback.print_exc()
                phase_status["phase5_qdrant"] = f"failed: {e}"
            _save_status()
    else:
        print("\n>>> Skipping Phase 5 (Database Ingestion - Preview Only).")
        phase_status["phase5_postgres"] = "skipped"
        phase_status["phase5_qdrant"] = "skipped"
        _save_status()

    # ── Final Summary ───────────────────────────────────────────────────────
    total_dt = time.time() - t_start
    has_failure = any("failed" in str(v) for v in phase_status.values())
    if has_failure:
        _banner(f"PIPELINE COMPLETED WITH ERRORS in {total_dt:.1f}s (Version: {version})")
        print("  Phase status:")
        for k, v in phase_status.items():
            print(f"    {k}: {v}")
        print("  Use --resume to retry failed phases.")
    else:
        _banner(f"PIPELINE COMPLETED SUCCESSFULLY in {total_dt:.1f}s (Version: {version})")
        print(f"  • Safe Mode: Version '{version}' ingested with is_current=False (Active version remains unchanged).")
        print("  • To check status: python scripts/version_manager.py status")
        print(f"  • To activate:     python scripts/version_manager.py promote --version {version}")
    _save_status()
    return 1 if has_failure else 0


def main():
    parser = argparse.ArgumentParser(description="Unified Ingestion Harness Pipeline")
    parser.add_argument("--version", default="v3", help="Target version identifier (default: v3)")
    parser.add_argument("--recreate", action="store_true", help="Recreate Qdrant collections cleanly")
    parser.add_argument("--skip-brochures", action="store_true", help="Skip brochure extraction")
    parser.add_argument("--skip-configurator", action="store_true", help="Skip configurator extraction")
    parser.add_argument("--skip-web", action="store_true", help="Skip web/policy text extraction")
    parser.add_argument("--no-ingest-db", action="store_true", help="Skip database ingestion (preview only)")
    parser.add_argument("--force", action="store_true", help="Force re-extraction of brochures")
    parser.add_argument("--resume", action="store_true", help="Resume from last failed phase (skip successful phases)")
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
            resume=args.resume,
        )
    )


if __name__ == "__main__":
    main()
