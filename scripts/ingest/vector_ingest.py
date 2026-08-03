#!/usr/bin/env python3
"""
vector_ingest.py — Ingest vector JSONL into local Qdrant.

For each line in data/clean/<version>/vector/*.jsonl:
  - embed the text using a local sentence-transformers model
  - upsert into Qdrant collection named after the file
  - attach all non-text fields as payload

Default model: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
(small, multilingual, good for Vietnamese short queries).

Usage:
    python scripts/ingest/vector_ingest.py --version v1
"""

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTOR_DIR = REPO_ROOT / "data" / "clean" / "{version}" / "vector"

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_QDRANT_URL = "http://localhost:6333"
VECTOR_SIZE = 384  # MiniLM-L12-v2 output dimension
BATCH_SIZE = 64


def load_model(model_name: str) -> SentenceTransformer:
    print(f"[vector_ingest] loading embedding model: {model_name}")
    return SentenceTransformer(model_name)


def qdrant_id(chunk_id: str) -> str:
    """Qdrant requires point id to be a UUID or unsigned integer.
    Convert our stable string id into a deterministic UUIDv5.
    """
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # OID namespace
    return str(uuid.uuid5(namespace, chunk_id))


def make_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    """Keep everything except the raw text and id for payload."""
    payload = {k: v for k, v in chunk.items() if k not in {"id", "text", "is_hot"}}
    return payload


def ingest_file(client: QdrantClient, model: SentenceTransformer, path: Path, recreate: bool) -> int:
    collection_name = path.stem
    print(f"[vector_ingest] processing {collection_name} ...")

    if recreate and client.collection_exists(collection_name):
        print(f"  dropping existing collection {collection_name}")
        client.delete_collection(collection_name)

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"  created collection {collection_name}")

    chunks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not chunks:
        print(f"  empty file, skipping")
        return 0

    texts = [c["text"] for c in chunks]
    print(f"  embedding {len(texts)} chunks ...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=BATCH_SIZE)

    points = [
        PointStruct(
            id=qdrant_id(c["id"]),
            vector=emb.tolist(),
            payload=make_payload(c),
        )
        for c, emb in zip(chunks, embeddings)
    ]

    client.upsert(collection_name=collection_name, points=points, wait=True)
    print(f"  upserted {len(points)} points into {collection_name}")
    return len(points)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest vector JSONL into local Qdrant.")
    ap.add_argument("--version", default="v1", help="Clean data version")
    ap.add_argument("--url", default=DEFAULT_QDRANT_URL, help="Qdrant URL")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Sentence-transformers model name")
    ap.add_argument("--recreate", action="store_true", help="Drop and recreate collections")
    args = ap.parse_args()

    vector_dir = Path(str(VECTOR_DIR).format(version=args.version))
    if not vector_dir.exists():
        print(f"[vector_ingest] vector dir not found: {vector_dir}", file=sys.stderr)
        return 1

    client = QdrantClient(url=args.url)
    try:
        client.get_collections()
    except Exception as e:
        print(f"[vector_ingest] cannot connect to Qdrant at {args.url}: {e}", file=sys.stderr)
        print("  hint: docker compose up -d", file=sys.stderr)
        return 1

    model = load_model(args.model)

    total = 0
    for jsonl in sorted(vector_dir.glob("*.jsonl")):
        total += ingest_file(client, model, jsonl, args.recreate)

    print(f"[vector_ingest] done. total points: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
