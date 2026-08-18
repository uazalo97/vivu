from app.agent.graph_state import AgentState


def route_after_classify(state: AgentState) -> str:
    """Route after classify_node. Trust classify_node's decision."""
    decision = state.get("decision", "answer")
    if decision in ("out_of_scope", "clarify", "refuse", "greeting"):
        return "respond"
    return "call_tools"


def route_after_validate(state: AgentState) -> str:
    return "respond"
