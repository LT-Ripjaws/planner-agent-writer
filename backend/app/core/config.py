from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Planner Agent Writer API"
    environment: str = "development"
    database_url: str = "sqlite:///./backend/data/app.db"
    cors_origins: str = "http://localhost:3000"
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.kilo.ai/api/gateway"
    llm_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    tavily_api_key: str | None = None
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache # makes sure we create the settings object only once.
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
