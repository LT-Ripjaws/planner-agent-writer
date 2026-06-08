from functools import lru_cache
from typing import TypeVar

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from backend.app.core.config import settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)

# Role -> (provider_setting, model_setting) lane mapping. Roles not listed
# (or role=None) fall back to the default Kilo provider + `llm_model`.
_ROLE_LANES: dict[str, tuple[str, str]] = {
    "writer": ("writer_provider", "writer_model"),
    "improvement": ("writer_provider", "writer_model"),
    "router": ("reasoning_provider", "reasoning_model"),
    "planner": ("reasoning_provider", "reasoning_model"),
    "evaluator": ("reasoning_provider", "reasoning_model"),
    "citation_repair": ("reasoning_provider", "reasoning_model"),
    "fallback": ("fallback_provider", "fallback_model"),
}


def require_llm_api_key() -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required but not set in the environment.")

    return settings.llm_api_key


def provider_registry() -> dict[str, tuple[str, str | None]]:
    """Map provider name -> (base_url, api_key).

    Add an OpenAI-compatible provider by adding an entry here plus its two
    config fields (base_url + api_key) — nothing else in the pipeline needs to
    change, since every provider is driven through the same `ChatOpenAI` client.
    """
    return {
        "kilo": (settings.llm_base_url, settings.llm_api_key),
        "openrouter": (settings.openrouter_base_url, settings.openrouter_api_key),
        "openai": (settings.openai_base_url, settings.openai_api_key),
    }


def provider_credentials(provider: str) -> tuple[str, str]:
    """Return (base_url, api_key) for a provider name.

    Unknown providers, or providers whose key isn't configured, transparently
    degrade to the default Kilo provider so the app always has a working client.
    """
    base_url, api_key = provider_registry().get(provider, ("", None))
    if api_key:
        return base_url, api_key
    return settings.llm_base_url, require_llm_api_key()


def resolve_role(role: str | None) -> tuple[str, str]:
    """Resolve a role to (provider, model).

    A role whose lane points at a provider without a configured key (e.g.
    `reasoning_provider="openrouter"` but no OpenRouter key, or
    `writer_provider="openai"` but no OpenAI key) transparently degrades to the
    default Kilo provider + `llm_model`, so the app works regardless of which
    extra providers are set up.
    """
    lane = _ROLE_LANES.get(role or "")
    if lane is None:
        return "kilo", settings.llm_model

    provider = getattr(settings, lane[0])
    model = getattr(settings, lane[1])
    _, api_key = provider_registry().get(provider, ("", None))
    if not api_key:
        return "kilo", settings.llm_model
    return provider, model


@lru_cache
def get_llm(
    model: str | None = None,
    temperature: float = 0.3,
    timeout: int | None = None,
    role: str | None = None,
) -> ChatOpenAI:
    """Build (and cache) a chat client for a pipeline role.

    `role` selects the provider + model lane from settings; an explicit `model`
    overrides the lane's model while keeping its provider. Falls back to the
    Kilo default when no role is given.
    """
    provider, role_model = resolve_role(role)
    base_url, api_key = provider_credentials(provider)
    return ChatOpenAI(
        model=model or role_model,
        api_key=SecretStr(api_key),
        base_url=base_url,
        temperature=temperature,
        timeout=timeout or settings.llm_timeout_seconds,
        # Keep the gateway-level retry at 1: structured() layers its own
        # `.with_retry(stop_after_attempt=2)` on top, so a higher value here
        # multiplies into very long worst-case latency now that the per-call
        # timeout is larger. Matches the tuned default in the plan.
        max_retries=1,
    )


def structured(llm: ChatOpenAI, schema: type[SchemaT]):
    return llm.with_structured_output(schema).with_retry(stop_after_attempt=2)


def with_role_fallback(primary: Runnable, fallback: Runnable) -> Runnable:
    """Wrap `primary` so it retries on `fallback` when it errors.

    No-op (returns `primary` unchanged) when `LLM_FALLBACK_ENABLED` is off —
    which is how the test suite keeps using simple fakes that don't implement
    `.with_fallbacks`.
    """
    if not settings.llm_fallback_enabled:
        return primary
    return primary.with_fallbacks([fallback])
