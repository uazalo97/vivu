#!/usr/bin/env python3
"""
vector_cache.py — Cache embedding vector theo **content-hash** (SQLite).

Mục đích: incremental embed — chunk nào content KHÔNG đổi → lấy vector từ
cache, KHÔNG gọi OpenRouter API. Đổi 1 raw file → chỉ embed lại các chunk thực
sự đổi (cache miss), còn lại cache hit (0 token). Re-run cùng version → 100%
hit → 0 API call.

Key = `sha1(f"{embed_model}:{content_hash}")`:
  - theo **content** (`sha1(text + json.dumps(structured, sort_keys=True))`) →
    content y hệt dù sang version khác vẫn hit;
  - theo **embed_model** → đổi model embed = miss tự nhiên (không dùng nhầm
    vector của model cũ).

Lưu `data/.vector_cache/cache.sqlite` (gitignored — artifact lớn). Vector nén
dạng `array('f').tobytes()` (1536 float ≈ 6KB/row).
"""

import array
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "data" / ".vector_cache"
CACHE_PATH = CACHE_DIR / "cache.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vector_cache (
    hash        TEXT PRIMARY KEY,
    collection  TEXT,
    embed_model TEXT,
    dim         INT,
    vector      BLOB,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_vc_collection ON vector_cache(collection);
"""


def content_hash(text: str, structured: dict | None, embed_model: str) -> str:
    """Hash ổn định theo content + embed_model (dùng làm cache key)."""
    import hashlib
    import json

    body = json.dumps(structured or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(f"{embed_model}\x1f{text}\x1f{body}".encode("utf-8")).hexdigest()


class VectorCache:
    """SQLite cache: hash → vector. Mở 1 connection / run."""

    def __init__(self, path: Path = CACHE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(_SCHEMA)
        self.hits = 0
        self.misses = 0

    def get(self, h: str) -> list[float] | None:
        row = self._conn.execute("SELECT vector FROM vector_cache WHERE hash = ?", (h,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        a = array.array("f")
        a.frombytes(row[0])
        return a.tolist()

    def put(self, h: str, collection: str, embed_model: str, vec: list[float]) -> None:
        blob = array.array("f", vec).tobytes()
        self._conn.execute(
            "INSERT OR REPLACE INTO vector_cache (hash, collection, embed_model, dim, vector, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (h, collection, embed_model, len(vec), blob),
        )

    def commit(self) -> None:
        self._conn.commit()
    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses}

    def prune(self, max_age_days: int = 30, max_rows: int = 50000) -> dict:
        """Xóa cache cũ / dư. Return {aged, trimmed, total}."""
        cur = self._conn.cursor()
        # 1) xóa theo age: created_at < now - N days
        cur.execute(
            "DELETE FROM vector_cache WHERE created_at < datetime('now', ?)",
            (f"-{max_age_days} days",),
        )
        aged = cur.rowcount if cur.rowcount != -1 else 0
        # 2) xóa theo size: giữ max_rows mới nhất (created_at ASC)
        cur.execute("SELECT COUNT(*) FROM vector_cache")
        row = cur.fetchone()
        total = row[0] if row else 0
        trimmed = 0
        if total > max_rows:
            to_delete = total - max_rows
            cur.execute(
                "DELETE FROM vector_cache WHERE hash IN ("
                " SELECT hash FROM vector_cache ORDER BY created_at ASC LIMIT ?"
                ")",
                (to_delete,),
            )
            trimmed = cur.rowcount if cur.rowcount != -1 else to_delete
        self._conn.commit()
        # 3) thu hồi disk
        if aged + trimmed > 0:
            try:
                self._conn.execute("VACUUM")
            except Exception:
                pass
        cur.execute("SELECT COUNT(*) FROM vector_cache")
        final_total = cur.fetchone()[0]
        return {"aged": aged, "trimmed": trimmed, "total": final_total}

    def stats_extended(self) -> dict:
        cur = self._conn.execute("SELECT COUNT(*), SUM(LENGTH(vector)) FROM vector_cache")
        cnt, sz = cur.fetchone()
        return {"rows": cnt or 0, "bytes": sz or 0, "hits": self.hits, "misses": self.misses}

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()
