from langgraph.graph import StateGraph, END

from app.agent.graph_state import AgentState
from app.agent.nodes.classify import classify_node
from app.agent.nodes.call_tools import call_tools_node
from app.agent.nodes.generate import generate_node
from app.agent.nodes.validate import validate_node
from app.agent.nodes.respond import respond_node
from app.agent.edges import route_after_classify


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("classify", classify_node)
    g.add_node("call_tools", call_tools_node)
    g.add_node("generate", generate_node)
    g.add_node("validate", validate_node)
    g.add_node("respond", respond_node)

    g.set_entry_point("classify")

    # classify → clarify/oos → respond | answer → call_tools
    g.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "out_of_scope": "respond",
            "respond": "respond",
            "call_tools": "call_tools",
        },
    )

    # call_tools → generate (always, single LLM call)
    g.add_edge("call_tools", "generate")

    # generate → validate
    g.add_edge("generate", "validate")

    # validate → respond (always — conditional edge was redundant, route_after_validate always returned "respond")
    g.add_edge("validate", "respond")

    g.add_edge("respond", END)

    return g


_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph().compile()
    return _compiled
