import logging

from langgraph.graph import StateGraph, END

from app.agent.graph_state import AgentState
from app.agent.nodes.classify import classify_node
from app.agent.nodes.call_tools import call_tools_node
from app.agent.nodes.generate import generate_node
from app.agent.nodes.validate import validate_node
from app.agent.nodes.respond import respond_node
from app.agent.edges import route_after_classify

# ── Patch xxhash pure-fallback bug: xxh3_128_hexdigest returns int not hex str ──
# langgraph 0.6+ uses _xxhash_str which expects hex string; pure fallback returns int -> TypeError: 'int' object is not subscriptable
try:
    import xxhash as _xxhash_mod  # type: ignore
    import langgraph.pregel._algo as _algo_mod  # type: ignore

    _orig = getattr(_xxhash_mod, "xxh3_128_hexdigest", None)
    if _orig is not None:
        # quick probe: does it return int?
        try:
            _probe = _orig(b"test")
            if isinstance(_probe, int):
                def _fixed_xxh3_128_hexdigest(data: bytes = b"", seed: int = 0) -> str:  # type: ignore[no-redef]
                    v = _orig(data, seed) if seed else _orig(data)
                    # 128-bit -> 32 hex chars, pad
                    return format(int(v), "032x")

                _xxhash_mod.xxh3_128_hexdigest = _fixed_xxh3_128_hexdigest  # type: ignore[attr-defined]
                # also patch already-imported reference in _algo
                if hasattr(_algo_mod, "xxh3_128_hexdigest"):
                    _algo_mod.xxh3_128_hexdigest = _fixed_xxh3_128_hexdigest  # type: ignore[attr-defined]
                # patch _xxhash_str to be safe even if xxhash still returns int
                _orig_xxhash_str = getattr(_algo_mod, "_xxhash_str", None)
                if _orig_xxhash_str is not None:
                    def _patched_xxhash_str(namespace: bytes, *parts):  # type: ignore[no-redef]
                        from xxhash import xxh3_128_hexdigest as _h
                        hx = _h(namespace + b"".join(p.encode() if isinstance(p, str) else p if isinstance(p, (bytes, bytearray)) else str(p).encode() for p in parts))
                        if isinstance(hx, int):
                            hx = format(hx, "032x")
                        return f"{hx[:8]}-{hx[8:12]}-{hx[12:16]}-{hx[16:20]}-{hx[20:32]}"

                    _algo_mod._xxhash_str = _patched_xxhash_str  # type: ignore[attr-defined]
        except Exception:
            pass
except Exception:
    pass

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
