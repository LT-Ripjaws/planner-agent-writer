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
        default=3600,
        validation_alias="RUN_FALLBACK_TIMEOUT_SECONDS",
    )
    writer_timeout_seconds: int = Field(
        default=600,
        validation_alias="WRITER_TIMEOUT_SECONDS",
    )
    # Max writers running at once in the fanout super-step.
    writer_max_concurrency: int = Field(
        default=2,
        validation_alias="WRITER_MAX_CONCURRENCY",
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
        default=1,
        validation_alias="QUALITY_MAX_SECTIONS_PER_ITER",
    )
    quality_node_timeout_seconds: int = Field(
        # Budget for one full evaluate -> improve -> re-evaluate cycle at the
        # 280s per-call ceiling (280 * 3 = 840). Keeps QUALITY_MAX_SECTIONS_PER_ITER
        # at 1 so the validating re-eval fits inside the budget.
        default=900,
        validation_alias="QUALITY_NODE_TIMEOUT_SECONDS",
    )

    quality_llm_timeout_seconds: int = Field(
        default=280,
        validation_alias="QUALITY_LLM_TIMEOUT_SECONDS",
    )

    evaluator_max_sections_per_call: int = Field(
        default=4,
        validation_alias="EVALUATOR_MAX_SECTIONS_PER_CALL",
    )
    quality_min_improvement_seconds: int = Field(
        default=90,
        validation_alias="QUALITY_MIN_IMPROVEMENT_SECONDS",
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
    llm_timeout_seconds: int = Field(default=180, validation_alias="LLM_TIMEOUT_SECONDS")

    # --- Multi-provider routing -------------------------------------------
    # Second provider: OpenRouter (OpenAI-compatible). Used for the reasoning
    # lane below when a key is set; otherwise those roles transparently fall
    # back to the default Kilo provider so the app still works key-less.
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias="OPENROUTER_BASE_URL",
    )
    # Third provider slot: OpenAI (or any OpenAI-compatible endpoint). Inactive
    # until OPENAI_API_KEY is set; then a lane can use provider="openai".
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias="OPENAI_BASE_URL",
    )

    # Per-role model routing. provider is "kilo" or "openrouter".
    # Writer lane (writers + improvement): fast prose model on Kilo (no per-min
    # cap, so the parallel fanout isn't throttled).
    writer_provider: str = Field(default="kilo", validation_alias="WRITER_PROVIDER")
    writer_model: str = Field(
        default="stepfun/step-3.7-flash:free",
        validation_alias="WRITER_MODEL",
    )
    # Reasoning lane (router, planner, evaluator, citation repair): strong
    # structured model on OpenRouter (separate infra → not subject to Kilo's
    # ~300s gateway 524s; the evaluator especially benefits).
    reasoning_provider: str = Field(default="openrouter", validation_alias="REASONING_PROVIDER")
    reasoning_model: str = Field(
        default="moonshotai/kimi-k2.6:free",
        validation_alias="REASONING_MODEL",
    )
    # Cross-provider fallback for the reasoning lane: if the primary errors
    # (OpenRouter 503/429/timeout), retry on this provider+model.
    llm_fallback_enabled: bool = Field(default=True, validation_alias="LLM_FALLBACK_ENABLED")
    fallback_provider: str = Field(default="kilo", validation_alias="FALLBACK_PROVIDER")
    fallback_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b:free",
        validation_alias="FALLBACK_MODEL",
    )

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
