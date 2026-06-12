import asyncio
from datetime import date, datetime, timedelta

from backend.app.agents.state import EvidenceItem, State
from backend.app.core.config import settings
from backend.app.services.search import dedupe_evidence, tavily_search_async


class ResearchEmpty(RuntimeError):
    pass


def evidence_to_dicts(items: list[EvidenceItem]) -> list[dict]:
    return [item.model_dump() for item in items]


def parse_date(value: str | None) -> date | None:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def filter_by_recency(
    items: list[EvidenceItem],
    *,
    as_of: str | None,
    recency_days: int | None,
) -> list[EvidenceItem]:
    if not as_of or not recency_days:
        return items

    as_of_date = parse_date(as_of)
    if as_of_date is None:
        return items

    cutoff = as_of_date - timedelta(days=recency_days)
    filtered: list[EvidenceItem] = []

    for item in items:
        published_at = parse_date(item.published_at)
        if published_at is None or published_at >= cutoff:
            filtered.append(item)

    return filtered


async def research_node(state: State) -> State:
    if not state.get("needs_research", False):
        return {"evidence": []}

    queries = state.get("queries", [])
    if not queries:
        if state.get("research_mode") == "required":
            raise ResearchEmpty("Research was required, but no search queries were provided.")

        return {"evidence": []}

    # Fail fast with the real cause when the search backend isn't configured,
    # instead of letting every per-query call raise and surfacing a misleading
    # "no usable results" downstream.
    if not settings.tavily_api_key:
        message = (
            "TAVILY_API_KEY is not configured, so research mode cannot run. "
            "Set it in the backend .env, or submit with research mode 'off'."
        )
        if state.get("research_mode") == "required":
            raise ResearchEmpty(message)
        return {"evidence": [], "warnings": [message]}

    max_results = state.get("max_results_per_query", 5)

    async def search_with_retry(query: str) -> list[EvidenceItem]:
        last_exc: BaseException | None = None
        for attempt in range(2):
            try:
                items = await tavily_search_async(query, max_results=max_results)
            except BaseException as exc:  # noqa: BLE001
                last_exc = exc
                if attempt == 1:
                    raise
                await asyncio.sleep(1)
                continue

            if items or attempt == 1:
                return items
            await asyncio.sleep(1)

        if last_exc is not None:
            raise last_exc
        return []

    results_by_query = await asyncio.gather(
        *[search_with_retry(query) for query in queries],
        return_exceptions=True,
    )

    evidence: list[EvidenceItem] = []
    warnings: list[str] = []

    for query, result in zip(queries, results_by_query):
        if isinstance(result, BaseException):
            warnings.append(f"Search failed for query: {query}")
            continue

        evidence.extend(result)

    evidence = dedupe_evidence(evidence)
    recent = filter_by_recency(
        evidence,
        as_of=state.get("as_of"),
        recency_days=state.get("recency_days"),
    )
    # Recency is a ranking preference, not a hard gate. If the filter would
    # discard every hit we actually found — common for evergreen topics in
    # `hybrid` (45d) or `open_book` (7d) mode, where the window is tight — keep
    # the older sources instead of failing the whole run. Better to cite a
    # slightly dated source than to error out with "no evidence found".
    if evidence and not recent:
        warnings.append(
            "all evidence fell outside the "
            f"{state.get('recency_days')}-day recency window; keeping older sources"
        )
    else:
        evidence = recent

    evidence = sorted(evidence, key=lambda item: item.score or 0, reverse=True)[:16]

    if state.get("research_mode") == "required" and not evidence:
        raise ResearchEmpty("Research was required, but Tavily returned no usable results.")

    return {
        "evidence": evidence_to_dicts(evidence),
        "warnings": warnings,
    }
