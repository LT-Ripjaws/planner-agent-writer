from __future__ import annotations

import re
from typing import Any

_HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s*(?P<title>.*?)\s*$")
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_LEADING_TITLE_JUNK_RE = re.compile(r"^[\s:：\-–—|/\\]+")


def clean_title(title: str | None, fallback: str = "Untitled") -> str:
    cleaned = re.sub(r"\s+", " ", (title or "").strip())
    cleaned = _LEADING_TITLE_JUNK_RE.sub("", cleaned).strip()
    return cleaned or fallback


def clean_markdown_headings(markdown: str) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            lines.append(f"{match.group('level')} {clean_title(match.group('title'))}")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _heading_key(value: str) -> str:
    value = clean_title(value)
    value = re.sub(r"[^\w\s]+", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip().casefold()


def trim_to_section_heading(markdown: str, expected_title: str | None = None) -> str:
    text = _THINK_BLOCK_RE.sub("", markdown).strip()
    if not text:
        return text

    lines = text.splitlines()
    expected_key = _heading_key(expected_title or "")

    first_h2_index: int | None = None
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if not match or match.group("level") != "##":
            continue

        if first_h2_index is None:
            first_h2_index = index

        if expected_key and _heading_key(match.group("title")) == expected_key:
            return "\n".join(lines[index:]).strip()

    if first_h2_index is not None:
        return "\n".join(lines[first_h2_index:]).strip()

    return text


def sanitize_section_markdown(markdown: str, expected_title: str | None = None) -> str:
    text = clean_markdown_headings(trim_to_section_heading(markdown, expected_title))
    if not text:
        return f"## {clean_title(expected_title, fallback='Section')}"

    lines = text.splitlines()
    first_nonempty = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_nonempty is None:
        return f"## {clean_title(expected_title, fallback='Section')}"

    match = _HEADING_RE.match(lines[first_nonempty])
    if match and match.group("level") == "##":
        lines[first_nonempty] = f"## {clean_title(match.group('title'), expected_title or 'Section')}"
        return "\n".join(lines).strip()

    heading = f"## {clean_title(expected_title, fallback='Section')}"
    return f"{heading}\n\n{text}".strip()


def compact_evidence_for_prompt(
    evidence: list[dict[str, Any]],
    *,
    limit: int = 10,
    snippet_chars: int = 320,
) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in evidence[:limit]:
        if not isinstance(item, dict):
            continue

        url = item.get("url")
        if not isinstance(url, str) or not url:
            continue

        snippet = str(item.get("snippet") or "")
        if len(snippet) > snippet_chars:
            snippet = f"{snippet[:snippet_chars].rstrip()}..."

        compacted.append(
            {
                "title": str(item.get("title") or "Untitled"),
                "url": url,
                "source": item.get("source"),
                "published_at": item.get("published_at"),
                "snippet": snippet,
            }
        )

    return compacted
