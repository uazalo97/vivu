import logging
import time

from app.agent.context_builder import build_structured_context
from app.agent.graph_state import AgentState
from app.agent.llm import OUTPUT_MAX_TOKENS, INPUT_MAX_TOKENS, stream_chat_with_fallback, get_llm, truncate_messages
from app.agent.prompts import SYNTHESIZE_PROMPT

logger = logging.getLogger("bds.graph.generate")


async def generate_node(state: AgentState) -> dict:
    tool_results = state.get("tool_results", [])

    if not tool_results:
        return {"final_response": "", "decision": "refuse", "reason_code": "insufficient_evidence"}

    # Build context từ tool results (Vietnamese labels cho spec keys)
    query = state.get("query", "")
    context = build_structured_context(tool_results, query=query)

    # Build history-aware query cho multi-turn (chỉ lấy 4 turns gần nhất)
    history = state.get("history", [])
    if history:
        history_context = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
        full_query = f"Lịch sử hội thoại:\n{history_context}\n\nCâu hỏi hiện tại: {query}"
    else:
        full_query = query

    # Lấy system prompt từ state (đã được call_tools_node set sẵn)
    # Không gọi lại get_system_prompt() để tránh double PG round-trip
    system_prompt = state["messages"][0]["content"] if state.get("messages") else ""
    if not system_prompt:
        logger.warning("generate_node: messages empty — using minimal inline fallback prompt")
        system_prompt = "Bạn là trợ lý tư vấn xe VinFast. Chỉ dùng thông tin trong context được cung cấp."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": SYNTHESIZE_PROMPT.format(context=context, query=full_query)},
    ]
    # Fix #5: Truncate để tránh 400 error khi context vượt context limit (fleet query)
    messages = truncate_messages(messages, INPUT_MAX_TOKENS)

    llm = get_llm()  # Fix #2: dùng shared singleton từ llm.py, không tạo client riêng
    t_generate_start = time.time()

    final_response = state.get("final_response", "")
    try:
        new_response, _, _ = await stream_chat_with_fallback(llm, messages, max_tokens=OUTPUT_MAX_TOKENS)
        if new_response:
            final_response = new_response
    except Exception as e:
        logger.error("generate_node LLM error (all models): %s", e)
        return {
            "final_response": final_response,
            "t_generate_start": t_generate_start,
            "t_generate_end": time.time(),
        }

    return {
        "final_response": final_response,
        "t_generate_start": t_generate_start,
        "t_generate_end": time.time(),
    }
