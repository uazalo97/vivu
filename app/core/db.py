import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import asyncpg
from dotenv import dotenv_values

from app.config import settings

logger = logging.getLogger("bds.db")

_pool: asyncpg.Pool | None = None
_pool_loop = None
_lock = asyncio.Lock()

T = TypeVar("T")

RETRYABLE_DB_ERRORS = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.InternalClientError,
    ConnectionResetError,
    ConnectionRefusedError,
    BrokenPipeError,
    OSError,
    asyncio.TimeoutError,
)

_stats = {"created_at": 0.0, "acquire_count": 0}


def _pg_url() -> str:
    url = settings.postgres_url.replace("postgresql+asyncpg://", "postgresql://")
    if "localhost:5432" in url:
        _env = dotenv_values(".env")
        cloud_dsn = _env.get("PG_DSN") or _env.get("POSTGRES_URL")
        if cloud_dsn:
            url = cloud_dsn.replace("postgresql+asyncpg://", "postgresql://")
    return url


async def get_pool() -> asyncpg.Pool:
    global _pool, _pool_loop
    current_loop = asyncio.get_running_loop()
    if _pool is None or _pool_loop != current_loop:
        async with _lock:
            if _pool is None or _pool_loop != current_loop:
                _pool = await asyncpg.create_pool(
                    _pg_url(),
                    min_size=1,
                    max_size=15,
                    max_queries=5000,
                    max_inactive_connection_lifetime=180.0,
                    command_timeout=20,
                    statement_cache_size=0,
                )
                _pool_loop = current_loop
                _stats["created_at"] = time.time()
                logger.info("PG pool created (Neon / PostgreSQL compatible)")
    return _pool


async def reset_pool(reason: str = "") -> None:
    """Invalidate pool sau khi phát hiện connection chết."""
    global _pool, _pool_loop
    async with _lock:
        pool = _pool
        _pool = None
        _pool_loop = None
        if pool is None:
            return
        try:
            if not pool._loop.is_closed():
                await asyncio.wait_for(pool.close(), timeout=2.0)
        except Exception:
            try:
                pool.terminate()
            except Exception:
                pass


async def run_with_db_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    label: str = "query",
    retries: int = 2,
) -> T:
    """Chạy operation, reset pool và retry khi network connection bị rớt."""
    for attempt in range(retries + 1):
        try:
            return await operation()
        except RETRYABLE_DB_ERRORS as exc:
            if attempt >= retries:
                raise
            logger.warning(
                "PG %s failed (%s, attempt %d/%d), resetting pool and retrying...",
                label,
                type(exc).__name__,
                attempt + 1,
                retries,
            )
            await reset_pool(reason=type(exc).__name__)
            await asyncio.sleep(0.15 * (attempt + 1))
    raise RuntimeError("unreachable")


def pool_stats() -> dict:
    """Live pool statistics for monitoring."""
    if _pool is None:
        return {"status": "not_initialized"}
    return {
        "status": "active",
        "min_size": _pool.get_min_size(),
        "max_size": _pool.get_max_size(),
        "size": _pool.get_size(),
        "free_size": _pool.get_idle_size(),
        "uptime_seconds": int(time.time() - _stats["created_at"]),
    }
