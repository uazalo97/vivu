#!/usr/bin/env python3
"""
qdrant.py — Qdrant Vector Sink for Unified Ingestion Harness.
Exports retrieval chunks and ingests Dense Embeddings + BM25 Sparse Vectors into Qdrant:
- vivu_product_info__{version}
- vivu_policy__{version}
- vivu_maintenance__{version}
- sparse__{version}
"""

import json
import math
import re
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from scripts.harness.chunker.semantic import SemanticChunker
from scripts.harness.config import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    QDRANT_API_KEY,
    QDRANT_TIMEOUT,
    QDRANT_URL,
    RETRIEVAL_DIR,
)
from scripts.harness.schemas import CanonicalDocument

UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

STOPWORDS = set(
    """
    của và có là trong với cho khi từ không những các một được sẽ đã đang này đó thì
    để về ra theo tại cũng như nên vào đến nhưng bởi vì hay hoặc gì rất hơn hết cả đều
    sau trước mới lại còn phải bị do qua lên xuống ngay chỉ mà nữa đây ấy nào bao nhiêu
    mình bạn tôi nó họ chúng ta ông bà anh chị em cùng thôi cần nếu đúng xin quý
    """.split()
)


def qdrant_id(chunk_id: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, chunk_id))


def tokenize_vi(text: str) -> List[str]:
    text = unicodedata.normalize("NFC", text).lower()
    tokens = re.findall(r"[a-z0-9à-ỹ]+", text)
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


class QdrantSink:
    def __init__(self, output_dir: Path = RETRIEVAL_DIR, url: str = QDRANT_URL, api_key: str = QDRANT_API_KEY):
        self.output_dir = Path(output_dir)
        self.url = url
        self.api_key = api_key
        self.chunker = SemanticChunker()

    def export_preview(self, doc: CanonicalDocument) -> Path:
        """Chunk a canonical brochure document and write to brochures/{doc_id}_chunks.jsonl."""
        brochures_dir = self.output_dir / "brochures"
        brochures_dir.mkdir(parents=True, exist_ok=True)

        doc_id = doc.document.id
        chunks = self.chunker.chunk_document(doc)

        out_path = brochures_dir / f"{doc_id}_chunks.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        return out_path

    def consolidate_all_chunks(self, web_chunks: List[Dict[str, Any]]) -> Dict[str, Path]:
        """Consolidate brochure chunks and web chunks into collection JSONL files."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        policies_dir = self.output_dir / "policies"
        policies_dir.mkdir(parents=True, exist_ok=True)

        all_chunks: List[Dict[str, Any]] = []

        # 1. Read all brochure chunks (C4-hotfix: handle both brochures/ subdir and legacy flat files)
        # New path: retrieval/brochures/*.jsonl ; Legacy: retrieval/*.jsonl (flat)
        brochures_dir = self.output_dir / "brochures"
        seen_chunk_ids: set = set()
        brochure_files: List[Path] = []
        if brochures_dir.exists():
            brochure_files.extend(sorted(brochures_dir.glob("*.jsonl")))
        # Legacy flat files in retrieval root (e.g., vf2_brochure_chunks.jsonl) - for backward compat
        # Exclude master, sparse, and policies output files
        for flat in sorted(self.output_dir.glob("*.jsonl")):
            if flat.name in ("all_models_chunks.jsonl", "sparse_index.json") or flat.name.startswith("sparse_index__"):
                continue
            # Skip if already in brochures list (same resolved path)
            if flat.resolve() in {p.resolve() for p in brochure_files}:
                continue
            # Only include brochure-like files (contain _chunks and not in policies)
            if "_chunks" in flat.name:
                brochure_files.append(flat)
        for f in sorted(brochure_files):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    for line in fp:
                        if line.strip():
                            chunk = json.loads(line)
                            cid = chunk.get("id")
                            if cid and cid in seen_chunk_ids:
                                continue
                            if cid:
                                seen_chunk_ids.add(cid)
                            all_chunks.append(chunk)
            except Exception as e:
                print(f"[QdrantSink] Warning: failed to read {f}: {e}")

        # 2. Add web chunks (deduplicate by id as well)
        for wc in web_chunks:
            cid = wc.get("id")
            if cid and cid in seen_chunk_ids:
                continue
            if cid:
                seen_chunk_ids.add(cid)
            all_chunks.append(wc)

        # 3. Write master all_models_chunks.jsonl
        master_path = self.output_dir / "all_models_chunks.jsonl"
        with open(master_path, "w", encoding="utf-8") as f:
            for c in all_chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        # 4. Group by collection
        by_col: Dict[str, List[Dict[str, Any]]] = {}
        for c in all_chunks:
            col = c.get("collection") or c.get("metadata", {}).get("collection") or "vivu_product_info"
            by_col.setdefault(col, []).append(c)

        out_files = {"all": master_path}
        for col_name, items in by_col.items():
            sub_path = policies_dir / f"{col_name}.jsonl"
            with open(sub_path, "w", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            out_files[col_name] = sub_path

        return out_files

    def ingest_to_qdrant(self, version: str = "v3", recreate: bool = False) -> Dict[str, int]:
        """
        Active Qdrant Ingestion:
        1. Embeds and creates dense collections: {collection}__{version}
        2. Computes BM25 and creates sparse collection: sparse__{version}
        """
        client = QdrantClient(url=self.url, api_key=self.api_key or None, timeout=QDRANT_TIMEOUT)

        # Load all chunks
        master_file = self.output_dir / "all_models_chunks.jsonl"
        if not master_file.exists():
            return {}

        all_chunks: List[Dict[str, Any]] = []
        with open(master_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    all_chunks.append(json.loads(line))

        # Group chunks by dense collection
        by_col: Dict[str, List[Dict[str, Any]]] = {}
        for c in all_chunks:
            col = c.get("collection") or c.get("metadata", {}).get("collection") or "vivu_product_info"
            by_col.setdefault(col, []).append(c)

        # C5 fix: guard for missing API key (dense requires it, sparse does not)
        has_api_key = bool(OPENAI_API_KEY)
        if not has_api_key:
            print(
                "[QdrantSink] WARNING: OPENAI_API_KEY not set - skipping dense embedding ingestion (sparse BM25 will still be built)."
            )
            embed_client = None
            model_name = EMBEDDING_MODEL.split("/")[-1]
        else:
            embed_client = OpenAI(
                api_key=OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL if OPENAI_BASE_URL and "openai.com" not in OPENAI_BASE_URL else None,
            )
            model_name = EMBEDDING_MODEL.split("/")[-1]

        stats: Dict[str, int] = {}

        # 1. Ingest Dense Collections
        for col_name, items in by_col.items():
            physical_col = f"{col_name}__{version}"
            print(f"  -> Ingesting dense collection: {physical_col} ({len(items)} chunks)...")

            if not has_api_key:
                print(f"  [SKIP] Dense {physical_col} skipped due to missing API key.")
                stats[physical_col] = 0
                continue

            if recreate or not client.collection_exists(physical_col):
                if client.collection_exists(physical_col):
                    client.delete_collection(physical_col)
                client.create_collection(
                    collection_name=physical_col,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )
                try:
                    client.create_payload_index(physical_col, "model_id", PayloadSchemaType.KEYWORD)
                except Exception as e:
                    print(f"[QdrantSink] Payload index for {physical_col} exists or failed: {e}")

            # Embed in batches
            batch_size = 64
            points: List[PointStruct] = []

            for i in range(0, len(items), batch_size):
                batch = items[i : i + batch_size]
                texts = [b["text"] for b in batch]

                resp = embed_client.embeddings.create(input=texts, model=model_name)
                vectors = [d.embedding for d in resp.data]

                for chunk, vec in zip(batch, vectors):
                    pid = qdrant_id(chunk["id"])
                    payload = dict(chunk.get("metadata", {}))
                    payload["chunk_id"] = chunk["id"]
                    payload["text"] = chunk["text"]
                    payload["vector_version"] = version
                    payload["ingested_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

                    points.append(PointStruct(id=pid, vector=vec, payload=payload))

            # Upsert points
            for i in range(0, len(points), 100):
                client.upsert(collection_name=physical_col, points=points[i : i + 100])

            # C5 fix: cleanup stale points when not recreating (delete points not in new set)
            if not recreate:
                try:
                    new_ids = {p.id for p in points}
                    # Scroll existing points to find stale ones (only if collection existed before)
                    existing_ids = set()
                    offset = None
                    while True:
                        batch, offset = client.scroll(
                            collection_name=physical_col,
                            limit=256,
                            offset=offset,
                            with_payload=False,
                            with_vectors=False,
                        )
                        for pt in batch:
                            existing_ids.add(str(pt.id))
                        if offset is None:
                            break
                    stale_ids = list(existing_ids - new_ids)
                    if stale_ids:
                        print(f"  [CLEANUP] Deleting {len(stale_ids)} stale points from {physical_col}")
                        # Qdrant delete by ids in batches
                        for i in range(0, len(stale_ids), 100):
                            client.delete(collection_name=physical_col, points_selector=stale_ids[i : i + 100])
                except Exception as e:
                    print(f"[QdrantSink] Stale cleanup for {physical_col} failed: {e}")

            stats[physical_col] = len(points)

        # 2. Ingest BM25 Sparse Collection
        sparse_col = f"sparse__{version}"
        print(f"  -> Ingesting sparse collection: {sparse_col} ({len(all_chunks)} chunks)...")

        if recreate or not client.collection_exists(sparse_col):
            if client.collection_exists(sparse_col):
                client.delete_collection(sparse_col)
            client.create_collection(
                collection_name=sparse_col,
                sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
            )
            try:
                client.create_payload_index(sparse_col, "model_id", PayloadSchemaType.KEYWORD)
            except Exception as e:
                print(f"[QdrantSink] Payload index for {sparse_col} exists or failed: {e}")

        # Build BM25 Vocabulary & IDF
        vocab: Dict[str, int] = {}
        df: Dict[int, int] = {}
        doc_tokens_list: List[List[str]] = []
        N = len(all_chunks)

        for c in all_chunks:
            tokens = tokenize_vi(c["text"])
            doc_tokens_list.append(tokens)
            seen_in_doc = set()
            for t in tokens:
                if t not in vocab:
                    vocab[t] = len(vocab)
                tid = vocab[t]
                if tid not in seen_in_doc:
                    df[tid] = df.get(tid, 0) + 1
                    seen_in_doc.add(tid)

        idf: Dict[int, float] = {}
        for tid, doc_freq in df.items():
            idf[tid] = math.log((N - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

        # Save sparse index metadata (C5 fix: versioned file + legacy for backward compat)
        sparse_index_file = self.output_dir / f"sparse_index__{version}.json"
        with open(sparse_index_file, "w", encoding="utf-8") as f:
            json.dump({"vocab": vocab, "idf": {str(k): v for k, v in idf.items()}}, f, ensure_ascii=False)
        # Keep legacy path for existing code that expects sparse_index.json
        legacy_sparse = self.output_dir / "sparse_index.json"
        try:
            with open(legacy_sparse, "w", encoding="utf-8") as f:
                json.dump({"vocab": vocab, "idf": {str(k): v for k, v in idf.items()}}, f, ensure_ascii=False)
        except Exception:
            pass

        # Compute Sparse Vectors & Upsert
        sparse_points: List[PointStruct] = []
        avgdl = sum(len(toks) for toks in doc_tokens_list) / max(N, 1)
        k1 = 1.5
        b = 0.75

        for chunk, tokens in zip(all_chunks, doc_tokens_list):
            tf = {}
            for t in tokens:
                tid = vocab[t]
                tf[tid] = tf.get(tid, 0) + 1

            dl = len(tokens)
            indices: List[int] = []
            values: List[float] = []

            for tid, count in tf.items():
                score = idf[tid] * (count * (k1 + 1)) / (count + k1 * (1 - b + b * (dl / avgdl)))
                if score > 0:
                    indices.append(tid)
                    values.append(round(score, 4))

            pid = qdrant_id(chunk["id"])
            payload = dict(chunk.get("metadata", {}))
            payload["chunk_id"] = chunk["id"]
            payload["text"] = chunk["text"]
            payload["vector_version"] = version

            sparse_points.append(
                PointStruct(id=pid, vector={"sparse": SparseVector(indices=indices, values=values)}, payload=payload)
            )

        for i in range(0, len(sparse_points), 100):
            client.upsert(collection_name=sparse_col, points=sparse_points[i : i + 100])

        stats[sparse_col] = len(sparse_points)
        # B1: prune VectorCache (fail-open, không ảnh hưởng ingest)
        try:
            from lib.vector_cache import VectorCache

            vc = VectorCache()
            res = vc.prune()
            print(f"[VectorCache] prune {res}")
            vc.close()
        except Exception as e:
            print(f"[VectorCache] prune failed (fail-open): {e}")
        return stats
