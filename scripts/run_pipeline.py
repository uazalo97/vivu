#!/usr/bin/env python3
"""
run_pipeline.py — Wrapper for Unified Ingestion Harness Pipeline.
Forwards execution directly to scripts.harness.pipeline.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.harness.pipeline import main  # noqa: E402

if __name__ == "__main__":
    main()
