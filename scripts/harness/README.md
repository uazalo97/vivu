# Agentic Document Ingestion Harness

Unified data extraction and ingestion engine for VinFast vehicle specifications, pricing, colors, options, and policy documents.

## Directory Structure

```
scripts/harness/
├── pipeline.py                 # Master pipeline entrypoint (Phase 1-5)
├── batch_runner.py             # Batch brochure PDF processor
├── orchestrator.py             # Single brochure processing pipeline (5-step: inspect→plan→extract→save→export)
├── config.py                   # Centralized configuration & environment paths
├── schemas.py                  # Pydantic data models
├── inspector.py                # PDF layout analysis & page signal computation
├── planner.py                  # Routing planner (Vision vs Native extraction)
├── crop_generator.py           # Visual bounding box crop generator
├── extractors/
│   ├── pymupdf.py              # Native text block extractor
│   ├── vision.py               # Multimodal Vision extractor (OpenAI-compatible, gpt-5.6-luna)
│   ├── configurator.py         # Configurator CSV extractor
│   └── web_text.py             # Web policy & maintenance text extractor
├── normalizers/
│   ├── table.py                # Spec key, unit, and category normalizer
│   └── text.py                 # Prose cleaner & price stripper
├── chunker/
│   └── semantic.py             # Semantic retriever chunker
├── validators/
│   └── multi_layer.py          # Structural and schema validator
└── sinks/
    ├── postgres.py             # PostgreSQL structured data sink
    └── qdrant.py               # Qdrant dense embedding & sparse BM25 sink
```

## Quick Start

```powershell
# Run the complete pipeline for a new version
python -m scripts.harness.pipeline --version v3 --recreate

# Run brochure batch only
python -m scripts.harness.batch_runner --force

# Inspect status
python scripts/version_manager.py status
```

For comprehensive documentation, see [docs/DATA_PIPELINE.md](../../docs/DATA_PIPELINE.md).
