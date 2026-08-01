# -*- coding: utf-8 -*-
"""
Token usage logger — appends per-turn usage to a JSONL file.

Each line records: timestamp, model, project (from request headers),
prompt_tokens, completion_tokens, total_tokens.
"""

import json
import time
from pathlib import Path
from typing import Optional
from loguru import logger

USAGE_LOG_PATH = Path.home() / "Desktop" / ".kiro-token-usage.jsonl"


def log_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    project: Optional[str] = None,
    session: Optional[str] = None,
) -> None:
    """Append a usage record to the JSONL log file."""
    entry = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    if project:
        entry["project"] = project
    if session:
        entry["session"] = session

    try:
        with open(USAGE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[UsageLogger] Failed to write: {e}")
