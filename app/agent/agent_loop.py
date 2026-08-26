import logging
import time

from app.agent.graph import get_compiled_graph
from app.agent.nodes.respond import AgentResult

logger = logging.getLogger("bds.agent")


class AgentLoop:
    def __init__(self):
        self.graph = get_compiled_graph()

    async def run(self, query: str, history: list[dict], current_context: dict = None, session_id: str | None = None, intent: str | None = None) -> AgentResult:
        if history is None:
            history = []
        _ans_cache_key = None
        _ans_cache_enabled = False
        # L1 exact-match ans cache check (single-turn only, fail-open)
        try:
            from app.core.cache import _is_cacheable, make_answer_key, get_ans_cached

            _intent_for_cache = intent
            if _intent_for_cache is None:
                try:
                    import re as _re

                    _greet_pat = _re.compile(
                        r"^(hello|hi|hey|chào|chào\s*bạn|xin\s*chào|alo|cảm\s*ơn|thanks|thank\s*you|chào\s*buổi\s*(sáng|trưa|chiều|tối))[\s!?.]*$",
                        _re.IGNORECASE,
                    )
                    if _greet_pat.search((query or "").strip()):
                        _intent_for_cache = "greeting"
                except Exception:
                    pass
            if _is_cacheable(history, session_id, _intent_for_cache):
                _model_code = None
                _version = None
                try:
                    from app.agent.classifier import get_classifier

                    _clf = get_classifier()
                    try:
                        _cr = _clf.classify(query)
                        _model_code = _cr.entities.get("model_code")
                        _version = _cr.entities.get("version")
                    except Exception:
                        try:
                            _mc, _ = _clf._detect_model(query)
                            _model_code = _mc
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    _ans_cache_key = await make_answer_key(query, _model_code, _version)
                except TypeError:
                    try:
                        _ans_cache_key = await make_answer_key(query)
                    except Exception:
                        _ans_cache_key = None
                if _ans_cache_key:
                    try:
                        _cached = await get_ans_cached(_ans_cache_key)
                    except Exception as e:
                        logger.debug("ans cache get failed (fail-open): %s", e)
                        _cached = None
                    if isinstance(_cached, dict) and _cached.get("response") is not None:
                        return AgentResult(
                            response=_cached.get("response", ""),
                            sources=_cached.get("sources", []) if isinstance(_cached.get("sources", []), list) else [],
                            decision=_cached.get("decision", "answer"),
                            cache_hit=True,
                            cache_type="ans",
                            classify_result={"decision": _cached.get("decision", "answer")},
                        )
                    _ans_cache_enabled = True
        except ImportError as e:
            logger.debug("ans cache helpers not available (fail-open): %s", e)
        except Exception as e:
            logger.debug("ans cache check failed (fail-open): %s", e)
            _ans_cache_key = None
            _ans_cache_enabled = False

        state = {
            "query": query,
            "history": history,
            "current_context": current_context or {},
            "t0": time.time(),
        }
        final = await self.graph.ainvoke(state)
        result = final.get("result")
        if result is None:
            return AgentResult(
                response="Mình chưa thể hoàn tất câu trả lời lúc này.",
                decision="refuse",
                classify_result={"decision": "refuse", "reason_code": "system_error"},
            )
        # SET ans cache on miss (only answer, fail-open)
        if _ans_cache_enabled and _ans_cache_key:
            try:
                if result.decision == "answer" and result.response:
                    from app.core.cache import set_ans_cached

                    await set_ans_cached(
                        _ans_cache_key,
                        {"response": result.response, "sources": result.sources or [], "decision": result.decision},
                    )
            except Exception as e:
                logger.debug("ans cache set failed (fail-open): %s", e)
        return result

    async def run_stream(self, query: str, history: list[dict], current_context: dict = None, session_id: str | None = None, intent: str | None = None):
        """True streaming: token LLM được đẩy qua custom stream mode ngay khi sinh."""
        import asyncio

        if history is None:
            history = []

        # ── L1 exact-match ans cache check (single-turn only, fail-open) ──
        _ans_cache_key = None
        _ans_cache_enabled = False
        _final_response_for_cache: str | None = None
        _sources_for_cache: list[dict] = []
        _decision_for_cache: str = "answer"
        try:
            from app.core.cache import _is_cacheable, make_answer_key, get_ans_cached

            _intent_for_cache = intent
            if _intent_for_cache is None:
                try:
                    import re as _re

                    _greet_pat = _re.compile(
                        r"^(hello|hi|hey|chào|chào\s*bạn|xin\s*chào|alo|cảm\s*ơn|thanks|thank\s*you|chào\s*buổi\s*(sáng|trưa|chiều|tối))[\s!?.]*$",
                        _re.IGNORECASE,
                    )
                    if _greet_pat.search((query or "").strip()):
                        _intent_for_cache = "greeting"
                except Exception:
                    pass
            if _is_cacheable(history, session_id, _intent_for_cache):
                _model_code = None
                _version = None
                try:
                    from app.agent.classifier import get_classifier

                    _clf = get_classifier()
                    try:
                        _cr = _clf.classify(query)
                        _model_code = _cr.entities.get("model_code")
                        _version = _cr.entities.get("version")
                    except Exception:
                        try:
                            _mc, _ = _clf._detect_model(query)
                            _model_code = _mc
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    _ans_cache_key = await make_answer_key(query, _model_code, _version)
                except TypeError:
                    try:
                        _ans_cache_key = await make_answer_key(query)
                    except Exception:
                        _ans_cache_key = None
                if _ans_cache_key:
                    try:
                        _cached = await get_ans_cached(_ans_cache_key)
                    except Exception as e:
                        logger.debug("ans cache get failed (fail-open): %s", e)
                        _cached = None
                    if isinstance(_cached, dict) and _cached.get("response") is not None:
                        _resp = _cached.get("response")
                        _src = _cached.get("sources", [])
                        _dec = _cached.get("decision", "answer")
                        if not isinstance(_src, list):
                            _src = []
                        # SSE replay: status -> cache -> answer/clarify -> sources -> done (no tool_call)
                        yield {"type": "status", "content": "Đang tìm câu trả lời…"}
                        yield {"type": "cache", "content": {"hit": True, "type": "ans"}}
                        if _dec == "out_of_scope":
                            yield {"type": "answer", "content": _resp}
                        elif _dec == "clarify":
                            yield {"type": "clarify", "content": _resp}
                            yield {"type": "sources", "content": []}
                        elif _dec == "greeting":
                            yield {"type": "answer", "content": _resp}
                        else:
                            yield {"type": "answer", "content": _resp}
                            yield {"type": "sources", "content": _src}
                        yield {"type": "done"}
                        return
                    _ans_cache_enabled = True
        except ImportError as e:
            logger.debug("ans cache helpers not available (fail-open): %s", e)
        except Exception as e:
            logger.debug("ans cache check failed (fail-open): %s", e)
            _ans_cache_key = None
            _ans_cache_enabled = False

        state = {
            "query": query,
            "history": history,
            "current_context": current_context or {},
            "t0": time.time(),
        }

        yielded_tokens = False
        queue: asyncio.Queue = asyncio.Queue()
        _SENTINEL = object()
        graph_error: Exception | None = None

        async def _producer():
            nonlocal graph_error
            try:
                async for mode, payload in self.graph.astream(state, stream_mode=["updates", "custom"]):
                    await queue.put((mode, payload))
            except Exception as e:
                graph_error = e
            finally:
                await queue.put(_SENTINEL)

        task = asyncio.create_task(_producer())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=3.0)
                except asyncio.TimeoutError:
                    yield {"type": "ping"}
                    continue
                if item is _SENTINEL:
                    break
                mode, payload = item
                if mode == "custom":
                    if isinstance(payload, dict) and payload.get("type") == "token":
                        yielded_tokens = True
                    yield payload
                    continue
                for node_name, node_output in payload.items():
                    if node_name == "classify":
                        dec = node_output.get("decision", "answer")
                        yield {"type": "decision", "content": dec}
                        yield {
                            "type": "classify",
                            "content": {
                                "specificity": node_output.get("specificity", ""),
                                "entities": node_output.get("entities", {}),
                                "category": node_output.get("category", ""),
                            },
                        }
                    elif node_name == "call_tools":
                        for tr in node_output.get("tool_results", []):
                            yield {"type": "tool_call", "content": {"tool": tr["tool"], "success": tr["success"]}}
                        if node_output.get("cache_hit"):
                            yield {
                                "type": "cache",
                                "content": {
                                    "hit": True,
                                    "type": node_output.get("cache_type", "") or "cache",
                                },
                            }
                    elif node_name == "generate":
                        # Với stream thật, token đã được đẩy qua custom, không yield cả cục nữa
                        pass
                    elif node_name == "validate":
                        pass
                    elif node_name == "respond":
                        result = node_output.get("result")
                        if result is None:
                            continue
                        # capture for ans cache SET (only answer should be cached)
                        try:
                            _final_response_for_cache = result.response
                            _decision_for_cache = result.decision
                        except Exception:
                            pass
                        if result.decision == "out_of_scope":
                            yield {"type": "answer", "content": result.response}
                            _sources_for_cache = []
                        elif result.decision == "clarify":
                            yield {"type": "clarify", "content": result.response}
                            yield {"type": "sources", "content": []}
                            _sources_for_cache = []
                        elif result.decision == "refuse":
                            if not yielded_tokens:
                                yield {"type": "token", "content": result.response}
                            _sources_for_cache = []
                        elif not yielded_tokens:
                            yield {"type": "token", "content": result.response}
                        if result.sources and result.decision == "answer":
                            seen = set()
                            formatted = []
                            for c in sorted(result.sources, key=lambda x: x.get("score", 0), reverse=True):
                                if c.get("score", 0) < 0.4:
                                    continue
                                url = c.get("source_url", "")
                                if not url or not url.startswith("http"):
                                    continue
                                if "dat-coc" in url and c.get("source_type") != "pricing":
                                    continue
                                if url in seen:
                                    continue
                                seen.add(url)
                                model = c.get("model_code", "")
                                label = c.get("source_type", "")
                                page = c.get("page", "")
                                page_str = f" - Trang {page}" if page else ""
                                score = round(c.get("score", 0), 3)
                                text = f"{model} ({label}{page_str})" if model and label else (label or url)
                                formatted.append({"text": text, "url": url, "type": label, "score": score})
                                if len(formatted) >= 5:
                                    break
                            if formatted:
                                yield {"type": "sources", "content": formatted}
                                _sources_for_cache = formatted
                            else:
                                _sources_for_cache = []
                        else:
                            if result.decision == "answer":
                                # answer but no sources after filter
                                if not _sources_for_cache:
                                    _sources_for_cache = []
                        # if answer but yielded_tokens true, sources already handled; keep _sources_for_cache as above
                    # keep decision/sources for outer scope even before respond (default)
            if graph_error is not None:
                logger.error("GRAPH ERROR %s", graph_error, exc_info=graph_error)
                yield {"type": "error", "content": "Có lỗi xảy ra khi xử lý câu hỏi. Vui lòng thử lại."}
        finally:
            if not task.done():
                task.cancel()
            # Miss: SET ans cache if cacheable and answer (fail-open) — must be in finally to run even if client disconnects (GeneratorExit)
            if _ans_cache_enabled and _ans_cache_key and _final_response_for_cache and _decision_for_cache == "answer":
                try:
                    from app.core.cache import set_ans_cached

                    await set_ans_cached(
                        _ans_cache_key,
                        {"response": _final_response_for_cache, "sources": _sources_for_cache, "decision": _decision_for_cache},
                    )
                    logger.info("ANS SET DONE key=%s", _ans_cache_key)
                except Exception as e:
                    logger.debug("ans cache set failed (fail-open): %s", e)
            else:
                logger.info("ANS SET SKIP enabled=%s key=%s resp_len=%s decision=%s", _ans_cache_enabled, _ans_cache_key, len(_final_response_for_cache) if _final_response_for_cache else 0, _decision_for_cache)
        yield {"type": "done"}
