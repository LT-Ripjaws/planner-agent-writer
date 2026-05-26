from functools import lru_cache
from urllib.parse import urlparse

from tavily import AsyncTavilyClient

from backend.app.agents.state import EvidenceItem
from backend.app.core.config import settings


def require_tavily_api_key() -> str:
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is required to use the search service.")

    return settings.tavily_api_key


@lru_cache
def get_tavily_client() -> AsyncTavilyClient:
    return AsyncTavilyClient(api_key=require_tavily_api_key())


def source_from_url(url: str) -> str | None:
    hostname = urlparse(url).hostname
    if hostname is None:
        return None

    return hostname.removeprefix("www.")


def normalize_hit(hit: dict) -> EvidenceItem | None:
    url = hit.get("url")
    title = hit.get("title")
    snippet = hit.get("content") or hit.get("snippet") or hit.get("raw_content")

    if not url or not title or not snippet:
        return None

    return EvidenceItem(
        title=title,
        url=url,
        published_at=hit.get("published_date") or hit.get("published_at"),
        snippet=snippet,
        source=source_from_url(url),
        score=hit.get("score"),
    )


def dedupe_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    by_url: dict[str, EvidenceItem] = {}

    for item in items:
        existing = by_url.get(item.url)
        if existing is None:
            by_url[item.url] = item
            continue

        existing_score = existing.score or 0
        item_score = item.score or 0

        if item_score > existing_score:
            by_url[item.url] = item

    return list(by_url.values())


async def tavily_search_async(query: str, max_results: int = 5) -> list[EvidenceItem]:
    client = get_tavily_client()

    response = await client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
        include_answer=False,
        include_raw_content=False,
    )

    raw_results = response.get("results", [])
    normalized = [
        item
        for hit in raw_results
        if (item := normalize_hit(hit)) is not None
    ]

    return dedupe_evidence(normalized)