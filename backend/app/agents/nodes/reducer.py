from backend.app.agents.markdown_sanitize import clean_title, clean_markdown_headings
from backend.app.agents.state import Plan, State


def require_plan(state: State) -> Plan:
    plan = state.get("plan")
    if plan is None:
        raise ValueError("State is missing required field: plan")

    return Plan.model_validate(plan)


def reducer_node(state: State) -> State:
    plan = require_plan(state)
    sections = state.get("sections", [])
    ordered_sections = [
        clean_markdown_headings(section)
        for _, section in sorted(sections, key=lambda item: item[0])
    ]
    body = "\n\n".join(section.strip() for section in ordered_sections if section.strip())
    final = f"# {clean_title(plan.blog_title)}\n\n{body}".strip()

    return {
        "merged_md": final,
        "final": final,
    }
