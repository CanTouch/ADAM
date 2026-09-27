"""Appends one line per action to AgentSandbox/logs/adam_log.txt."""
import json
import threading
from datetime import datetime

from config import LOG_FILE

MAX_RESULT_CHARS = 2000
_lock = threading.Lock()


def log(action, params, decision, result):
    """decision is 'approved', 'rejected', or 'auto' (no confirmation needed)."""
    result = str(result).replace("\n", "\\n")
    if len(result) > MAX_RESULT_CHARS:
        result = result[:MAX_RESULT_CHARS] + f"... [truncated, {len(result)} chars]"
    line = (
        f"{datetime.now():%Y-%m-%d %H:%M:%S} | {action} | "
        f"{json.dumps(params, ensure_ascii=False)} | {decision} | {result}\n"
    )
    with _lock, open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
