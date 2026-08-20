import json
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from app.config import settings

logger = logging.getLogger("retrieval")

_reranker = None
_sparse_index = None
_embed_client = None


def _get_embed_client():
    """OpenAI client for embeddings — single OpenAI key (OPENAI_API_KEY)."""
    global _embed_client
    if _embed_client is None:
        from openai import OpenAI

        _embed_client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            max_retries=3,
            timeout=60.0,
        )
    return _embed_client


# Collections to search. Override via QDRANT_DENSE_COLLECTIONS env var.
import os as _os  # noqa: E402

_dense_env = _os.environ.get("QDRANT_DENSE_COLLECTIONS", "")
DENSE_COLLECTIONS = (
    [c.strip() for c in _dense_env.split(",") if c.strip()]
    if _dense_env
    else ["vivu_product_info", "vivu_policy", "vivu_maintenance"]
)
SPARSE_COLLECTION = "sparse"

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CLEAN_DIR = REPO_ROOT / "data" / "clean"

STOPWORDS = set(
    """
và của là đã đang sẽ được với cho từ đến tại cũng như hay hoặc nhưng nếu thì
khi mà nên vì thế nên để lại vẫn còn rất chỉ mỗi này kia nào đó đây những các
tất mọi người tôi bạn chúng ta họ nó ông bà anh chị em cùng thôi cần nếu đúng
xin quý""".split()
)

TOKEN_RE = re.compile(r"[a-zà-ỹ0-9]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and len(t) > 1]


# ── Sparse index auto-detection (DB is source of truth) ─────────────────────
_pg_current_version: str | None = None
_pg_version_checked = False


def _get_current_version_from_db() -> str | None:
    """Đọc version is_current từ PG ingest_version — DB là source of truth."""
    global _pg_current_version, _pg_version_checked
    if _pg_version_checked and _pg_current_version is not None:
        return _pg_current_version
    try:
        import psycopg2

        pg_url = settings.postgres_url.replace("+asyncpg", "")
        # Fallback PG_DSN như app/core/db.py (Neon cloud)
        if "localhost:5432" in pg_url:
            from dotenv import dotenv_values

            _env2 = dotenv_values(REPO_ROOT / ".env")
            cloud_dsn = _env2.get("PG_DSN") or _env2.get("POSTGRES_URL")
            if cloud_dsn:
                pg_url = cloud_dsn.replace("+asyncpg://", "postgresql://")
        conn = psycopg2.connect(pg_url)
        cur = conn.cursor()
        cur.execute("SELECT version FROM ingest_version WHERE is_current LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            _pg_current_version = str(row[0]).strip()
            _pg_version_checked = True
            return _pg_current_version
    except Exception as e:
        logger.debug("PG current version query failed (fallback to file scan): %s", e)
    _pg_version_checked = True
    return None


def _find_latest_sparse_index() -> Path | None:
    """Ưu tiên DB is_current, fallback scan file."""
    global _sparse_index
    if not DATA_CLEAN_DIR.exists():
        return None
    # 1. Thử lấy version active từ DB — đây là source of truth (PG v2 nhưng file chỉ v1 là lệch pipeline)
    db_ver = _get_current_version_from_db()
    if db_ver:
        db_path = DATA_CLEAN_DIR / db_ver / "sparse_index.json"
        if db_path.exists():
            try:
                raw = db_path.read_text(encoding="utf-8")
                idx = json.loads(raw)
                _sparse_index = idx
                return db_path
            except Exception as e:
                logger.warning("Failed to load DB version sparse_index %s: %s, falling back to scan", db_path, e)
        else:
            logger.warning(
                "DB is_current=%s nhưng file %s không tồn tại — pipeline chưa build v2, fallback scan file cũ",
                db_ver,
                db_path,
            )
    # 2. Fallback: scan file lấy version cao nhất (hành vi cũ)
    best_num = -1
    best_path = None
    for p in DATA_CLEAN_DIR.glob("*/sparse_index.json"):
        try:
            raw = p.read_text(encoding="utf-8")
            idx = json.loads(raw)
            ver = idx.get("version", p.parent.name)
            num = int(ver.lstrip("v")) if ver.lstrip("v").isdigit() else 0
            if num > best_num:
                best_num = num
                best_path = p
                _sparse_index = idx
        except Exception:
            continue
    return best_path


def _load_sparse_index() -> dict:
    global _sparse_index
    if _sparse_index is None:
        path = _find_latest_sparse_index()
        if path is None:
            _sparse_index = {}
        else:
            src = (
                "DB is_current"
                if _pg_current_version and path.name == "sparse_index.json" and path.parent.name == _pg_current_version
                else "file scan"
            )
            logger.info("Loaded sparse index from %s (version=%s, src=%s)", path, _sparse_index.get("version"), src)
    return _sparse_index or {}


def _query_to_sparse(query: str) -> dict | None:
    idx = _load_sparse_index()
    if not idx or "vocab" not in idx:
        return None

    vocab = idx["vocab"]
    idf_list = idx["idf"]
    k1 = idx.get("k1", 1.5)
    b = idx.get("b", 0.75)
    avgdl = idx.get("avgdl", 47.5)

    tokens = tokenize(query)
    if not tokens:
        return None

    tf = Counter(tokens)
    indices = []
    values = []
    for t, f in tf.items():
        if t not in vocab:
            continue
        vocab_idx = vocab[t]
        idf_val = idf_list[vocab_idx] if isinstance(idf_list, list) and vocab_idx < len(idf_list) else 1.0
        w = idf_val * f * (k1 + 1) / (f + k1 * (1 - b + b * 1.0 / avgdl))
        indices.append(vocab_idx)
        values.append(round(w, 6))

    if not indices:
        return None

    order = sorted(range(len(indices)), key=lambda i: indices[i])
    return {"indices": [indices[i] for i in order], "values": [values[i] for i in order]}


def _openrouter_embed_api(texts: list[str]) -> list[list[float]]:
    """Pure sync: embed texts via OpenAI API (compat name kept). Called in thread pool."""
    client = _get_embed_client()
    batch_size = 100
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(
            model=settings.openai_embed_model,
            input=batch,
        )
        sorted_data = sorted(response.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])
    return all_embeddings


# Compat aliases — giữ tên cũ để không vỡ import ngoài
_openai_embed_api = _openrouter_embed_api


def _openrouter_embed(texts: list[str]) -> list[list[float]]:
    """Sync embed (KHÔNG cache) — dùng bởi _rerank_texts (sync context)."""
    return _openrouter_embed_api(texts)


_openai_embed = _openrouter_embed


async def _embed_texts_cached(texts: list[str]) -> list[list[float]]:
    """Async wrapper: check embedding cache (emb:) first, miss → thread-pool API call + SET."""
    from app.core.cache import get_embedding_cached, set_embedding_cached
    import asyncio

    results: list[list[float] | None] = [None] * len(texts)
    uncached_indices: list[int] = []

    # 1. Batch check cache
    for i, text in enumerate(texts):
        cached = await get_embedding_cached(text)
        if cached is not None:
            results[i] = cached
        else:
            uncached_indices.append(i)

    # 2. Embed uncached texts in thread pool
    if uncached_indices:
        uncached_texts = [texts[i] for i in uncached_indices]
        loop = asyncio.get_event_loop()
        new_embeddings = await loop.run_in_executor(
            _thread_pool,
            _openrouter_embed_api,
            uncached_texts,
        )
        # 3. Store in cache + fill results
        for j, idx in enumerate(uncached_indices):
            emb = new_embeddings[j]
            results[idx] = emb
            asyncio.create_task(set_embedding_cached(texts[idx], emb))

    return results  # type: ignore[return-value]


# ── Qdrant REST API helper ─────────────────────────────────────────────────
class QdrantREST:
    """Thin wrapper around Qdrant REST API."""

    def __init__(self, url: str, api_key: str = ""):
        self.base = url.rstrip("/")
        self.session = requests.Session()
        if api_key:
            self.session.headers["api-key"] = api_key
        self.session.headers["Content-Type"] = "application/json"
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _build_filter(self, model_id: str = None) -> dict | None:
        if not model_id:
            return None
        return {"must": [{"key": "model_id", "match": {"value": model_id}}]}

    def search(self, collection: str, vector: list[float], model_id: str = None, limit: int = 10) -> list[dict]:
        body = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        f = self._build_filter(model_id)
        if f:
            body["filter"] = f

        try:
            r = self.session.post(
                f"{self.base}/collections/{collection}/points/search",
                json=body,
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("result", [])
        except Exception as e:
            if model_id and "Index required" in str(e):
                body.pop("filter", None)
                r = self.session.post(
                    f"{self.base}/collections/{collection}/points/search",
                    json=body,
                    timeout=30,
                )
                r.raise_for_status()
                return r.json().get("result", [])
            raise

    def search_sparse(self, collection: str, sparse: dict, model_id: str = None, limit: int = 10) -> list[dict]:
        body = {
            "vector": {
                "name": "sparse",
                "indices": sparse["indices"],
                "values": sparse["values"],
            },
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        f = self._build_filter(model_id)
        if f:
            body["filter"] = f

        try:
            r = self.session.post(
                f"{self.base}/collections/{collection}/points/search",
                json=body,
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("result", [])
        except Exception:
            return []

    def retrieve(self, collection: str, ids: list[str]) -> list[dict]:
        """Fetch points by IDs from a collection (with payload, no vectors)."""
        if not ids:
            return []
        try:
            r = self.session.post(
                f"{self.base}/collections/{collection}/points",
                json={"ids": ids, "with_payload": True, "with_vector": False},
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("result", [])
        except Exception as e:
            logger.warning("retrieve %s failed: %s", collection, e)
            return []


_qdrant: QdrantREST | None = None


def get_qdrant() -> QdrantREST:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantREST(settings.qdrant_url, settings.qdrant_api_key)
    return _qdrant


# ── Reranker ───────────────────────────────────────────────────────────────
class CohereReranker:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.cohere.ai/v1/rerank"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        query = pairs[0][0]
        documents = [doc for _, doc in pairs]
        try:
            r = self.session.post(
                self.base_url,
                json={
                    "model": "rerank-multilingual-v3.0",
                    "query": query,
                    "documents": documents,
                    "top_n": len(documents),
                },
                timeout=30,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            scores = [0.0] * len(pairs)
            for item in results:
                scores[item.get("index", 0)] = item.get("relevance_score", 0.0)
            return scores
        except Exception as e:
            logger.warning("Cohere rerank failed: %s", e)
            return [0.0] * len(pairs)


def get_reranker():
    global _reranker
    if _reranker is None and settings.rerank_enabled:
        if settings.cohere_api_key:
            _reranker = CohereReranker(settings.cohere_api_key)
        else:
            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder(settings.rerank_model)
    return _reranker


# ── Fusion ─────────────────────────────────────────────────────────────────
def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def _rrf_fusion(result_lists: list[list], k: int = 60) -> list[tuple]:
    scores = {}
    hit_data = {}
    for results in result_lists:
        for rank, hit in enumerate(results):
            pid = hit.get("id", "")
            scores[pid] = scores.get(pid, 0) + _rrf_score(rank, k)
            if pid not in hit_data:
                hit_data[pid] = hit
    sorted_ids = sorted(scores.keys(), key=lambda pid: scores[pid], reverse=True)
    return [(hit_data[pid], scores[pid]) for pid in sorted_ids]


# ── Sparse text resolution ──────────────────────────────────────────────────
def _resolve_sparse_texts(qdrant: QdrantREST, sparse_results: list[dict]) -> list[dict]:
    """Resolve sparse results that lack 'text' by fetching from dense collections.

    Sparse v2+ stores reference-only payloads {collection, chunk_id, model_id}.
    Dense collections (via alias) contain the actual text. Point IDs are the same
    across sparse and dense (both derived from chunk_id via uuid5).
    """
    needs_text = []
    has_text = []
    for hit in sparse_results:
        payload = hit.get("payload", {})
        if payload.get("text", "").strip():
            has_text.append(hit)
        else:
            needs_text.append(hit)

    if not needs_text:
        return sparse_results

    # Group IDs by their source dense collection
    by_collection: dict[str, list[str]] = {}
    for hit in needs_text:
        col = hit.get("payload", {}).get("collection", "")
        if col:
            by_collection.setdefault(col, []).append(hit["id"])

    # Batch fetch from each dense collection
    text_map: dict[str, dict] = {}
    for col, ids in by_collection.items():
        records = qdrant.retrieve(col, ids)
        for rec in records:
            payload = rec.get("payload", {})
            text_map[rec["id"]] = {
                "text": payload.get("text", ""),
                "source_type": payload.get("source_type", ""),
                "source_url": payload.get("source_url", ""),
                "edition_id": payload.get("edition_id", ""),
                "text_type": payload.get("text_type", ""),
                "page": payload.get("page", ""),
            }

    # Inject text into sparse results
    resolved = []
    for hit in needs_text:
        extra = text_map.get(hit["id"], {})
        if extra.get("text"):
            hit.setdefault("payload", {}).update(extra)
            resolved.append(hit)
        else:
            logger.debug("Could not resolve text for sparse point %s", hit["id"])

    return has_text + resolved


# ── Main search ────────────────────────────────────────────────────────────
import asyncio  # noqa: E402
import concurrent.futures  # noqa: E402

_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


async def hybrid_search(query: str, model_id: str = None, top_k: int = 5) -> list[dict]:
    from app.core.cache import get_hybrid_cached, set_hybrid_cached

    skip_rerank = not settings.rerank_enabled

    # 0. Check hybrid search cache (hs:) — skip entire pipeline on hit
    cached = await get_hybrid_cached(query, model_id, top_k, skip_rerank)
    if cached is not None:
        logger.debug("hs cache hit")
        return cached
    logger.debug("hs cache miss")

    qdrant = get_qdrant()
    limit = top_k * 2

    # 1. Embed query (async, checks emb: cache) + sparse vector (sync thread)
    loop = asyncio.get_event_loop()
    embed_task = _embed_texts_cached([query])
    sparse_task = loop.run_in_executor(_thread_pool, _query_to_sparse, query)

    dense_vector = (await embed_task)[0]
    sparse_vec = await sparse_task

    # 2. Dense search across ALL collections IN PARALLEL
    async def _dense_search(col):
        try:
            return await loop.run_in_executor(_thread_pool, qdrant.search, col, dense_vector, model_id, limit)
        except Exception as e:
            logger.warning("search %s failed: %s", col, e)
            return []

    dense_tasks = [_dense_search(col) for col in DENSE_COLLECTIONS]
    dense_results = await asyncio.gather(*dense_tasks)
    all_dense = [hit for results in dense_results for hit in results]

    # 3. Sparse search (BM25) — in parallel with nothing (dense already done)
    sparse_results = []
    if sparse_vec:
        try:
            sparse_results = await loop.run_in_executor(
                _thread_pool, qdrant.search_sparse, SPARSE_COLLECTION, sparse_vec, model_id, limit
            )
            sparse_results = await loop.run_in_executor(_thread_pool, _resolve_sparse_texts, qdrant, sparse_results)
        except Exception as e:
            logger.warning("sparse search failed: %s", e)

    # 4. RRF fusion
    if sparse_results:
        fused = _rrf_fusion([all_dense, sparse_results])
    else:
        fused = [(hit, hit.get("score", 0)) for hit in all_dense]

    # 5. Rerank
    reranker = get_reranker()
    if reranker and len(fused) > 0:
        pairs = [(query, hit.get("payload", {}).get("text", "")) for hit, _ in fused]
        non_empty = [(i, q, d) for i, (q, d) in enumerate(pairs) if d.strip()]
        if non_empty:
            rerank_pairs = [(q, d) for _, q, d in non_empty]
            rerank_scores = await loop.run_in_executor(_thread_pool, reranker.predict, rerank_pairs)
            # Only apply rerank if at least one score is non-zero (rerank succeeded)
            if any(s > 0 for s in rerank_scores):
                scores = [0.0] * len(pairs)
                for j, (orig_idx, _, _) in enumerate(non_empty):
                    scores[orig_idx] = rerank_scores[j]
                fused = [(hit, float(score)) for (hit, _), score in zip(fused, scores)]
                fused.sort(key=lambda x: x[1], reverse=True)

    # 6. Return top_k (skip chunks without text)
    results = []
    for hit, score in fused:
        payload = hit.get("payload", {})
        text = payload.get("text", "")
        if not text or not text.strip():
            continue
        results.append(
            {
                "text": text,
                "model_id": payload.get("model_id"),
                "edition_id": payload.get("edition_id"),
                "text_type": payload.get("text_type", ""),
                "source_type": payload.get("source_type", ""),
                "source_url": payload.get("source_url", ""),
                "page": payload.get("page", ""),
                "score": round(score, 4),
            }
        )
        if len(results) >= top_k:
            break

    # 7. Cache the full-pipeline result (hs:)
    asyncio.create_task(set_hybrid_cached(query, model_id, top_k, skip_rerank, results))
    return results
