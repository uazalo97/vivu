#!/usr/bin/env python3
"""
cache_admin.py — CLI quản lý Redis cache.

Usage:
    python scripts/cache_admin.py stats                     # đếm key theo prefix
    python scripts/cache_admin.py clear                     # xóa TẤT CẢ cache keys
    python scripts/cache_admin.py clear --prefix cache:specs:  # xóa theo prefix
    python scripts/cache_admin.py version                   # hiển thị data_version hiện tại

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


def main():
    ap = argparse.ArgumentParser(description="Redis cache admin CLI")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("stats", help="Count keys by prefix")
    p_clear = sub.add_parser("clear", help="Clear cache keys")
    p_clear.add_argument("--prefix", help="Only clear keys matching this prefix")
    sub.add_parser("version", help="Show current data_version")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
