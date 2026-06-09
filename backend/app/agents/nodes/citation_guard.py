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

When violations are found, the guard first applies deterministic fixes:
normalize bare/bracketed source URLs into Markdown links, strip unsupported
links/images, and add a whitelisted source link when a citations-required
section has none. Only stubborn cases delegate to a single LLM repair pass.
If repair still violates the whitelist, the cleaned draft is preserved and a
warning is recorded.
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.markdown_sanitize import (
    clean_title,
    compact_evidence_for_prompt,
    sanitize_section_markdown,
)
from backend.app.agents.prompts import CITATION_REPAIR_SYSTEM, wrap_untrusted
from backend.app.agents.state import State
from backend.app.core.config import settings
from backend.app.services.llm import get_llm, with_role_fallback

logger = logging.getLogger(__name__)

_BRACKET_OPEN = "\u3010"
_BRACKET_CLOSE = "\u3011"
_RAW_URL_RE = re.compile(r"https?://[^\s<>\]]+")
_BRACKETED_URL_RE = re.compile(
    r"(?:" + re.escape(_BRACKET_OPEN) + r"|\{)\s*"
    r"(?P<url>https?://[^\s" + re.escape(_BRACKET_CLOSE) + r"}]+)\s*"
    r"(?:" + re.escape(_BRACKET_CLOSE) + r"|\})"
)
_BRACKETED_LABEL_RE = re.compile(
    rf"{re.escape(_BRACKET_OPEN)}\s*(?P<label>[^{re.escape(_BRACKET_CLOSE)}]{{1,120}}?)\s*{re.escape(_BRACKET_CLOSE)}"
)
_REFERENCE_DEFINITION_RE = re.compile(r"^\s*\[[^\]]+\]:\s*.*$")
_NESTED_SOURCE_LINK_RE = re.compile(
    r"\[\[[^\]]+\]\]\(\[(?P<anchor>[^\]]+)\]\((?P<url>https?://[^\s]+?)\)"
)


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


def _iter_markdown_spans(
    text: str,
    *,
    image: bool,
) -> list[tuple[int, int, str, str]]:
    spans: list[tuple[int, int, str, str]] = []
    index = 0

    while index < len(text):
        if image:
            start = text.find("![", index)
            if start == -1:
                break
            label_start = start + 2
        else:
            start = text.find("[", index)
            if start == -1:
                break
            if start > 0 and text[start - 1] == "!":
                index = start + 1
                continue
            label_start = start + 1

        label_end = text.find("]", label_start)
        if label_end == -1 or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            index = start + 1
            continue

        url_start = label_end + 2
        url_end = url_start
        depth = 0
        while url_end < len(text):
            char = text[url_end]
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            url_end += 1

        if url_end >= len(text):
            index = start + 1
            continue

        label = text[label_start:label_end]
        url = text[url_start:url_end].strip()
        spans.append((start, url_end + 1, label, url))
        index = url_end + 1

    return spans


def extract_links(text: str) -> list[tuple[str, str]]:
    """Return list of (anchor_text, url) for every Markdown link."""
    return [(label, url) for _, _, label, url in _iter_markdown_spans(text, image=False)]


def extract_images(text: str) -> list[tuple[str, str]]:
    """Return list of (alt_text, url) for every Markdown image."""
    return [(label, url) for _, _, label, url in _iter_markdown_spans(text, image=True)]


def evidence_url_whitelist(evidence: Iterable[dict[str, Any]]) -> set[str]:
    return {
        item["url"]
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    }


def canonical_allowed_url(raw_url: str, allowed_urls: set[str]) -> str | None:
    url = raw_url.strip().strip("<>")
    if url in allowed_urls:
        return url

    candidates = [url]
    if url.endswith("}"):
        candidates.append(f"{url[:-1]})")

    trimmed = url
    for _ in range(12):
        if not trimmed:
            break
        last = trimmed[-1]
        if last in f".,;!?]}}{_BRACKET_CLOSE}'\"":
            trimmed = trimmed[:-1]
            candidates.append(trimmed)
            continue
        if last == "}" and f"{trimmed[:-1]})" in allowed_urls:
            candidates.append(f"{trimmed[:-1]})")
        if last == ")" and trimmed not in allowed_urls:
            trimmed = trimmed[:-1]
            candidates.append(trimmed)
            continue
        break

    for candidate in candidates:
        if candidate in allowed_urls:
            return candidate

    return None


def _inside_span(index: int, spans: list[tuple[int, int, str, str]]) -> bool:
    return any(start <= index < end for start, end, _, _ in spans)


def _canonical_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _domain_labels(url: str) -> list[str]:
    host = urlparse(url).netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    pieces = [piece for piece in host.split(".") if piece]
    labels = [host, *pieces]
    if len(pieces) >= 2:
        labels.append(".".join(pieces[-2:]))
    return labels


def citation_label_url(
    label: str,
    evidence: list[dict[str, Any]],
    allowed_urls: set[str],
) -> str | None:
    label_key = _canonical_label(label)
    if not label_key:
        return None

    for item in evidence:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or url not in allowed_urls:
            continue

        candidates = [
            str(item.get("title") or ""),
            str(item.get("source") or ""),
            url,
            *_domain_labels(url),
        ]
        for candidate in candidates:
            candidate_key = _canonical_label(candidate)
            if not candidate_key or len(candidate_key) < 3:
                continue
            if label_key == candidate_key or label_key in candidate_key or candidate_key in label_key:
                return url

    return None


# ---------------------------------------------------------------------------
# Per-section operations


def strip_disallowed_images(section: str, allowed_urls: set[str]) -> tuple[str, list[str]]:
    """Remove `![alt](url)` whose url is not whitelisted.

    Returns (cleaned_text, stripped_urls). Stripped images are replaced with
    empty string — they carry no semantic content we want to preserve.
    """
    spans = _iter_markdown_spans(section, image=True)
    if not spans:
        return section, []

    stripped: list[str] = []
    parts: list[str] = []
    cursor = 0

    for start, end, _alt, url in spans:
        parts.append(section[cursor:start])
        if url in allowed_urls:
            parts.append(section[start:end])
        else:
            stripped.append(url)
        cursor = end

    parts.append(section[cursor:])
    return "".join(parts), stripped


def strip_disallowed_links(section: str, allowed_urls: set[str]) -> tuple[str, list[str]]:
    spans = _iter_markdown_spans(section, image=False)
    if not spans:
        return section, []

    stripped: list[str] = []
    parts: list[str] = []
    cursor = 0

    for start, end, anchor, url in spans:
        parts.append(section[cursor:start])
        if url in allowed_urls:
            parts.append(section[start:end])
        else:
            stripped.append(url)
            parts.append(anchor)
        cursor = end

    parts.append(section[cursor:])
    return "".join(parts), stripped


def unwrap_bracketed_markdown_links(section: str, allowed_urls: set[str]) -> str:
    parts: list[str] = []
    cursor = 0

    while cursor < len(section):
        start = section.find(_BRACKET_OPEN, cursor)
        if start == -1:
            parts.append(section[cursor:])
            break

        end = section.find(_BRACKET_CLOSE, start + len(_BRACKET_OPEN))
        if end == -1:
            parts.append(section[cursor:])
            break

        inner = section[start + len(_BRACKET_OPEN):end].strip()
        spans = _iter_markdown_spans(inner, image=False)
        if len(spans) == 1 and spans[0][0] == 0 and spans[0][1] == len(inner):
            _span_start, _span_end, _anchor, url = spans[0]
            canonical = canonical_allowed_url(url, allowed_urls)
            if canonical is not None:
                parts.append(section[cursor:start])
                parts.append(inner.replace(url, canonical, 1))
                cursor = end + len(_BRACKET_CLOSE)
                continue

        parts.append(section[cursor:end + len(_BRACKET_CLOSE)])
        cursor = end + len(_BRACKET_CLOSE)

    return "".join(parts)


def normalize_source_citations(
    section: str,
    evidence: list[dict[str, Any]],
    allowed_urls: set[str],
) -> str:
    def replace_nested(match: re.Match[str]) -> str:
        url = canonical_allowed_url(match.group("url"), allowed_urls)
        if url is None:
            return match.group(0)
        anchor = match.group("anchor").strip() or "source"
        return f"[{anchor}]({url})"

    def replace_bracketed(match: re.Match[str]) -> str:
        url = canonical_allowed_url(match.group("url"), allowed_urls)
        if url is None:
            return match.group(0)
        return f" [source]({url})"

    def replace_label(match: re.Match[str]) -> str:
        label = match.group("label").strip()
        if not label:
            return ""
        if extract_links(label):
            return match.group(0)
        url = citation_label_url(label, evidence, allowed_urls)
        if url is None:
            return ""
        return f" [source]({url})"

    normalized = _NESTED_SOURCE_LINK_RE.sub(replace_nested, section)
    normalized = unwrap_bracketed_markdown_links(normalized, allowed_urls)
    normalized = _BRACKETED_URL_RE.sub(replace_bracketed, normalized)
    normalized = _BRACKETED_LABEL_RE.sub(replace_label, normalized)
    markdown_spans = [
        *_iter_markdown_spans(normalized, image=False),
        *_iter_markdown_spans(normalized, image=True),
    ]

    parts: list[str] = []
    cursor = 0
    for match in _RAW_URL_RE.finditer(normalized):
        if _inside_span(match.start(), markdown_spans):
            continue

        url = canonical_allowed_url(match.group(0), allowed_urls)
        if url is None:
            continue

        parts.append(normalized[cursor:match.start()])
        parts.append(f"[source]({url})")
        cursor = match.end()

    if not parts:
        return normalized

    parts.append(normalized[cursor:])
    return "".join(parts)


def strip_reference_definitions(section: str) -> str:
    lines = [
        line
        for line in section.splitlines()
        if _REFERENCE_DEFINITION_RE.match(line) is None
    ]
    return "\n".join(lines)


def has_whitelisted_link(section: str, allowed_urls: set[str]) -> bool:
    return any(url in allowed_urls for _, url in extract_links(section))


def append_source_links(
    section: str,
    evidence: list[dict[str, Any]],
    allowed_urls: set[str],
) -> str:
    urls = [
        item.get("url")
        for item in evidence
        if isinstance(item, dict) and item.get("url") in allowed_urls
    ]
    if not urls or has_whitelisted_link(section, allowed_urls):
        return section

    lines = section.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index].rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        suffix = f" [source]({urls[0]})"
        if line.endswith((".", "!", "?")):
            lines[index] = f"{line}{suffix}."
        else:
            lines[index] = f"{line}.{suffix}"
        return "\n".join(lines)

    return f"{section}\n\n[source]({urls[0]})"


def deterministic_repair_section(
    section: str,
    task: dict[str, Any],
    evidence: list[dict[str, Any]],
    allowed_urls: set[str],
) -> tuple[str, list[str]]:
    title = str(task.get("title") or "")
    repaired = sanitize_section_markdown(section, title)
    repaired = normalize_source_citations(repaired, evidence, allowed_urls)
    repaired = strip_reference_definitions(repaired)
    repaired, stripped_images = strip_disallowed_images(repaired, allowed_urls)
    repaired, stripped_links = strip_disallowed_links(repaired, allowed_urls)
    repaired = re.sub(r"[ \t]{2,}(?=\[[^\]]+\]\(https?://)", " ", repaired)
    repaired = re.sub(r"\s+([.,;:!?])", r"\1", repaired)

    if bool(task.get("requires_citations")):
        repaired = append_source_links(repaired, evidence, allowed_urls)

    warnings: list[str] = []
    if stripped_images:
        warnings.append(f"stripped images: {stripped_images}")
    if stripped_links:
        warnings.append(f"stripped links: {stripped_links}")

    return repaired, warnings


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

    markdown_spans = [
        *_iter_markdown_spans(section, image=False),
        *_iter_markdown_spans(section, image=True),
    ]
    for match in _RAW_URL_RE.finditer(section):
        if _inside_span(match.start(), markdown_spans):
            continue
        raw_url = match.group(0)
        if canonical_allowed_url(raw_url, allowed_urls) is None:
            issues.append(f"off-whitelist raw URL {raw_url}")
        else:
            issues.append(f"raw citation URL should be a Markdown link: {raw_url}")

    if _BRACKETED_LABEL_RE.search(section):
        issues.append("bracketed citation labels should be Markdown links")

    # 2. Required-citation coverage
    if requires_citations:
        if not has_whitelisted_link(section, allowed_urls):
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
    llm = with_role_fallback(
        get_llm(role="citation_repair", temperature=0.2),
        get_llm(role="fallback", temperature=0.2),
    )
    compact_evidence = compact_evidence_for_prompt(evidence)
    prompt = f"""
{wrap_untrusted("section", section)}

{wrap_untrusted("task", str(task))}

{wrap_untrusted("evidence", str(compact_evidence))}

Issues to fix:
- """ + "\n- ".join(issues) + """

Rewrite the section above to address every issue.
""".strip()

    response = await asyncio.wait_for(
        llm.ainvoke(
            [
                SystemMessage(content=CITATION_REPAIR_SYSTEM),
                HumanMessage(content=prompt),
            ]
        ),
        timeout=settings.llm_timeout_seconds,
    )
    content = response.content
    if isinstance(content, list):
        text = "\n".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part)
            for part in content
        )
    else:
        text = str(content)

    return sanitize_section_markdown(text, str(task.get("title") or ""))


# ---------------------------------------------------------------------------
# Final-assembly helpers


def rebuild_final(blog_title: str, sections: list[tuple[int, str]]) -> str:
    ordered = [body for _, body in sorted(sections, key=lambda item: item[0])]
    body = "\n\n".join(s.strip() for s in ordered if s.strip())
    return f"# {clean_title(blog_title)}\n\n{body}".strip()


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

        cleaned, deterministic_warnings = deterministic_repair_section(
            body,
            task,
            evidence,
            allowed_urls,
        )
        for warning in deterministic_warnings:
            log(f"task={task_id} {warning}")

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
            fallback, fallback_warnings = deterministic_repair_section(
                cleaned,
                task,
                evidence,
                allowed_urls,
            )
            remaining = section_violations(fallback, requires_citations, allowed_urls)
            if remaining:
                new_warnings.append(
                    f"citation_guard task={task_id} repair failed: {type(exc).__name__}"
                )
                unresolved_per_section[task_id] = remaining
            for warning in fallback_warnings:
                log(f"task={task_id} fallback {warning}")
            new_sections.append((task_id, fallback))
            continue

        repaired, repair_warnings = deterministic_repair_section(
            repaired,
            task,
            evidence,
            allowed_urls,
        )
        for warning in repair_warnings:
            log(f"task={task_id} post-repair {warning}")

        # Re-check after repair
        remaining = section_violations(repaired, requires_citations, allowed_urls)
        if remaining:
            fallback, fallback_warnings = deterministic_repair_section(
                repaired,
                task,
                evidence,
                allowed_urls,
            )
            fallback_remaining = section_violations(
                fallback,
                requires_citations,
                allowed_urls,
            )
            for warning in fallback_warnings:
                log(f"task={task_id} fallback {warning}")
            if not fallback_remaining:
                log(f"task={task_id} deterministic fallback succeeded")
                new_sections.append((task_id, fallback))
                continue

            remaining = fallback_remaining
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
