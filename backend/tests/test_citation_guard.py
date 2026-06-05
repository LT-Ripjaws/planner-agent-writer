"""Citation guard (no real provider calls).

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


def test_extract_links_handles_parenthesized_urls():
    url = "https://en.wikipedia.org/wiki/Hallucination_(artificial_intelligence)"
    text = f"See [Wikipedia]({url})."
    assert extract_links(text) == [("Wikipedia", url)]


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


# --- node: off-whitelist link stripped deterministically ------------------


async def test_off_whitelist_link_stripped_without_llm(monkeypatch):
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    state = {
        "plan": _plan(),
        "evidence": EVIDENCE,
        "sections": [(1, "## Section 1\n\nBad [link](https://evil.com).")],
    }
    result = await citation_guard_node(state)

    assert "evil.com" not in result["final"]
    assert not any("unresolved" in w for w in result["warnings"])


# --- node: repair still invalid -> warning, draft preserved ---------------


async def test_repair_still_invalid_records_warning(monkeypatch):
    # With no evidence, even repair cannot satisfy a required citation.
    fake = FakeLLM(repair_markdown=lambda human: "## Section 1\n\nStill no citation.")
    monkeypatch.setattr(cg, "get_llm", lambda *a, **k: fake)

    state = {
        "plan": _plan(requires_citations=True),
        "evidence": [],
        "sections": [(1, "## Section 1\n\nNo citation.")],
    }
    result = await citation_guard_node(state)

    # Non-fatal: draft is preserved and a warning is recorded.
    assert any("unresolved" in w for w in result["warnings"])
    assert "Section 1" in result["final"]


async def test_required_citations_missing_adds_source_without_llm(monkeypatch):
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    state = {
        "plan": _plan(requires_citations=True),
        "evidence": EVIDENCE,
        "sections": [(1, "## Section 1\n\nNo citation at all.")],
    }
    result = await citation_guard_node(state)

    assert WL in result["final"]
    assert not any("unresolved" in w for w in result["warnings"])


async def test_bracketed_source_url_becomes_markdown_link(monkeypatch):
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    state = {
        "plan": _plan(requires_citations=True),
        "evidence": EVIDENCE,
        "sections": [(1, f"## Section 1\n\nClaim with odd citation 【{WL}】.")],
    }
    result = await citation_guard_node(state)

    assert f"[source]({WL})" in result["final"]
    assert "【" not in result["final"]
    assert not result["warnings"]


async def test_bracketed_markdown_link_is_unwrapped(monkeypatch):
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    state = {
        "plan": _plan(requires_citations=True),
        "evidence": EVIDENCE,
        "sections": [(1, f"## Section 1\n\nClaim with wrapped citation 【[Allowed]({WL})】.")],
    }
    result = await citation_guard_node(state)

    assert f"[Allowed]({WL})" in result["final"]
    assert "【" not in result["final"]
    assert not result["warnings"]


async def test_bracketed_source_label_maps_to_whitelisted_link(monkeypatch):
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    evidence = [
        {
            "title": "What Are AI Hallucinations? - IBM",
            "url": WL,
            "source": "ibm.com",
            "snippet": "s",
        }
    ]
    state = {
        "plan": _plan(requires_citations=True),
        "evidence": evidence,
        "sections": [(1, "## Section 1\n\nClaim with bracket label 【IBM】.")],
    }
    result = await citation_guard_node(state)

    assert f"[source]({WL})" in result["final"]
    assert "【" not in result["final"]
    assert not result["warnings"]


async def test_reference_definition_citation_lines_are_stripped(monkeypatch):
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    state = {
        "plan": _plan(requires_citations=True),
        "evidence": EVIDENCE,
        "sections": [
            (
                1,
                f"## Section 1\n\nClaim cites [Allowed]({WL}).\n\n[Allowed]: [source]({WL})",
            )
        ],
    }
    result = await citation_guard_node(state)

    assert f"[Allowed]({WL})" in result["final"]
    assert "[Allowed]:" not in result["final"]
    assert not result["warnings"]


async def test_nested_source_link_becomes_single_markdown_link(monkeypatch):
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    state = {
        "plan": _plan(requires_citations=True),
        "evidence": EVIDENCE,
        "sections": [(1, f"## Section 1\n\nClaim with bad link [[source]]([source]({WL}) text.")],
    }
    result = await citation_guard_node(state)

    assert f"[source]({WL})" in result["final"]
    assert "[[source]]" not in result["final"]
    assert not result["warnings"]


async def test_reasoning_before_expected_heading_is_stripped(monkeypatch):
    monkeypatch.setattr(
        cg, "get_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    state = {
        "plan": _plan(requires_citations=True),
        "evidence": EVIDENCE,
        "sections": [
            (
                1,
                "We need to write this section first.\n\n"
                "## Section 1\n\nFinal body without scratch text.",
            )
        ],
    }
    result = await citation_guard_node(state)

    assert "We need to write" not in result["final"]
    assert result["final"].count("## Section 1") == 1
    assert WL in result["final"]
