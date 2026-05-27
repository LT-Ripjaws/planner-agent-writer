import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.prompts import WRITER_SYSTEM
from backend.app.agents.state import Plan, State, Task
from backend.app.services.llm import get_llm


def require_task(state: State) -> Task:
    task = state.get("task")
    if task is None:
        raise ValueError("State is missing required field: task")

    return Task.model_validate(task)


def require_plan(state: State) -> Plan:
    plan = state.get("plan")
    if plan is None:
        raise ValueError("State is missing required field: plan")

    return Plan.model_validate(plan)


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(str(item))

        return "\n".join(parts)

    return str(content)


def build_writer_prompt(state: State, task: Task, plan: Plan) -> str:
    evidence = state.get("evidence", [])
    return f"""
Blog title: {plan.blog_title}
Topic: {state.get("topic", "")}
Audience: {plan.audience}
Tone: {plan.tone}
Mode: {state.get("mode", "closed_book")}
As of date: {state.get("as_of", "unknown")}

Task:
{task.model_dump_json(indent=2)}

Available evidence:
{json.dumps(evidence[:16], indent=2)}

Write only this section.
""".strip()


async def writer_node(state: State) -> State:
    task = require_task(state)
    plan = require_plan(state)
    llm = get_llm(temperature=0.7)

    response = await llm.ainvoke(
        [
            SystemMessage(content=WRITER_SYSTEM),
            HumanMessage(content=build_writer_prompt(state, task, plan)),
        ]
    )

    markdown = content_to_text(response.content).strip()
    return {
        "sections": [(task.id, markdown)],
    }
