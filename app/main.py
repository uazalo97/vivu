import logging
from contextlib import asynccontextmanager

from app.tracing import setup_tracing

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.admin_prompts import router as admin_prompts_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router

# Configure logging so bds.* loggers appear in terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("bds").setLevel(logging.INFO)

logger = logging.getLogger("bds.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Warm connections at startup — tránh first-request latency (Neon cold + pool init + data_version)."""
    try:
        from app.core.cache import data_version
        from app.core.db import get_pool

        await get_pool()
        await data_version()
        logger.info("Warmup done: PG pool + data_version")
    except Exception as e:  # non-blocking
        logger.warning("Warmup failed (non-blocking): %s", e)
    yield


app = FastAPI(title="Vivu Chatbot & Telemetry API", lifespan=lifespan)

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
app.mount("/", StaticFiles(directory="app/static", html=True))
setup_tracing()
