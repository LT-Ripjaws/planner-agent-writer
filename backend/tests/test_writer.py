from __future__ import annotations

import asyncio
import time
from typing import Any

from backend.app.agents.nodes import writer
from backend.app.agents.nodes.writer import invoke_writer_with_retry, writer_node
from backend.tests.fakes import make_plan


class FlakyWriterLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, _messages: Any) -> Any:
        self.calls += 1
        if self.calls == 1:
            raise ValueError({"message": "Provider returned error", "code": 504})
        return type("Response", (), {"content": "## Section 1\n\nRecovered draft."})()


async def test_writer_retries_transient_provider_errors(monkeypatch):
    fake = FlakyWriterLLM()
    monkeypatch.setattr(writer, "get_llm", lambda *a, **k: fake)

    plan = make_plan(n_tasks=5)
    task = plan.tasks[0]
    state = {
        "topic": "AI hallucination explained",
        "plan": plan.model_dump(),
        "task": task.model_dump(),
        "writer_timeout_seconds": 5,
    }

    result = await writer_node(state)

    assert fake.calls == 2
    assert result["sections"] == [(1, "## Section 1\n\nRecovered draft.")]
    assert "warnings" not in result


async def test_writer_retry_respects_total_timeout_budget():
    fake = FlakyWriterLLM()
    task = make_plan(n_tasks=5).tasks[0]

    try:
        await invoke_writer_with_retry(
            fake,
            [],
            task=task,
            started=time.monotonic() - 10,
            timeout_seconds=1,
        )
    except asyncio.TimeoutError:
        pass
    else:
        raise AssertionError("expected total writer budget to be exhausted")

    assert fake.calls == 0
