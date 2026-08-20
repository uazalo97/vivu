import os
from pathlib import Path

from dotenv import load_dotenv

# Tải .env nếu có (dành cho chạy local)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _get_env(key: str, default: str = "") -> str:
    val = os.getenv(key)
    return val if val is not None else default


def _strip_prefix(m: str) -> str:
    m = m.strip()
    return m.split("/", 1)[-1] if "/" in m else m


class Settings:
    def __init__(self):
        # LLM + Embedding — single OpenAI key (unified) — fallback các key cũ để migration
        self.openai_api_key: str = (
            _get_env("OPENAI_API_KEY", "") or _get_env("OPENROUTER_API_KEY", "") or _get_env("DEEPINFRA_API_KEY", "")
        )
        self.openai_base_url: str = _get_env("OPENAI_BASE_URL", "https://api.openai.com/v1")
        raw_llm = _get_env("LLM_MODEL", "") or _get_env("DEEPINFRA_CHAT_MODEL", "gpt-4o-mini")
        self.llm_model: str = _strip_prefix(raw_llm)
        # Fallback khi model chính lỗi
        raw_fallback = _get_env("DEEPINFRA_FALLBACK_MODEL", "gpt-4o-mini")
        self.llm_fallback_model: str = _strip_prefix(raw_fallback)
        # Embed model: ưu tiên OPENAI_EMBED_MODEL, fallback các key cũ
        raw_embed = (
            _get_env("OPENAI_EMBED_MODEL", "")
            or _get_env("OPENROUTER_EMBED_MODEL", "")
            or _get_env("EMBEDDING_MODEL", "")
            or "text-embedding-3-small"
        )
        self.openai_embed_model: str = _strip_prefix(raw_embed)
        # Deprecated aliases — giữ để code cũ không vỡ
        self.openrouter_api_key: str = self.openai_api_key
        self.openrouter_embed_model: str = self.openai_embed_model
        self.deepinfra_api_key: str = self.openai_api_key
        self.deepinfra_base_url: str = self.openai_base_url
        # Embedding compat
        self.embedding_model: str = _get_env("EMBEDDING_MODEL", self.openai_embed_model)
        if "/" in self.embedding_model:
            self.embedding_model = _strip_prefix(self.embedding_model)
        self.embedding_dim: int = int(_get_env("EMBEDDING_DIM", "1536"))
        # Rerank
        self.rerank_enabled: bool = _get_env("RERANK_ENABLED", "true").lower() == "true"
        self.rerank_model: str = _get_env("RERANK_MODEL", _get_env("DEEPINFRA_RERANK_MODEL", "Qwen/Qwen3-Reranker-0.6B"))
        self.rerank_top_k: int = int(_get_env("RERANK_TOP_K", "20"))
        self.cohere_api_key: str = _get_env("COHERE_API_KEY", "")
        # DB — POSTGRES_URL canonical, PG_DSN fallback (Neon)
        self.postgres_url: str = _get_env("POSTGRES_URL", "") or _get_env("PG_DSN", "postgresql://vivu:vivu@localhost:5432/vivu")
        self.qdrant_url: str = _get_env("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key: str = _get_env("QDRANT_API_KEY", "")
        self.qdrant_collection: str = _get_env("QDRANT_COLLECTION", "vivu_specs")
        # Redis cache (Upstash) — xử lý https REST URL tự chuyển sang rediss
        raw_redis = _get_env("REDIS_URL", "").strip()
        if raw_redis.startswith("https://"):
            token = _get_env("REDIS_TOKEN", "") or _get_env("UPSTASH_REDIS_REST_TOKEN", "")
            host = raw_redis.replace("https://", "").rstrip("/")
            if token and host:
                self.redis_url: str = f"rediss://default:{token}@{host}:6379"
            else:
                self.redis_url: str = "redis://localhost:6379/0"
        else:
            self.redis_url: str = raw_redis or "redis://localhost:6379/0"
        self.redis_token: str = _get_env("REDIS_TOKEN", "")
        self.cache_enabled: bool = _get_env("CACHE_ENABLED", "true").lower() == "true"
        self.rate_limit_enabled: bool = _get_env("RATE_LIMIT_ENABLED", "true").lower() == "true"
        self.rate_limit_rpm: int = int(_get_env("RATE_LIMIT_RPM", "30"))
        self.rate_limit_burst: int = int(_get_env("RATE_LIMIT_BURST", "5"))
        self.backpressure_max: int = int(_get_env("BACKPRESSURE_MAX", "50"))
        # Token limits (multi-turn safety)
        self.llm_max_output_tokens: int = int(_get_env("LLM_MAX_OUTPUT_TOKENS", "4000"))
        self.llm_tool_call_max_tokens: int = int(_get_env("LLM_TOOL_CALL_MAX_TOKENS", "1024"))
        self.llm_input_max_tokens: int = int(_get_env("LLM_INPUT_MAX_TOKENS", "16000"))
        self.llm_user_input_max_tokens: int = int(_get_env("LLM_USER_INPUT_MAX_TOKENS", "1000"))
        # Admin & Metrics Telemetry
        self.admin_api_key: str = _get_env("ADMIN_API_KEY", "")
        self.metrics_enabled: bool = _get_env("METRICS_ENABLED", "true").lower() == "true"
        self.usd_vnd_rate: float = float(_get_env("USD_VND_EXCHANGE_RATE", "25400.0"))
        self.app_version: str = _get_env("APP_VERSION", "v1.0.0")


def llm_extra_kwargs(model: str) -> dict:
    """Reasoning models cần giảm thinking tokens — gpt-* không cần."""
    m = model.lower()
    if "gpt-oss" in m:
        return {"reasoning_effort": "low"}
    if any(k in m for k in ("qwen", "luna", "o1", "o3", "gemini", "deepseek")):
        # gpt-* sẽ 400 nếu gửi reasoning_effort
        if "gpt" in m:
            return {}
        return {"reasoning_effort": "none"}
    return {}


settings = Settings()
