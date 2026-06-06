import argparse
import asyncio
import sys
from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig

from backend.app.agents.graph import build_graph
from backend.app.agents.state import State
from backend.app.core.config import settings
from backend.app.workers.retry import finalize_warnings


def log(message: str) -> None:
    print(f"[run_once] {message}", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the blog-writing graph once.")
    parser.add_argument("topic", nargs="+", help="Blog topic to write about.")
    parser.add_argument("--audience", default=None)
    parser.add_argument(
        "--tone",
        default="neutral",
        choices=["neutral", "technical", "casual", "authoritative"],
    )
    parser.add_argument(
        "--blog-kind",
        default="auto",
        choices=[
            "auto",
            "explainer",
            "tutorial",
            "news_roundup",
            "comparison",
            "system_design",
        ],
    )
    parser.add_argument(
        "--research-mode",
        default="auto",
        choices=["auto", "required", "off"],
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=settings.run_fallback_timeout_seconds,
        help="Maximum time to wait for the full graph run.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=settings.writer_max_concurrency,
        help="Maximum concurrent LangGraph tasks. Provider-dependent; "
        "bump higher only on providers that don't stall under load.",
    )
    parser.add_argument(
        "--max-sections",
        type=int,
        default=None,
        help="Limit writer fanout for quick provider smoke tests.",
    )
    parser.add_argument(
        "--writer-timeout-seconds",
        type=int,
        default=settings.writer_timeout_seconds,
        help="Maximum time to wait for each writer section.",
    )

    return parser.parse_args()


def describe_progress(snapshot: Mapping[str, Any], seen: set[str]) -> None:
    if "mode" in snapshot and "router" not in seen:
        seen.add("router")
        log(
            "router complete: "
            f"mode={snapshot.get('mode')}, "
            f"needs_research={snapshot.get('needs_research')}"
        )

    if "evidence" in snapshot and snapshot.get("needs_research") and "research" not in seen:
        seen.add("research")
        log(f"research complete: {len(snapshot.get('evidence', []))} evidence items")

    if "plan" in snapshot and "planner" not in seen:
        seen.add("planner")
        plan = snapshot.get("plan") or {}
        tasks = plan.get("tasks", []) if isinstance(plan, dict) else []
        log(f"planner complete: {len(tasks)} sections planned")

    section_count = len(snapshot.get("sections", []))
    last_section_count = int(snapshot.get("_last_logged_section_count", 0))
    if section_count > last_section_count:
        log(f"writer progress: {section_count} sections completed")

    if "final" in snapshot and "reducer" not in seen:
        seen.add("reducer")
        log("reducer complete: final Markdown assembled")


async def run_graph_with_progress(
    state: State,
    *,
    max_concurrency: int,
) -> Mapping[str, Any]:
    graph = build_graph()
    final_state: Mapping[str, Any] = {}
    seen: set[str] = set()
    last_section_count = 0
    config: RunnableConfig = {"max_concurrency": max_concurrency}

    async for snapshot in graph.astream(
        state,
        config=config,
        stream_mode="values",
    ):
        final_state = snapshot
        section_count = len(snapshot.get("sections", []))
        describe_progress(
            {
                **snapshot,
                "_last_logged_section_count": last_section_count,
            },
            seen,
        )
        last_section_count = section_count

    return final_state


async def run() -> None:
    args = parse_args()
    topic = " ".join(args.topic)
    state: State = {
        "topic": topic,
        "audience": args.audience,
        "tone": args.tone,
        "blog_kind": args.blog_kind,
        "research_mode": args.research_mode,
        "writer_timeout_seconds": args.writer_timeout_seconds,
    }
    if args.max_sections is not None:
        state["max_sections"] = args.max_sections

    log("starting graph")
    log(f"max_concurrency={args.max_concurrency}")
    if args.max_sections is not None:
        log(f"max_sections={args.max_sections}")

    if args.research_mode == "off":
        log("research is disabled; first provider call will be the planner")

    try:
        final_state = await asyncio.wait_for(
            run_graph_with_progress(state, max_concurrency=args.max_concurrency),
            timeout=args.timeout_seconds,
        )
    except asyncio.TimeoutError:
        log(f"timed out after {args.timeout_seconds} seconds")
        log("try the provider health check: python -m backend.scripts.check_llm")
        raise SystemExit(124) from None

    final = str(final_state.get("final", "")).strip()
    if not final:
        log("graph finished without final Markdown")
        raise SystemExit(1)

    warnings = finalize_warnings(final_state)
    if warnings:
        log(f"completed with {len(warnings)} warning(s):")
        for warning in warnings:
            log(f"  - {warning}")

    print(final)


def main() -> None:
    # The final Markdown can contain non-cp1252 characters (e.g. the
    # non-breaking hyphen ‑ that reasoning models like to emit in titles).
    # Force UTF-8 so `print(final)` doesn't crash on the Windows console.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    asyncio.run(run())


if __name__ == "__main__":
    main()
