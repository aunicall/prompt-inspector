"""Application configuration loaded from environment variables."""

from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/prompt_inspector"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_DETECTION_CACHE_TTL: int = 86400
    REDIS_DETECTION_CACHE_PREFIX: str = "pi:detect:"

    # Fixed API Key for authentication (frontend & API consumers)
    API_KEY: str = "change-me-in-production"

    # Embedding provider: "self_hosted" or "bailian"
    EMBEDDING_PROVIDER: str = "self_hosted"

    # Self-hosted embedding service (TEI / OpenAI-compatible)
    EMBEDDING_BASE_URL: str = "http://127.0.0.1:8080/v1"
    EMBEDDING_API_KEY: str = "not-needed"
    EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"
    EMBEDDING_DIM: int = 1024

    # Bailian (DashScope) embedding service
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_MODEL: str = "text-embedding-v3"
    DASHSCOPE_DIMENSIONS: int = 1024

    EMBEDDING_BATCH_SIZE: int = 10

    # Vector search
    VECTOR_HNSW_EF_SEARCH: int = 32

    # Similarity score thresholds
    VEC_SIM_LOW: float = 0.60
    VEC_SIM_HIGH: float = 0.85

    # LLM review triggers variant augmentation when score exceeds this
    SUSPICIOUS_TEXT_TH: float = 0.60

    # LLM review: deepseek | qwen | genai
    LLM_REVIEW_PROVIDER: str = "genai"
    LLM_REVIEW_MODEL: str = "gemini-2.0-flash-lite"
    LLM_REVIEW_THINK_LEVEL: str = "LOW"

    # LLM variant augmentation (independent from review)
    LLM_AUGMENT_PROVIDER: str = "genai"
    LLM_AUGMENT_MODEL: str = "gemini-2.0-flash-lite"
    LLM_AUGMENT_THINK_LEVEL: str = "LOW"

    # Long-text sliding window
    TEXT_CHUNK_SIZE: int = 800
    TEXT_CHUNK_OVERLAP: int = 200

    # Max input text length
    MAX_TEXT_LENGTH: int = 5000

    # Application
    APP_NAME: str = "Prompt Inspector"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Debug mode
    DEBUG_MODE: bool = False

    model_config = SettingsConfigDict(
        env_file=(str(BASE_DIR / ".env.example"), str(BASE_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
