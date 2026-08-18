"""
app/api/metrics.py — Admin Metrics REST API Endpoints for Monitoring & Stakeholder Dashboard.

Toàn bộ Endpoint mở trực tiếp cho Frontend / Dashboard gọi lấy dữ liệu mà không cần xác thực header.
Tự động fallback về dữ liệu mặc định nếu Database chưa kết nối hoặc chưa có data.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.telemetry import (
    get_metrics_intents,
    get_metrics_logs,
    get_metrics_overview,
    get_metrics_timeseries,
)

logger = logging.getLogger("bds.metrics_api")

router = APIRouter(prefix="/api/admin/metrics", tags=["Admin & Telemetry"])


@router.get("/overview", summary="Tổng quan KPI vận hành")
async def metrics_overview(
    hours: int = Query(24, ge=1, le=720, description="Khoảng thời gian tính theo giờ (1-720)"),
):
    """Trả về các chỉ số KPI: Tổng queries, Token consumption, Chi phí ($ & VNĐ),
    TTFT P50/P95, Latency P50/P95/P99, Tỷ lệ Cache Hit, Tỷ lệ lỗi.
    """
    try:
        data = await get_metrics_overview(hours=hours)
        if not data:
            data = {
                "status": "success",
                "window_hours": hours,
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "error_rate_pct": 0.0,
                "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "costs": {"total_cost_usd": 0.0, "total_cost_vnd": 0.0},
                "latency_ms": {"avg": 0, "p50": 0, "p95": 0, "p99": 0},
                "ttft_ms": {"avg": 0, "p50": 0, "p95": 0},
                "caching": {"cache_hits": 0, "cache_hit_rate_pct": 0.0},
            }
        return JSONResponse(content=data)
    except Exception as e:
        logger.warning("Metrics overview fallback due to: %s", e)
        return JSONResponse(content={
            "status": "success",
            "window_hours": hours,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "error_rate_pct": 0.0,
            "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "costs": {"total_cost_usd": 0.0, "total_cost_vnd": 0.0},
            "latency_ms": {"avg": 0, "p50": 0, "p95": 0, "p99": 0},
            "ttft_ms": {"avg": 0, "p50": 0, "p95": 0},
            "caching": {"cache_hits": 0, "cache_hit_rate_pct": 0.0},
        })


@router.get("/timeseries", summary="Chuỗi thời gian (Requests, Latency, Cost)")
async def metrics_timeseries(
    hours: int = Query(24, ge=1, le=720, description="Khoảng thời gian tính theo giờ"),
):
    """Dữ liệu chuỗi thời gian phân đoạn theo giờ để hiển thị biểu đồ đường."""
    try:
        data = await get_metrics_timeseries(hours=hours)
        return JSONResponse(content=data)
    except Exception as e:
        logger.warning("Metrics timeseries fallback due to: %s", e)
        return JSONResponse(content={"status": "success", "points": []})


@router.get("/intents", summary="Phân bổ Intent & câu hỏi người dùng")
async def metrics_intents(
    hours: int = Query(168, ge=1, le=720, description="Khoảng thời gian tính theo giờ (mặc định 7 ngày)"),
):
    """Thống kê các intent (specs, price, compare, policy...) được quan tâm nhiều nhất."""
    try:
        data = await get_metrics_intents(hours=hours)
        return JSONResponse(content=data)
    except Exception as e:
        logger.warning("Metrics intents fallback due to: %s", e)
        return JSONResponse(content={"status": "success", "intents": []})


@router.get("/logs", summary="Danh sách Request Logs chi tiết")
async def metrics_logs(
    limit: int = Query(50, ge=1, le=200, description="Số lượng bản ghi mỗi trang"),
    offset: int = Query(0, ge=0, description="Vị trí bắt đầu phân trang"),
    intent: Optional[str] = Query(None, description="Lọc theo intent"),
    cache_only: bool = Query(False, description="Chỉ lấy các request có cache hit"),
):
    """Truy vấn danh sách request logs chi tiết có phân trang và bộ lọc."""
    try:
        data = await get_metrics_logs(
            limit=limit, offset=offset, intent=intent, cache_only=cache_only
        )
        return JSONResponse(content=data)
    except Exception as e:
        logger.warning("Metrics logs fallback due to: %s", e)
        return JSONResponse(content={"total": 0, "limit": limit, "offset": offset, "logs": []})
