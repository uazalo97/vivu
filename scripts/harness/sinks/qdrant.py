#!/usr/bin/env python3
"""
qdrant.py — Qdrant Retrieval Chunks Sink.

Exports semantic chunks to data_v2/retrieval/{doc_id}_chunks.jsonl
with source metadata payload. (Safe test mode: no DB mutation).
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.harness.schemas import CanonicalDocument
from scripts.harness.chunker.semantic import SemanticChunker


class QdrantChunksSink:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.chunker = SemanticChunker()

    def export_preview(self, doc: CanonicalDocument) -> Path:
        """
        Chunk canonical document and write retrieval JSONL.
        """
        retrieval_dir = self.output_dir / "retrieval"
        retrieval_dir.mkdir(parents=True, exist_ok=True)

        doc_id = doc.document.id
        chunks = self.chunker.chunk_document(doc)

        out_path = retrieval_dir / f"{doc_id}_chunks.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        return out_path
