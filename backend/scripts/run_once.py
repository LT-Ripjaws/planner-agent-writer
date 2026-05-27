import argparse
import asyncio

from backend.app.agents.graph import build_graph
from backend.app.agents.state import State


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

    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    topic = " ".join(args.topic)
    state: State = {
        "topic": topic,
        "audience": args.audience,
        "tone": args.tone,
        "blog_kind": args.blog_kind,
        "research_mode": args.research_mode,
    }

    graph = build_graph()
    final_state = await graph.ainvoke(state)
    print(final_state.get("final", ""))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
