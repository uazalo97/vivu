"""FastAPI backend cho chatbot VIVU (UC-01).

Endpoints:
  POST /api/chat/stream  → SSE: stage → sources → delta* → metrics → done
  GET  /api/suggestions  → list gợi ý
  GET  /api/health       → {status, qdrant, postgres, llm}

Chạy:  uvicorn backend.main:app --port 8000 --reload
"""

import datetime
import json
import sys
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Import retriever + lib (cùng folder backend/)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from retriever import hybrid_retriever as hr  # noqa: E402
from lib import openrouter  # noqa: E402

app = FastAPI(title="VIVU Chatbot API", version="0.1.0")

# ── Batching: flush theo số token (mặc định ~10 token/event) ───────────────
MAX_TOKENS_PER_EVENT = 10
# Citation hiển thị trên UI: chỉ top N chunk (LLM vẫn đọc đủ top_k)
CITATIONS_MAX = 2


def _json_default(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    return str(o)


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False, default=_json_default)}\n\n"


def batched_tokens(token_iter, max_tokens=MAX_TOKENS_PER_EVENT):
    """Gom token thành từng chunk ~max_tokens → yield (không theo thời gian)."""
    buf = ""
    count = 0
    for token in token_iter:
        buf += token
        count += 1
        if count >= max_tokens:
            yield buf
            buf = ""
            count = 0
    if buf:
        yield buf


class ChatRequest(BaseModel):
    message: str
    top_k: int = 3


def gen_chat(req: ChatRequest):
    """SSE generator: stage → sources → delta* → metrics → done.

    Chạy đồng bộ (không thread) để tránh Windows socket/threading issues
    (ví dụ: psycopg2/qdrant_client trong sub-thread đôi khi trả [Errno 22]).
    Stage events được push bằng cách gọi yield trực tiếp từ on_stage.
    """
    openrouter.reset_metrics()  # metrics chỉ tính request hiện tại

    def _err_content(e: Exception) -> str:
        tb = traceback.format_exception(type(e), e, e.__traceback__)
        return f"Đã có lỗi khi tra cứu: {e}\n\n{''.join(tb)}"

    try:
        # ── Retrieve đồng bộ: push stage events bằng cách yield từ helper ──
        yield sse({"type": "stage", "data": {"label": hr.STAGE_LABELS["detect"]}})
        yield sse({"type": "stage", "data": {"label": hr.STAGE_LABELS["search"]}})

        try:
            result = hr.retrieve(req.message, top_k=req.top_k)
        except Exception as e:  # noqa: BLE001
            yield sse({"type": "done", "data": {
                "id": str(uuid.uuid4()),
                "content": _err_content(e),
            }})
            return

        # Sources — chỉ hiển thị top CITATIONS_MAX chunk + tối đa CITATIONS_MAX brochure
        yield sse({"type": "stage", "data": {"label": hr.STAGE_LABELS["price"]}})
        yield sse({"type": "sources", "data": {
            "chunks": result["chunks"][:CITATIONS_MAX],
            "price": result["price"],
            "brochures": result["brochures"][:CITATIONS_MAX],
        }})

        # Answer — stream LLM tokens (batched)
        yield sse({"type": "stage", "data": {"label": hr.STAGE_LABELS["answer"]}})
        content_parts: list[str] = []
        for chunk in batched_tokens(
            hr.generate_answer_stream(req.message, result["chunks"],
                                      result["price"], result["brochures"],
                                      maintenance=result.get("maintenance"),
                                      model_list=result.get("model_list"))):
            content_parts.append(chunk)
            yield sse({"type": "delta", "data": {"content": chunk}})
        content = "".join(content_parts)

        # Metrics
        sm = openrouter.summarize_metrics()
        tot = sm["total"]
        chat = sm["by_op"].get("chat", {})
        metrics = {
            "total_ms": round(tot["latency_ms"], 1),
            "api_calls": tot["calls"],
            "tokens_in": tot["input_tokens"],
            "tokens_out": tot["output_tokens"],
            "ttft_ms": round(chat["ttft_ms"] / chat["ttft_calls"], 1)
                       if chat.get("ttft_calls") else None,
            "stages": {k: v["calls"] for k, v in sm["by_op"].items()},
        }
        yield sse({"type": "metrics", "data": metrics})

        # Done
        yield sse({"type": "done", "data": {
            "id": str(uuid.uuid4()),
            "content": content,
        }})
    except Exception as e:  # noqa: BLE001
        yield sse({"type": "done", "data": {
            "id": str(uuid.uuid4()),
            "content": _err_content(e),
        }})


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    return StreamingResponse(gen_chat(req), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/suggestions")
def suggestions():
    return [
        "VF 9 Plus giá bao nhiêu?",
        "VF 8 có những màu ngoại thất nào?",
        "Chính sách bảo hành pin VinFast như thế nào?",
        "VF 6 Eco và VF 6 Plus khác gì nhau?",
        "Trễ hạn thanh toán phí thuê pin thì sao?",
        "Tải brochure VF 9 ở đâu?",
    ]


@app.get("/api/health")
def health():
    ok = bool(openrouter.API_KEY)
    return {
        "status": "ok" if ok else "degraded",
        "qdrant": "up",
        "postgres": "up",
        "llm": "ok" if ok else "missing OPENROUTER_API_KEY",
    }
