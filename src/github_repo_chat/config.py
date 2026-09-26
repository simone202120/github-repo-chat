"""Application settings loaded from environment variables (and `.env` in local development)."""

from functools import lru_cache

from pydantic import SecretStr
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

    max_files: int = 500
    max_file_bytes: int = 200_000
    max_archive_bytes: int = 100_000_000
    download_timeout_s: float = 60.0

    code_chunk_lines: int = 60
    code_chunk_max_chars: int = 2000
    text_chunk_tokens: int = 512

    top_k: int = 6
    history_turns: int = 6

    api_url: str = "http://localhost:8000"

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
