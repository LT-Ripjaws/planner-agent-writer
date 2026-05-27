from functools import lru_cache
from typing import TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from backend.app.core.config import settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def require_llm_api_key() -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required but not set in the environment.")

    return settings.llm_api_key


@lru_cache
def get_llm(model: str | None = None, temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.llm_model,
        api_key=SecretStr(require_llm_api_key()),
        base_url=settings.llm_base_url,
        temperature=temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )


def structured(llm: ChatOpenAI, schema: type[SchemaT]):
    return llm.with_structured_output(schema).with_retry(stop_after_attempt=2)
