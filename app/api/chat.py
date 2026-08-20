import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.agent.agent_loop import AgentLoop
from app.agent.decision import log_store
from app.config import settings
from app.core.memory import (
    load_session,
    save_turn,
    update_current_context,
    save_user_fact,
    get_redis,
)
from app.core.telemetry import log_metric_background, record_metric

logger = logging.getLogger("bds.api")

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
    message_id: Optional[str] = None
    history: list[dict] = []


class ChatResponse(BaseModel):
    response: str
    sources: list[dict] = []
    needs_clarification: bool = False
    classify: dict = {}
    decision: str = "answer"
    decision_log: dict = {}
    session_id: Optional[str] = None


def _estimate_tokens(text: str) -> int:
    """Ước lượng số tokens cho tiếng Việt và code nếu không có token count chính xác."""
    if not text:
        return 0
    words = text.split()
    return max(1, int(len(words) * 1.4))


# ── Rate limit + Dedupe (fail-open: Redis down → pass-through) ────────────────

_RATE_LIMIT_MSG = "Bạn gửi hơi nhanh, chờ vài giây rồi thử lại."
_DEDUP_MSG = "Tin nhắn trùng lặp."


async def _rate_limit_check(session_id: str, ip: str) -> str | None:
    """Kiểm tra rate limit. Trả None nếu OK, trả error message nếu bị block."""
    if not getattr(settings, "rate_limit_enabled", True):
        return None
    r = get_redis()
    if not r:
        return None
    try:
        now = int(time.time())
        # Session: 10 msg / 10s
        s_key = f"rl:s:{session_id}:{now // 10}"
        s_count = await r.incr(s_key)
        if s_count == 1:
            await r.expire(s_key, 10)
        if s_count > 10:
            return _RATE_LIMIT_MSG
        # IP: 30 msg / 60s
        i_key = f"rl:ip:{ip}:{now // 60}"
        i_count = await r.incr(i_key)
        if i_count == 1:
            await r.expire(i_key, 60)
        if i_count > 30:
            return _RATE_LIMIT_MSG
    except Exception:
        pass  # fail-open
    return None


async def _dedup_check(session_id: str, message_id: str) -> bool:
    """True nếu request mới (OK), False nếu trùng lặp."""
    r = get_redis()
    if not r:
        return True
    try:
        key = f"dedup:{hashlib.sha1(f'{session_id}|{message_id}'.encode()).hexdigest()}"
        ok = await r.set(key, "1", nx=True, ex=3600)
        return ok is not None  # None = key đã tồn tại = trùng
    except Exception:
        return True  # fail-open


@router.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request):
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    t0 = time.time()
    session_id = request.session_id or str(uuid.uuid4())

    # Rate limit (fail-open)
    ip = http_request.client.host if http_request.client else "unknown"
    rl_msg = await _rate_limit_check(session_id, ip)
    if rl_msg:
        return JSONResponse(status_code=429, content={"error": rl_msg})

    # Dedupe (fail-open)
    if request.message_id:
        is_new = await _dedup_check(session_id, request.message_id)
        if not is_new:
            return JSONResponse(status_code=409, content={"error": _DEDUP_MSG})

    session = await load_session(session_id)
    history = session["history"] or request.history or []
    current_context = session["current_context"]

    agent = get_agent()
    result = await agent.run(request.message, history, current_context)
    total_latency_ms = int((time.time() - t0) * 1000)

    # Persist turn + context + long-term memory (fail-open)
    await save_turn(session_id, request.message, result.response)
    entities = (result.classify_result or {}).get("entities", {})
    model_code = entities.get("model_code")
    version = entities.get("version")
    topic = (result.decision_log or {}).get("detected_topic")
    await update_current_context(session_id, model_code=model_code, version=version, topic=topic)
    if model_code:
        await save_user_fact(session_id, "preferred_model", model_code)
    if version:
        await save_user_fact(session_id, "preferred_version", version)

    cache_hit = bool(getattr(result, "cache_hit", False))
    cache_type = getattr(result, "cache_type", "none") or "none"

    # Telemetry recording — dùng số liệu THẬT từ decision_log (bỏ ttft*0.4 giả)
    dlog = result.decision_log or {}
    intent = (
        dlog.get("topic") or dlog.get("detected_topic") or (result.classify_result or {}).get("assessment") or "general"
    )
    tools_used = [t.get("tool") for t in dlog.get("retrieved_chunks", []) if isinstance(t, dict) and t.get("tool")]
    prompt_tok = _estimate_tokens(request.message) + sum(_estimate_tokens(h.get("content", "")) for h in history)
    comp_tok = _estimate_tokens(result.response)
    latency_retrieval_ms = int(dlog.get("latency_retrieval_ms") or dlog.get("latency_ms") or 0)
    latency_generation_ms = int(dlog.get("latency_generation_ms") or 0)
    ttot_ms = int(dlog.get("latency_total_ms") or dlog.get("ttot_ms") or total_latency_ms)
    ttft_ms = int(dlog.get("ttft_ms") or 0)
    if ttft_ms == 0 and latency_retrieval_ms:
        ttft_ms = latency_retrieval_ms
    model_code = entities.get("model_code")
    model_version = entities.get("version")
    retrieval_status = "success" if dlog.get("retrieved_chunks") else "none"
    chunks_retrieved = len(dlog.get("retrieved_chunks") or dlog.get("chunks") or [])
    reasoning_tokens = int(dlog.get("reasoning_tokens") or 0)
    log_metric_background(
        record_metric(
            request_id=req_id,
            session_id=session_id,
            query_text=request.message,
            intent=intent,
            decision=result.decision,
            model_used=settings.llm_model,
            prompt_version=getattr(settings, "app_version", "v1.0.0"),
            prompt_tokens=prompt_tok,
            completion_tokens=comp_tok,
            ttft_ms=ttft_ms,
            ttot_ms=ttot_ms,
            total_latency_ms=total_latency_ms,
            latency_retrieval_ms=latency_retrieval_ms,
            latency_generation_ms=latency_generation_ms,
            cache_hit=cache_hit,
            cache_type=cache_type,
            tools_used=tools_used,
            status_code=200,
            model_code=model_code,
            model_version=model_version,
            retrieval_status=retrieval_status,
            chunks_retrieved=chunks_retrieved,
            reasoning_tokens=reasoning_tokens,
        )
    )

    return ChatResponse(
        response=result.response,
        sources=result.sources,
        needs_clarification=result.needs_clarification,
        classify=result.classify_result,
        decision=result.decision,
        decision_log=result.decision_log,
        session_id=session_id,
    )


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    t0 = time.time()
    session_id = request.session_id or str(uuid.uuid4())

    # Rate limit (fail-open)
    ip = http_request.client.host if http_request.client else "unknown"
    rl_msg = await _rate_limit_check(session_id, ip)
    if rl_msg:
        return JSONResponse(status_code=429, content={"error": rl_msg})

    # Dedupe (fail-open)
    if request.message_id:
        is_new = await _dedup_check(session_id, request.message_id)
        if not is_new:
            return JSONResponse(status_code=409, content={"error": _DEDUP_MSG})

    session = await load_session(session_id)
    history = session["history"] or request.history or []
    current_context = session["current_context"]
    agent = get_agent()

    async def generate():
        ttft_ms = 0
        first_token = True
        accumulated_text = []
        decision = "answer"
        intent = "general"
        tools_used = []
        cache_hit = False
        cache_type = "none"
        entities = {}
        category = ""

        yield f"data: {json.dumps({'type': 'session', 'content': session_id}, ensure_ascii=False)}\n\n"

        try:
            async for event in agent.run_stream(request.message, history, current_context):
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
                elif etype == "classify":
                    entities = event.get("content", {}).get("entities", {}) or {}
                    category = event.get("content", {}).get("category", "")
                    if category:
                        intent = category
                elif etype == "cache":
                    cache_hit = True
                    cache_type = event.get("content", {}).get("type", "") or "cache"
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
            model_code = entities.get("model_code") if isinstance(entities, dict) else None
            version = entities.get("version") if isinstance(entities, dict) else None

            # Persist turn + context + long-term memory (fail-open)
            # Background task — KHÔNG await ở đây để đóng kết nối SSE ngay sau `done`
            # (chờ Redis/PG sẽ làm UI "đang load" thêm 200-500ms dù đã có đủ câu trả lời)
            async def _persist():
                try:
                    if full_resp:
                        await save_turn(session_id, request.message, full_resp)
                    await update_current_context(
                        session_id,
                        model_code=model_code,
                        version=version,
                        topic=category or None,
                    )
                    if model_code:
                        await save_user_fact(session_id, "preferred_model", model_code)
                    if version:
                        await save_user_fact(session_id, "preferred_version", version)
                except Exception as exc:
                    logger.warning("persist turn background failed (non-blocking): %s", exc)

            try:
                asyncio.create_task(_persist())
            except Exception:
                pass

            prompt_tok = _estimate_tokens(request.message) + sum(
                _estimate_tokens(h.get("content", "")) for h in history
            )
            comp_tok = _estimate_tokens(full_resp)
            model_code = entities.get("model_code") if isinstance(entities, dict) else None
            model_version = entities.get("version") if isinstance(entities, dict) else None
            log_metric_background(
                record_metric(
                    request_id=req_id,
                    session_id=session_id,
                    query_text=request.message,
                    intent=intent,
                    decision=decision,
                    model_used=settings.llm_model,
                    prompt_version=getattr(settings, "app_version", "v1.0.0"),
                    prompt_tokens=prompt_tok,
                    completion_tokens=comp_tok,
                    ttft_ms=ttft_ms,
                    ttot_ms=total_latency_ms,
                    total_latency_ms=total_latency_ms,
                    latency_retrieval_ms=0,
                    latency_generation_ms=0,
                    cache_hit=cache_hit,
                    cache_type=cache_type,
                    tools_used=tools_used,
                    status_code=200,
                    model_code=model_code,
                    model_version=model_version,
                    retrieval_status="success" if tools_used else "none",
                    chunks_retrieved=len(tools_used),
                    reasoning_tokens=0,
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
    lines = [json.dumps(l, ensure_ascii=False) for l in logs]  # noqa: E741
    content = "\n".join(lines) + "\n" if lines else ""
    fname = "logs_" + (run_id or "all") + ".jsonl"
    return StreamingResponse(
        content=iter([content]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=" + fname},
    )
