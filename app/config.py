import os
from dotenv import dotenv_values

_file_env = dotenv_values(".env") if os.path.exists(".env") else {}
# os.environ (Render/Docker/System) có độ ưu tiên cao hơn file .env
_env = {**_file_env, **{k: v for k, v in os.environ.items() if v is not None}}


class Settings:
    def __init__(self):
        # LLM + Embedding — single OpenAI key (unified)
        # Fallback OPENROUTER_/DEEPINFRA_ để .env cũ vẫn chạy trong giai đoạn migration
        self.openai_api_key: str = (
            _env.get("OPENAI_API_KEY", "") or _env.get("OPENROUTER_API_KEY", "") or _env.get("DEEPINFRA_API_KEY", "")
        )
        self.openai_base_url: str = _env.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        raw_llm = _env.get("LLM_MODEL", "gpt-5.6-luna").strip()
        # Strip prefix "openai/" nếu .env cũ để OPENAI_API_KEY qua OpenRouter/TokenRouter
        self.llm_model: str = raw_llm.split("/", 1)[-1] if "/" in raw_llm else raw_llm
        # Embed model: ưu tiên OPENAI_EMBED_MODEL, fallback OPENROUTER_EMBED_MODEL để tương thích .env cũ
        raw_embed = (
            _env.get("OPENAI_EMBED_MODEL")
            or _env.get("OPENROUTER_EMBED_MODEL")
            or _env.get("EMBEDDING_MODEL")
            or "text-embedding-3-small"
        ).strip()
        self.openai_embed_model: str = raw_embed.split("/", 1)[-1] if "/" in raw_embed else raw_embed
        # Deprecated aliases — giữ để code cũ không vỡ, nhưng đều trỏ về OpenAI key duy nhất
        self.openrouter_api_key: str = self.openai_api_key
        self.openrouter_embed_model: str = self.openai_embed_model
        # DB — POSTGRES_URL canonical, PG_DSN fallback (Neon .env cũ dùng PG_DSN)
        self.postgres_url: str = (
            _env.get("POSTGRES_URL") or _env.get("PG_DSN") or "postgresql+asyncpg://vivu:vivu@localhost:5432/vivu"
        )
        raw_redis = _env.get("REDIS_URL", "redis://localhost:6379/0").strip()
        # .env hiện tại đang để Upstash REST URL https://... + REDIS_TOKEN — redis-py không hiểu https
        # Tự chuyển sang rediss:// nếu phát hiện https Upstash, hoặc fallback localhost nếu không đủ token
        if raw_redis.startswith("https://"):
            token = _env.get("REDIS_TOKEN", "") or _env.get("UPSTASH_REDIS_REST_TOKEN", "")
            # Upstash REST host -> rediss host: https://correct-ladybug-xxx.upstash.io -> correct-ladybug-xxx.upstash.io
            host = raw_redis.replace("https://", "").rstrip("/")
            if token and host:
                self.redis_url: str = f"rediss://default:{token}@{host}:6379"
            else:
                self.redis_url: str = "redis://localhost:6379/0"
        else:
            self.redis_url: str = raw_redis
        self.qdrant_url: str = _env.get("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key: str = _env.get("QDRANT_API_KEY", "")
        self.qdrant_collection: str = _env.get("QDRANT_COLLECTION", "vivu_specs")
        self.embedding_model: str = _env.get("EMBEDDING_MODEL", self.openai_embed_model)
        self.embedding_dim: int = int(_env.get("EMBEDDING_DIM", "1536"))
        self.rerank_enabled: bool = _env.get("RERANK_ENABLED", "true").lower() == "true"
        self.rerank_model: str = _env.get("RERANK_MODEL", "cohere")
        self.rerank_top_k: int = int(_env.get("RERANK_TOP_K", "20"))
        self.cohere_api_key: str = _env.get("COHERE_API_KEY", "")

        # Telemetry & Admin Metrics (Thêm mới, giữ nguyên 100% code gốc bên trên)
        self.metrics_enabled: bool = _env.get("METRICS_ENABLED", "true").lower() == "true"
        self.admin_api_key: str = _env.get("ADMIN_API_KEY", "")
        self.usd_vnd_rate: float = float(_env.get("USD_VND_EXCHANGE_RATE", "25400.0"))
        self.app_version: str = _env.get("APP_VERSION", "v1.0.0")
        # LLM fallback model (dùng khi model chính lỗi trước khi stream)
        raw_fallback = _env.get("LLM_FALLBACK_MODEL", "") or _env.get("DEEPINFRA_FALLBACK_MODEL", "")
        raw_fallback = raw_fallback.strip()
        self.llm_fallback_model: str = raw_fallback.split("/", 1)[-1] if "/" in raw_fallback else raw_fallback
        # LLM token limits (fallback nếu .env chưa có, dùng cho llm.py)
        self.llm_max_output_tokens: int = int(_env.get("LLM_MAX_OUTPUT_TOKENS", "1024"))
        self.llm_tool_call_max_tokens: int = int(_env.get("LLM_TOOL_CALL_MAX_TOKENS", "512"))
        self.llm_user_input_max_tokens: int = int(_env.get("LLM_USER_INPUT_MAX_TOKENS", "4000"))
        self.llm_input_max_tokens: int = int(_env.get("LLM_INPUT_MAX_TOKENS", "8000"))
        # DeepInfra compat — trỏ về OpenAI để llm.py cũ không vỡ
        self.deepinfra_api_key: str = self.openai_api_key
        self.deepinfra_base_url: str = self.openai_base_url
        self.langfuse_enabled: bool = False
        self.langfuse_public_key: str = ""
        self.langfuse_secret_key: str = ""
        self.langfuse_host: str = ""
        # Cache & Rate Limit
        self.cache_enabled: bool = _env.get("CACHE_ENABLED", "true").lower() == "true"
        self.rate_limit_enabled: bool = _env.get("RATE_LIMIT_ENABLED", "true").lower() == "true"


def llm_extra_kwargs(model: str) -> dict:
    """Reasoning models (luna, o1, o3, o4) cần tắt reasoning tokens (reasoning_effort='none')
    để giảm TTFT và tương thích với function tools trên /v1/chat/completions."""
    m = (model or "").lower()
    if any(k in m for k in ("luna", "o1", "o3", "o4", "reasoning")):
        return {"reasoning_effort": "none"}
    return {}


settings = Settings()
