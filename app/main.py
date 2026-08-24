import logging

from app.tracing import setup_tracing

from pathlib import Path

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin_prompts import router as admin_prompts_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.config import settings

# Configure logging so bds.* loggers appear in terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("bds").setLevel(logging.INFO)

app = FastAPI(title="Vivu Chatbot & Telemetry API")


@app.on_event("startup")
async def _startup_pg_pool():
    """Tạo asyncpg connection pool cho prompts module — tránh tạo raw connection mỗi request."""
    import app.agent.prompts as _prompts_module

    try:
        pg_url = settings.postgres_url.replace("postgresql+asyncpg://", "postgresql://")
        _prompts_module._pg_pool = await asyncpg.create_pool(
            pg_url,
            min_size=1,
            max_size=5,
            command_timeout=10,
        )
        logging.getLogger("bds").info("PG pool created (min=1, max=5)")
    except Exception as e:
        logging.getLogger("bds").warning("PG pool creation failed (will use direct connect fallback): %s", e)


@app.on_event("shutdown")
async def _shutdown_pg_pool():
    """Đóng PG pool khi shutdown để không leak connections."""
    import app.agent.prompts as _prompts_module

    if _prompts_module._pg_pool is not None:
        await _prompts_module._pg_pool.close()
        logging.getLogger("bds").info("PG pool closed")


# Allow cross-origin calls from any frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(metrics_router)
app.include_router(admin_prompts_router)

# Phục vụ static files & SPA fallback cho React Router (hỗ trợ truy cập trực tiếp /admin)
_STATIC_DIR = Path("app/static")
if (_STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if not _STATIC_DIR.exists():
        return JSONResponse({"error": "Static directory not found"}, status_code=404)
    target = _STATIC_DIR / full_path
    if target.is_file():
        return FileResponse(target)
    index_file = _STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return JSONResponse({"error": "Not Found"}, status_code=404)


setup_tracing()
