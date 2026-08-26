#!/usr/bin/env python3
"""
cache_admin.py — CLI quản lý Redis cache + VectorCache + telemetry.

Usage:
    python scripts/cache_admin.py stats                     # đếm key theo prefix
    python scripts/cache_admin.py clear                     # xóa TẤT CẢ cache keys
    python scripts/cache_admin.py clear --prefix cache:specs:  # xóa theo prefix
    python scripts/cache_admin.py version                   # hiển thị data_version hiện tại
    python scripts/cache_admin.py vector-prune --age 30 --max-rows 50000  # prune VectorCache
    python scripts/cache_admin.py vector-stats              # thống kê VectorCache

Fail-open: script chỉ đọc/xóa cache, không ảnh hưởng DB hay app.
"""

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")


PREFIXES = [
    "cache:",  # tool cache (cache:{dv}:specs/colors/options/list_models)
    "hs:",  # hybrid search cache
    "emb:",  # embedding cache
    "ans:",  # answer cache (future)
    "session:",  # session store
    "user:",  # long-term memory
    "rl:",  # rate limit counters
    "dedup:",  # dedupe keys
]


async def stats():
    from app.core.memory import get_redis

    r = get_redis()
    if not r:
        print("Redis unavailable")
        return
    print(f"{'Prefix':<25} {'Count':>8}")
    print("-" * 35)
    total = 0
    for prefix in PREFIXES:
        count = 0
        try:
            async for _ in r.scan_iter(match=f"{prefix}*", count=500):
                count += 1
        except Exception as e:
            print(f"{prefix:<25} {'ERROR':>8}  ({e})")
            continue
        if count > 0:
            print(f"{prefix:<25} {count:>8}")
            total += count
    print("-" * 35)
    print(f"{'TOTAL':<25} {total:>8}")


async def clear(prefix: str | None = None):
    from app.core.memory import get_redis

    r = get_redis()
    if not r:
        print("Redis unavailable")
        return
    patterns = [prefix] if prefix else PREFIXES
    grand_total = 0
    for pat in patterns:
        keys = []
        try:
            async for k in r.scan_iter(match=f"{pat}*", count=500):
                keys.append(k)
        except Exception as e:
            print(f"SCAN {pat}* failed: {e}")
            continue
        if keys:
            deleted = await r.delete(*keys)
            print(f"Cleared {deleted} keys matching {pat}*")
            grand_total += deleted
    print(f"\nTotal cleared: {grand_total}")


async def version():
    from app.core.cache import data_version

    ver = await data_version()
    print(f"Current data version: {ver}")


async def metrics_prune(days: int = 90):
    from app.core.telemetry import prune_old_metrics

    deleted = await prune_old_metrics(days=days)
    print(f"Pruned {deleted} rows older than {days} days from request_metrics")
async def metrics_stats():
    from app.core.telemetry import get_metrics_retention_info

    info = await get_metrics_retention_info()
    print(f"Total rows: {info.get('total', 0)}")
    print(f"Oldest    : {info.get('oldest')}")
    print(f"Newest    : {info.get('newest')}")


def vector_prune(age: int = 30, max_rows: int = 50000):
    from lib.vector_cache import VectorCache

    vc = VectorCache()
    res = vc.prune(max_age_days=age, max_rows=max_rows)
    print(f"VectorCache prune: {res}")
    vc.close()


def vector_stats():
    from lib.vector_cache import VectorCache

    vc = VectorCache()
    ext = vc.stats_extended()
    print(f"VectorCache stats: rows={ext['rows']} bytes={ext['bytes']} hits={ext['hits']} misses={ext['misses']}")
    vc.close()


def main():
    ap = argparse.ArgumentParser(description="Redis cache admin CLI")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("stats", help="Count keys by prefix")
    p_clear = sub.add_parser("clear", help="Clear cache keys")
    p_clear.add_argument("--prefix", help="Only clear keys matching this prefix")
    sub.add_parser("version", help="Show current data_version")
    p_mprune = sub.add_parser("metrics-prune", help="Prune request_metrics older than N days")
    p_mprune.add_argument("--days", type=int, default=90, help="Retention days (default 90)")
    sub.add_parser("metrics-stats", help="Show request_metrics retention info (total/oldest/newest)")
    p_vprune = sub.add_parser("vector-prune", help="Prune VectorCache (SQLite) by age/size")
    p_vprune.add_argument("--age", type=int, default=30, help="max_age_days (default 30)")
    p_vprune.add_argument("--max-rows", type=int, default=50000, help="max rows to keep (default 50000)")
    sub.add_parser("vector-stats", help="Show VectorCache stats (rows/bytes/hits/misses)")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 1

    if args.cmd == "stats":
        asyncio.run(stats())
    elif args.cmd == "clear":
        asyncio.run(clear(args.prefix))
    elif args.cmd == "version":
        asyncio.run(version())
    elif args.cmd == "metrics-prune":
        asyncio.run(metrics_prune(args.days))
    elif args.cmd == "metrics-stats":
        asyncio.run(metrics_stats())
    elif args.cmd == "vector-prune":
        vector_prune(age=args.age, max_rows=args.max_rows)
    elif args.cmd == "vector-stats":
        vector_stats()
    return 0


if __name__ == "__main__":
    sys.exit(main())
