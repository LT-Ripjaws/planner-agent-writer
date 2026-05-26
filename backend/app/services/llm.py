from functools import lru_cache
from typing import TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from backend.app.core.config import settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)

def require_openai_api_key() -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required but not set in the environment.")
    return settings.openai_api_key

@lru_cache
def get_llm(model: str | None = None, temperature: float = 0.3) -> ChatOpenAI:
     return ChatOpenAI(
        model=model or settings.openai_model,
        api_key=SecretStr(require_openai_api_key()),
        temperature=temperature,
    )

def structured(llm: ChatOpenAI, schema: type[SchemaT]):
    return llm.with_structured_output(schema).with_retry(stop_after_attempt=2)