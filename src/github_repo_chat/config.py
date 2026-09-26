"""Application settings loaded from environment variables (and `.env` in local development)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "google/gemini-3.8-flash"
    llm_temperature: float = 0.1

    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_host: str = "https://cloud.langfuse.com"

    qdrant_url: str = "http://localhost:6333"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    rerank_model: str = ""

    max_files: int = Field(default=500, gt=0)
    max_file_bytes: int = Field(default=200_000, gt=0)
    max_archive_bytes: int = Field(default=100_000_000, gt=0)
    download_timeout_s: float = Field(default=60.0, gt=0)

    code_chunk_lines: int = Field(default=60, gt=0)
    code_chunk_max_chars: int = Field(default=2000, gt=0)
    text_chunk_tokens: int = Field(default=512, gt=0)

    top_k: int = Field(default=6, gt=0)
    history_turns: int = Field(default=6, ge=0)

    api_url: str = "http://localhost:8000"

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
