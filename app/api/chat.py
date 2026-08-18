import json
import time
import uuid
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.agent.agent_loop import AgentLoop
from app.agent.decision import log_store
from app.config import settings
from app.core.telemetry import log_metric_background, record_metric

router = APIRouter()

_agent = None


def get_agent() -> AgentLoop:
    global _agent
    if _agent is None:
        _agent = AgentLoop()
    return _agent


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    history: list[dict] = []


class ChatResponse(BaseModel):
    response: str
    sources: list[dict] = []
    needs_clarification: bool = False
    classify: dict = {}
    decision: str = "answer"
    decision_log: dict = {}


def _estimate_tokens(text: str) -> int:
    """Ước lượng số tokens cho tiếng Việt và code nếu không có token count chính xác."""
    if not text:
        return 0
    words = text.split()
    return max(1, int(len(words) * 1.4))


@router.post("/api/chat")
async def chat(request: ChatRequest):
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    t0 = time.time()
    agent = get_agent()
    result = await agent.run(request.message, request.history)
    total_latency_ms = int((time.time() - t0) * 1000)

    # Telemetry recording
    dlog = result.decision_log or {}
    intent = dlog.get("topic") or dlog.get("detected_topic") or result.classify_result.get("assessment") or "general"
    tools_used = [t.get("tool") for t in dlog.get("retrieved_chunks", []) if isinstance(t, dict) and t.get("tool")]

    prompt_tok = _estimate_tokens(request.message) + sum(_estimate_tokens(h.get("content", "")) for h in request.history)
    comp_tok = _estimate_tokens(result.response)

    log_metric_background(
        record_metric(
            request_id=req_id,
            session_id=request.session_id,
            query_text=request.message,
            intent=intent,
            decision=result.decision,
            model_used=settings.llm_model,
            prompt_version=getattr(settings, "app_version", "v1.0.0"),
            prompt_tokens=prompt_tok,
            completion_tokens=comp_tok,
            ttft_ms=int(total_latency_ms * 0.4),
            total_latency_ms=total_latency_ms,
            cache_hit=False,
            cache_type="none",
            tools_used=tools_used,
            status_code=200,
        )
    )

    return ChatResponse(
        response=result.response,
        sources=result.sources,
        needs_clarification=result.needs_clarification,
        classify=result.classify_result,
        decision=result.decision,
        decision_log=result.decision_log,
    )


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    t0 = time.time()
    agent = get_agent()

    async def generate():
        ttft_ms = 0
        first_token = True
        accumulated_text = []
        decision = "answer"
        intent = "general"
        tools_used = []

        try:
            async for event in agent.run_stream(request.message, request.history):
                etype = event.get("type")
                if etype == "token" and first_token:
                    ttft_ms = int((time.time() - t0) * 1000)
                    first_token = False

                if etype == "token":
                    accumulated_text.append(event.get("content", ""))
                elif etype == "answer" or etype == "clarify":
                    accumulated_text.append(event.get("content", ""))
                elif etype == "decision":
                    decision = event.get("content", "answer")
                elif etype == "tool_call":
                    tc = event.get("content", {})
                    if tc.get("tool"):
                        tools_used.append(tc.get("tool"))

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            total_latency_ms = int((time.time() - t0) * 1000)
            if ttft_ms == 0:
                ttft_ms = total_latency_ms

            full_resp = "".join(accumulated_text)
            prompt_tok = _estimate_tokens(request.message) + sum(_estimate_tokens(h.get("content", "")) for h in request.history)
            comp_tok = _estimate_tokens(full_resp)

            log_metric_background(
                record_metric(
                    request_id=req_id,
                    session_id=request.session_id,
                    query_text=request.message,
                    intent=intent,
                    decision=decision,
                    model_used=settings.llm_model,
                    prompt_version=getattr(settings, "app_version", "v1.0.0"),
                    prompt_tokens=prompt_tok,
                    completion_tokens=comp_tok,
                    ttft_ms=ttft_ms,
                    total_latency_ms=total_latency_ms,
                    cache_hit=False,
                    cache_type="none",
                    tools_used=tools_used,
                    status_code=200,
                )
            )

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/api/logs")
async def get_logs(run_id: str = None):
    if run_id:
        logs = log_store.get_by_run(run_id)
    else:
        logs = log_store.get_all()
    return JSONResponse(content={"count": len(logs), "run_id": run_id, "logs": logs})


@router.get("/api/logs/export")
async def export_logs(run_id: str = None):
    if run_id:
        logs = log_store.get_by_run(run_id)
    else:
        logs = log_store.get_all()
    lines = [json.dumps(l, ensure_ascii=False) for l in logs]
    content = "\n".join(lines) + "\n" if lines else ""
    fname = "logs_" + (run_id or "all") + ".jsonl"
    return StreamingResponse(
        content=iter([content]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=" + fname},
    )
