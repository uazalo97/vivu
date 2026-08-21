"""
app/api/health.py — Production Health & Readiness Probes for Kubernetes / Docker / Cloud.

Endpoints:
- /healthz: Liveness probe (nhẹ, <1ms) — kiểm tra FastAPI event loop còn sống.
- /ready: Readiness probe (sâu) — kiểm tra kết nối PostgreSQL, Qdrant, Cache, LLM Config.
- /api/health: Backward compatibility alias cho frontend status bar.
"""

import datetime
import logging
import time
from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.db import get_pool, pool_stats

logger = logging.getLogger("bds.health")

router = APIRouter(tags=["Health & Diagnostics"])


@router.get("/healthz", summary="Liveness Probe")
async def healthz():
    """Liveness probe: Trả về 200 ngay lập tức nếu uvicorn server đang hoạt động."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "alive",
            "app_version": settings.app_version,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    )


@router.get("/ready", summary="Readiness Probe")
async def readiness_probe(response: Response):
    """Readiness probe: Kiểm tra toàn diện DB (PostgreSQL), Vector DB (Qdrant), Cache (Redis)
    và LLM API keys. Trả về 503 nếu service cốt lõi gặp sự cố.
    """
    checks: dict[str, Any] = {}
    is_ready = True

    # 1. Check PostgreSQL Connection & Pool
    t0 = time.monotonic()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            db_latency_ms = round((time.monotonic() - t0) * 1000, 2)
            if val == 1:
                checks["postgres"] = {
                    "status": "ok",
                    "latency_ms": db_latency_ms,
                    "pool": pool_stats(),
                }
            else:
                checks["postgres"] = {"status": "degraded", "detail": "unexpected_result"}
                is_ready = False
    except Exception as e:
        db_latency_ms = round((time.monotonic() - t0) * 1000, 2)
        checks["postgres"] = {
            "status": "error",
            "latency_ms": db_latency_ms,
            "error": str(e),
        }
        is_ready = False

    # 2. Check Qdrant Vector DB
    t0 = time.monotonic()
    try:
        import requests

        q_url = settings.qdrant_url.rstrip("/")
        headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}
        r = requests.get(f"{q_url}/collections", headers=headers, timeout=3.0)
        q_latency_ms = round((time.monotonic() - t0) * 1000, 2)
        if r.status_code == 200:
            cols = r.json().get("result", {}).get("collections", [])
            checks["qdrant"] = {
                "status": "ok",
                "latency_ms": q_latency_ms,
                "collections_count": len(cols),
            }
        else:
            checks["qdrant"] = {
                "status": "degraded",
                "latency_ms": q_latency_ms,
                "status_code": r.status_code,
            }
    except Exception as e:
        q_latency_ms = round((time.monotonic() - t0) * 1000, 2)
        checks["qdrant"] = {
            "status": "error",
            "latency_ms": q_latency_ms,
            "error": str(e),
        }
        is_ready = False

    # 3. Check Cache (Redis / Upstash)
    try:
        from app.core.memory import get_redis

        r_client = get_redis()
        if r_client:
            pong = await r_client.ping()
            checks["cache"] = {
                "status": "ok" if pong else "degraded",
                "enabled": True,
            }
        else:
            checks["cache"] = {"status": "disabled", "enabled": False}
    except Exception as e:
        checks["cache"] = {"status": "error", "error": str(e), "enabled": True}

    # 4. Check LLM Configuration & Credentials
    has_openai = bool(settings.openai_api_key)
    checks["llm_config"] = {
        "chat_model": settings.llm_model,
        "fallback_model": settings.llm_fallback_model,
        "openai_configured": has_openai,
        "status": "ok" if has_openai else "error_missing_openai_key",
    }
    if not has_openai:
        is_ready = False

    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "app_version": settings.app_version,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "checks": checks,
        },
    )


@router.get("/api/health", summary="Legacy Healthcheck Endpoint")
async def legacy_health():
    """Endpoint tương thích ngược cho frontend và monitoring cũ."""
    stats = pool_stats()
    return JSONResponse(content={"status": "ok", "pool": stats, "version": settings.app_version})
