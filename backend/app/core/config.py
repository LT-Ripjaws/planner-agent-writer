from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = Field(
        default="Planner Agent Writer API",
        validation_alias="APP_NAME",
    )
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    database_url: str = Field(
        default="sqlite:///./backend/data/app.db",
        validation_alias="DATABASE_URL",
    )
    checkpoint_database_path: str = Field(
        default="./backend/data/checkpoints.db",
        validation_alias="CHECKPOINT_DATABASE_PATH",
    )
    run_fallback_timeout_seconds: int = Field(
        default=1800,
        validation_alias="RUN_FALLBACK_TIMEOUT_SECONDS",
    )
    rate_limit_runs_per_min: int = Field(
        default=6,
        validation_alias="RATE_LIMIT_RUNS_PER_MIN",
    )
    hitl_plan_approval_enabled: bool = Field(
        default=False,
        validation_alias="HITL_PLAN_APPROVAL_ENABLED",
    )
    hitl_approval_timeout_hours: int = Field(
        default=24,
        validation_alias="HITL_APPROVAL_TIMEOUT_HOURS",
    )
    quality_eval_enabled: bool = Field(
        default=True,
        validation_alias="QUALITY_EVAL_ENABLED",
    )
    quality_threshold: float = Field(
        default=7.0,
        validation_alias="QUALITY_THRESHOLD",
    )
    quality_max_iterations: int = Field(
        default=2,
        validation_alias="QUALITY_MAX_ITERATIONS",
    )
    quality_max_sections_per_iter: int = Field(
        default=3,
        validation_alias="QUALITY_MAX_SECTIONS_PER_ITER",
    )
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_base_url: str = Field(
        default="https://api.kilo.ai/api/gateway",
        validation_alias="LLM_BASE_URL",
    )
    llm_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b:free",
        validation_alias="LLM_MODEL",
    )
    llm_timeout_seconds: int = Field(default=90, validation_alias="LLM_TIMEOUT_SECONDS")
    tavily_api_key: str | None = Field(default=None, validation_alias="TAVILY_API_KEY")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
