#!/usr/bin/env python3
"""DEPRECATED shim — use backend.lib.openai_client instead. Kept for backward compat."""

import warnings

warnings.warn(
    "backend.lib.openrouter is deprecated, use backend.lib.openai_client (OpenAI pure). Shim will be removed.",
    DeprecationWarning,
    stacklevel=2,
)

from openai_client import *  # noqa: E402,F401,F403
from openai_client import (  # noqa: E402,F401
    API_KEY,
    BASE_URL,
    CHAT_MODEL,
    EMBED_MODEL,
    chat_completion,
    chat_completion_stream,
    embed_text,
    embed_texts,
    get_metrics,
    summarize_metrics,
)
