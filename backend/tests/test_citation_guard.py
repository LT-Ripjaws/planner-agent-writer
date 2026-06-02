"""T4 — citation guard (no real provider calls).

Covers: clean markdown passes untouched; an off-whitelist link triggers one
repair pass that can succeed; a repair that still violates preserves the draft
and records a warning (non-fatal in V1); off-whitelist images are stripped;
required-citation coverage is enforced. Pure helpers are also unit-tested.
"""
from __future__ import annotations

from backend.app.agents.nodes import citation_guard as cg
from backend.app.agents.nodes.citation_guard import (
    citation_guard_node,
    evidence_url_whitelist,
    extract_links,
    rebuild_final,
    section_violations,
    strip_disallowed_images,
)
from backend.tests.fakes import FakeLLM


WL = "https://allowed.com/a"
EVIDENCE = [{"title": "Allowed", "url": WL, "snippet": "s", "score": 0.9}]


def _plan(requires_citations: bool = False) -> dict:
    return {
        "blog_title": "Title",
        "audience": "general",
        "tone": "neutral",
        "blog_kind": "explainer",
        "constraints": [],
        "tasks": [
            {
                "id": 1,
                "title": "Section 1",
                "goal": "g",
                "bullets": ["a", "b", "c"],
                "target_words": 150,
                "tags": [],
                "requires_research": requires_citations,
                "requires_citations": requires_citations,
                "requires_code": False,
            }
        ],
    }


# --- pure helpers ---------------------------------------------------------


def test_extract_links_ignores_images():
    text = "A [link](https://x.com) and an ![img](https://y.com/i.png)."
    assert extract_links(text) == [("link", "https://x.com")]


def test_whitelist_from_evidence():
    assert evidence_url_whitelist(EVIDENCE) == {WL}


def test_strip_disallowed_images():
    text = f"Keep ![ok]({WL}) drop ![bad](https://evil.com/x.png)."
    cleaned, stripped = strip_disallowed_images(text, {WL})
    assert "evil.com" not in cleaned
    assert WL in cleaned
    assert stripped == ["https://evil.com/x.png"]


def test_section_violations_flags_off_whitelist_link():
    text = "See [bad](https://evil.com)."
    issues = section_violations(text, requires_citations=False, allowed_urls={WL})
    assert any("off-whitelist" in i for i in issues)


def test_section_violations_requires_citation_coverage():
    text = "No links here."
    issues = section_violations(text, requires_citations=True, allowed_urls={WL})
    assert any("requires_citations" in i for i in issues)


def test_rebuild_final_orders_and_titles():
    final = rebuild_final("T", [(2, "B"), (1, "A")])
    assert final.startswith("# T")
    assert final.index("A") < final.index("B")


# --- node: clean passthrough ---------------------------------------------


async def test_clean_markdown_passes_through(monkeypatch):
    # No LLM should be called when there are no violations.
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )
    state = {
        "plan": _plan(),
        "evidence": EVIDENCE,
        "sections": [(1, f"## Section 1\n\nClean body with [cite]({WL}).")],
    }
    result = await citation_guard_node(state)

    assert result["warnings"] == []
    assert WL in result["final"]
    assert result["sections"][0][1].strip().startswith("## Section 1")


# --- node: off-whitelist link repaired successfully -----------------------


async def test_off_whitelist_link_repaired(monkeypatch):
    fake = FakeLLM(
        repair_markdown=lambda human: f"## Section 1\n\nFixed body citing [src]({WL})."
    )
    monkeypatch.setattr(cg, "get_llm", lambda *a, **k: fake)

    state = {
        "plan": _plan(),
        "evidence": EVIDENCE,
        "sections": [(1, "## Section 1\n\nBad [link](https://evil.com).")],
    }
    result = await citation_guard_node(state)

    # Repaired section now only cites the whitelisted url; no unresolved warning.
    assert "evil.com" not in result["final"]
    assert WL in result["final"]
    assert not any("unresolved" in w for w in result["warnings"])


# --- node: repair still invalid -> warning, draft preserved ---------------


async def test_repair_still_invalid_records_warning(monkeypatch):
    # The repair "fixes" nothing — still points off-whitelist.
    fake = FakeLLM(
        repair_markdown=lambda human: "## Section 1\n\nStill [bad](https://evil.com)."
    )
    monkeypatch.setattr(cg, "get_llm", lambda *a, **k: fake)

    state = {
        "plan": _plan(),
        "evidence": EVIDENCE,
        "sections": [(1, "## Section 1\n\nBad [link](https://evil.com).")],
    }
    result = await citation_guard_node(state)

    # Non-fatal: draft is preserved and a warning is recorded.
    assert any("unresolved" in w for w in result["warnings"])
    assert "Section 1" in result["final"]


async def test_required_citations_missing_triggers_repair(monkeypatch):
    fake = FakeLLM(
        repair_markdown=lambda human: f"## Section 1\n\nNow cites [src]({WL})."
    )
    monkeypatch.setattr(cg, "get_llm", lambda *a, **k: fake)

    state = {
        "plan": _plan(requires_citations=True),
        "evidence": EVIDENCE,
        "sections": [(1, "## Section 1\n\nNo citation at all.")],
    }
    result = await citation_guard_node(state)

    assert WL in result["final"]
    assert not any("unresolved" in w for w in result["warnings"])
