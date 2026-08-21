from dotenv import dotenv_values

_env = dotenv_values(".env")


class Settings:
    def __init__(self):
        # LLM (TokenRouter)
        self.openai_api_key: str = _env.get("OPENAI_API_KEY", "")
        self.openai_base_url: str = _env.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.llm_model: str = _env.get("LLM_MODEL", "openai/gpt-4o-mini")
        # Embedding + Rerank (OpenRouter)
        self.openrouter_api_key: str = _env.get("OPENROUTER_API_KEY", "")
        self.openrouter_embed_model: str = _env.get("OPENROUTER_EMBED_MODEL", "openai/text-embedding-3-small")
        # DB
        self.postgres_url: str = _env.get("POSTGRES_URL", "postgresql+asyncpg://vivu:vivu@localhost:5432/vivu")
        self.redis_url: str = _env.get("REDIS_URL", "redis://localhost:6379/0")
        self.qdrant_url: str = _env.get("QDRANT_URL", "http://localhost:6333")
        self.qdrant_api_key: str = _env.get("QDRANT_API_KEY", "")
        self.qdrant_collection: str = _env.get("QDRANT_COLLECTION", "vivu_specs")
        # Embedding (OpenAI direct — dùng chung OPENAI_API_KEY)
        self.embedding_model: str = _env.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self.embedding_dim: int = int(_env.get("EMBEDDING_DIM", "2048"))
        self.rerank_enabled: bool = _env.get("RERANK_ENABLED", "true").lower() == "true"
        self.rerank_model: str = _env.get("RERANK_MODEL", "cohere")
        self.rerank_top_k: int = int(_env.get("RERANK_TOP_K", "20"))
        self.cohere_api_key: str = _env.get("COHERE_API_KEY", "")

        # Telemetry & Admin Metrics (Thêm mới, giữ nguyên 100% code gốc bên trên)
        self.metrics_enabled: bool = _env.get("METRICS_ENABLED", "true").lower() == "true"
        self.admin_api_key: str = _env.get("ADMIN_API_KEY", "")
        self.usd_vnd_rate: float = float(_env.get("USD_VND_EXCHANGE_RATE", "25400.0"))
        self.app_version: str = _env.get("APP_VERSION", "v1.0.0")
        # Cache & Rate Limit
        self.cache_enabled: bool = _env.get("CACHE_ENABLED", "true").lower() == "true"
        self.rate_limit_enabled: bool = _env.get("RATE_LIMIT_ENABLED", "true").lower() == "true"


settings = Settings()
