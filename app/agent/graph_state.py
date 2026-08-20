from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    query: str
    history: list[dict]
    current_context: dict[str, Any]
    cache_hit: bool
    cache_type: str
    messages: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    final_response: str

    decision: str
    reason_code: str
    response_text: str

    entities: dict[str, Any]
    specificity: str
    category: str | None
    allowed_tools: set[str] | None
    model_codes: list[str]  # explicit models for cross-model follow-up (multi-turn comparison)

    assessment: str
    citations: list[dict[str, Any]]
    grounding_ok: bool

    iteration: int
    t0: float
    t_retrieve_start: float
    t_retrieve_end: float
    t_generate_start: float

    result: Any
