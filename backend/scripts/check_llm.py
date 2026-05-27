import argparse
import asyncio
import sys
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.services.llm import get_llm, structured


class ProviderCheck(BaseModel):
    status: Literal["ok"]


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "\n".join(str(item) for item in content)

    return str(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the configured LLM provider.")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Maximum time to wait for the provider response.",
    )

    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    print(f"base_url: {settings.llm_base_url}", file=sys.stderr, flush=True)
    print(f"model: {settings.llm_model}", file=sys.stderr, flush=True)
    print("sending one short provider request...", file=sys.stderr, flush=True)

    llm = get_llm(temperature=0)
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content="You are a concise assistant."),
                    HumanMessage(content="Reply with exactly: provider ok"),
                ]
            ),
            timeout=args.timeout_seconds,
        )
    except asyncio.TimeoutError:
        print(f"provider timed out after {args.timeout_seconds} seconds", file=sys.stderr)
        raise SystemExit(124) from None

    print(f"plain: {content_to_text(response.content).strip()}")
    print("sending one structured-output request...", file=sys.stderr, flush=True)

    chain = structured(llm, ProviderCheck)
    try:
        structured_response = await asyncio.wait_for(
            chain.ainvoke(
                [
                    SystemMessage(content="You are a health check service."),
                    HumanMessage(content="Return status ok."),
                ]
            ),
            timeout=args.timeout_seconds,
        )
    except asyncio.TimeoutError:
        print(
            f"structured output timed out after {args.timeout_seconds} seconds",
            file=sys.stderr,
        )
        raise SystemExit(124) from None

    print(f"structured: {ProviderCheck.model_validate(structured_response).status}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
