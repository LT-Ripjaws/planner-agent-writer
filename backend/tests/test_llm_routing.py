"""Multi-provider per-role LLM routing (services/llm.py)."""
from __future__ import annotations

from langchain_core.runnables import RunnableLambda

from backend.app.services import llm as llm_mod


# --- resolve_role ---------------------------------------------------------


def test_resolve_role_writer_lane_is_kilo():
    provider, model = llm_mod.resolve_role("writer")
    assert provider == "kilo"
    assert model == llm_mod.settings.writer_model


def test_resolve_role_improvement_shares_writer_lane():
    assert llm_mod.resolve_role("improvement") == llm_mod.resolve_role("writer")


def test_resolve_role_reasoning_degrades_without_openrouter_key(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "openrouter_api_key", None)
    for role in ("router", "planner", "evaluator", "citation_repair"):
        provider, model = llm_mod.resolve_role(role)
        assert provider == "kilo"
        assert model == llm_mod.settings.llm_model


def test_resolve_role_reasoning_uses_openrouter_when_key_present(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "openrouter_api_key", "sk-or-test")
    for role in ("router", "planner", "evaluator", "citation_repair"):
        provider, model = llm_mod.resolve_role(role)
        assert provider == "openrouter"
        assert model == llm_mod.settings.reasoning_model


def test_resolve_role_fallback_lane():
    provider, model = llm_mod.resolve_role("fallback")
    assert provider == "kilo"
    assert model == llm_mod.settings.fallback_model


def test_resolve_role_unknown_defaults_to_kilo_llm_model():
    assert llm_mod.resolve_role(None) == ("kilo", llm_mod.settings.llm_model)
    assert llm_mod.resolve_role("nope") == ("kilo", llm_mod.settings.llm_model)


# --- provider_credentials -------------------------------------------------


def test_provider_credentials_kilo():
    base, key = llm_mod.provider_credentials("kilo")
    assert base == llm_mod.settings.llm_base_url
    assert key == llm_mod.settings.llm_api_key


def test_provider_credentials_openrouter_with_key(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "openrouter_api_key", "sk-or-test")
    base, key = llm_mod.provider_credentials("openrouter")
    assert base == llm_mod.settings.openrouter_base_url
    assert key == "sk-or-test"


def test_provider_credentials_openrouter_without_key_degrades_to_kilo(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "openrouter_api_key", None)
    base, key = llm_mod.provider_credentials("openrouter")
    assert base == llm_mod.settings.llm_base_url


# --- third provider: OpenAI (config-only) ---------------------------------


def test_provider_credentials_openai_with_key(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "openai_api_key", "sk-test")
    base, key = llm_mod.provider_credentials("openai")
    assert base == llm_mod.settings.openai_base_url
    assert key == "sk-test"


def test_resolve_role_uses_openai_when_lane_and_key_set(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(llm_mod.settings, "writer_provider", "openai")
    monkeypatch.setattr(llm_mod.settings, "writer_model", "gpt-4o-mini")
    assert llm_mod.resolve_role("writer") == ("openai", "gpt-4o-mini")


def test_resolve_role_openai_degrades_without_key(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "openai_api_key", None)
    monkeypatch.setattr(llm_mod.settings, "writer_provider", "openai")
    provider, model = llm_mod.resolve_role("writer")
    assert provider == "kilo"
    assert model == llm_mod.settings.llm_model


# --- with_role_fallback ---------------------------------------------------


def test_with_role_fallback_disabled_returns_primary_unchanged(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "llm_fallback_enabled", False)
    primary = RunnableLambda(lambda _: "primary")
    fallback = RunnableLambda(lambda _: "fallback")
    chain = llm_mod.with_role_fallback(primary, fallback)
    assert chain is primary


async def test_with_role_fallback_enabled_recovers_on_primary_error(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "llm_fallback_enabled", True)

    def boom(_):
        raise ValueError("primary down")

    primary = RunnableLambda(boom)
    fallback = RunnableLambda(lambda _: "recovered")
    chain = llm_mod.with_role_fallback(primary, fallback)
    assert await chain.ainvoke("x") == "recovered"
