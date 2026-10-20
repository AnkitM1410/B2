from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://memory:memory@localhost:5432/memory_graph"
    api_key: str = ""

    llm_model: str = "openai/gpt-4o-mini"
    llm_api_key: str = ""
    llm_api_base: str = ""

    embedding_model: str = "openai/text-embedding-3-small"
    embedding_api_key: str = ""
    embedding_api_base: str = ""
    embedding_dim: int = 1536

    stt_model: str = "openai/whisper-1"
    stt_api_key: str = ""
    stt_api_base: str = ""

    tts_provider: str = "groq"
    tts_api_key: str = ""
    tts_api_base: str = "https://api.groq.com/openai/v1"
    tts_model: str = "playai-tts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
