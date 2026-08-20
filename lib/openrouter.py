#!/usr/bin/env python3
"""DEPRECATED shim — use lib.openai_client instead. Kept for backward compat."""

import warnings

warnings.warn(
    "lib.openrouter is deprecated, use lib.openai_client (OpenAI pure). Shim will be removed.",
    DeprecationWarning,
    stacklevel=2,
)

from lib.openai_client import *  # noqa: E402,F401,F403
from lib.openai_client import (  # noqa: E402,F401
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
