"""Output-safety pass over the final Markdown.

Two responsibilities, both whitelist-driven:

1. **Link whitelist**: every Markdown link `[text](url)` must point to a
   URL that appears in `state["evidence"]`. Off-whitelist links are
   violations.
2. **Image whitelist**: every Markdown image `![alt](url)` must also be
   whitelisted. Default policy is to **strip** non-whitelisted images
   outright — images carry no semantic information we need to preserve, so
   repair is unnecessary.
3. **Required-citation coverage**: a section whose source `Task` has
   `requires_citations=True` must contain at least one whitelisted link.

When violations are found, the guard delegates to a single repair pass per
offending section using `CITATION_REPAIR_SYSTEM`. If the repair still
violates the whitelist, the section keeps its (now-cleaned) draft text and a
warning is recorded; the run is marked failed by the runner via
`CitationGuardFailed`.
"""
from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.prompts import CITATION_REPAIR_SYSTEM, wrap_untrusted
from backend.app.agents.state import State
from backend.app.services.llm import get_llm

logger = logging.getLogger(__name__)

# Regexes for Markdown links and images. Standard `[text](url)` / `![alt](url)`.
# We intentionally do NOT match raw `<http://...>` autolinks because the writer
# is instructed to use the descriptive-anchor `[text](url)` form.
_LINK_RE = re.compile(r"(?<!\!)\[(?P<text>[^\]]*)\]\((?P<url>[^)\s]+)\)")
_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)\)")


def log(message: str) -> None:
    print(f"[citation_guard] {message}", file=sys.stderr, flush=True)


class CitationGuardFailed(Exception):
    """Raised when citation guard cannot repair output to a passing state.

    Carries:
    - ``draft``: the partially-repaired markdown (the run can still preserve it)
    - ``warnings``: human-readable list of remaining violations
    """

    def __init__(self, draft: str, warnings: list[str]) -> None:
        self.draft = draft
        self.warnings = warnings
        super().__init__(
            f"citation guard failed with {len(warnings)} unresolved violation(s)"
        )


# ---------------------------------------------------------------------------
# Extraction helpers


def extract_links(text: str) -> list[tuple[str, str]]:
    """Return list of (anchor_text, url) for every Markdown link."""
    return [(m.group("text"), m.group("url")) for m in _LINK_RE.finditer(text)]


def extract_images(text: str) -> list[tuple[str, str]]:
    """Return list of (alt_text, url) for every Markdown image."""
    return [(m.group("alt"), m.group("url")) for m in _IMAGE_RE.finditer(text)]


def evidence_url_whitelist(evidence: Iterable[dict[str, Any]]) -> set[str]:
    return {
        item["url"]
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    }


# ---------------------------------------------------------------------------
# Per-section operations


def strip_disallowed_images(section: str, allowed_urls: set[str]) -> tuple[str, list[str]]:
    """Remove `![alt](url)` whose url is not whitelisted.

    Returns (cleaned_text, stripped_urls). Stripped images are replaced with
    empty string — they carry no semantic content we want to preserve.
    """
    stripped: list[str] = []

    def replace(match: re.Match[str]) -> str:
        url = match.group("url")
        if url in allowed_urls:
            return match.group(0)
        stripped.append(url)
        return ""

    cleaned = _IMAGE_RE.sub(replace, section)
    return cleaned, stripped


def section_violations(
    section: str,
    requires_citations: bool,
    allowed_urls: set[str],
) -> list[str]:
    """Detect link/citation violations in a single section.

    (Image violations are repaired by stripping before this runs, so they
    don't surface here.)
    """
    issues: list[str] = []

    # 1. Off-whitelist links
    for anchor, url in extract_links(section):
        if url not in allowed_urls:
            issues.append(f"off-whitelist link to {url} (anchor: {anchor!r})")

    # 2. Required-citation coverage
    if requires_citations:
        has_whitelisted_link = any(
            url in allowed_urls for _, url in extract_links(section)
        )
        if not has_whitelisted_link:
            issues.append("requires_citations=true but no whitelisted citations present")

    return issues


# ---------------------------------------------------------------------------
# Repair 


async def repair_section(
    section: str,
    task: dict[str, Any],
    evidence: list[dict[str, Any]],
    issues: list[str],
) -> str:
    """One repair pass per offending section using CITATION_REPAIR_SYSTEM."""
    llm = get_llm(temperature=0.2)
    prompt = f"""
{wrap_untrusted("section", section)}

{wrap_untrusted("task", str(task))}

{wrap_untrusted("evidence", str(evidence))}

Issues to fix:
- """ + "\n- ".join(issues) + """

Rewrite the section above to address every issue.
""".strip()

    response = await llm.ainvoke(
        [
            SystemMessage(content=CITATION_REPAIR_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )
    content = response.content
    if isinstance(content, list):
        return "\n".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part)
            for part in content
        ).strip()
    return str(content).strip()


# ---------------------------------------------------------------------------
# Final-assembly helpers


def rebuild_final(blog_title: str, sections: list[tuple[int, str]]) -> str:
    ordered = [body for _, body in sorted(sections, key=lambda item: item[0])]
    body = "\n\n".join(s.strip() for s in ordered if s.strip())
    return f"# {blog_title}\n\n{body}".strip()


def tasks_by_id(plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    tasks = plan.get("tasks") if isinstance(plan, dict) else None
    if not isinstance(tasks, list):
        return {}
    return {t["id"]: t for t in tasks if isinstance(t, dict) and "id" in t}


# ---------------------------------------------------------------------------
# Node entry point 


async def citation_guard_node(state: State) -> State:
    """Whitelist + repair pass over the final Markdown.

    Inspects `state["sections"]` (not `state["final"]`) so we can repair
    per-section with the task's specific requires_citations setting, then
    rebuild `final` from the cleaned sections.
    """
    sections: list[tuple[int, str]] = list(state.get("sections", []))
    evidence: list[dict[str, Any]] = list(state.get("evidence", []))
    plan: dict[str, Any] = state.get("plan") or {}

    if not sections or not isinstance(plan, dict):
        return {}

    allowed_urls = evidence_url_whitelist(evidence)
    tasks = tasks_by_id(plan)
    blog_title = plan.get("blog_title", "Untitled")

    new_sections: list[tuple[int, str]] = []
    new_warnings: list[str] = []
    unresolved_per_section: dict[int, list[str]] = {}

    for task_id, body in sections:
        task = tasks.get(task_id) or {}
        requires_citations = bool(task.get("requires_citations"))

        # strip disallowed images BEFORE link analysis
        cleaned, stripped_image_urls = strip_disallowed_images(body, allowed_urls)
        if stripped_image_urls:
            log(f"task={task_id} stripped {len(stripped_image_urls)} off-whitelist image(s)")
            new_warnings.append(
                f"citation_guard task={task_id} stripped images: {stripped_image_urls}"
            )

        # detect link / coverage violations
        violations = section_violations(cleaned, requires_citations, allowed_urls)

        if not violations:
            new_sections.append((task_id, cleaned))
            continue

        # repair pass
        log(f"task={task_id} has {len(violations)} violation(s); running one repair pass")
        try:
            repaired = await repair_section(cleaned, task, evidence, violations)
        except Exception as exc:  # noqa: BLE001 — provider failures get caught here
            log(f"task={task_id} repair raised {type(exc).__name__}: {exc}")
            new_warnings.append(
                f"citation_guard task={task_id} repair failed: {type(exc).__name__}"
            )
            new_sections.append((task_id, cleaned))
            unresolved_per_section[task_id] = violations
            continue

        # Strip any newly-introduced disallowed images before re-checking
        repaired, stripped_post = strip_disallowed_images(repaired, allowed_urls)
        if stripped_post:
            new_warnings.append(
                f"citation_guard task={task_id} post-repair stripped images: {stripped_post}"
            )

        # Re-check after repair
        remaining = section_violations(repaired, requires_citations, allowed_urls)
        if remaining:
            log(f"task={task_id} still has {len(remaining)} violation(s) after repair")
            unresolved_per_section[task_id] = remaining
            new_warnings.append(
                f"citation_guard task={task_id} unresolved after repair: {remaining}"
            )
            new_sections.append((task_id, repaired))
        else:
            log(f"task={task_id} repair succeeded")
            new_sections.append((task_id, repaired))

    final = rebuild_final(blog_title, new_sections)

    # if any section is still violating after repair, we surface the
    # warnings into state but DO NOT raise here. The graph still completes
    # so the user gets the draft. The runner inspects warnings to decide
    # whether to mark the run failed.
    return {
        "sections": new_sections,
        "warnings": new_warnings,
        "final": final,
    }
