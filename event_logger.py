"""
Structured event logging for runtime debugging.

Writes one JSON object per line to logs/events.jsonl.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_LOG_PATH = Path(__file__).resolve().parent / "logs" / "events.jsonl"


def _to_json_safe(value: Any) -> Any:
    """Convert values to JSON-safe representations."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(v) for v in value]
    return value


def log_event(event: str, **data: Any) -> None:
    """
    Append a structured event to the JSONL log file.

    Logging should never break bot flows. Failures are swallowed.
    """
    try:
        now_utc = datetime.now(timezone.utc)
        now_local = datetime.now().astimezone()
        payload = {
            "ts_utc": now_utc.isoformat(),
            "ts_local": now_local.isoformat(),
            "ts_unix_ms": int(now_utc.timestamp() * 1000),
            "event": event,
            **{k: _to_json_safe(v) for k, v in data.items()},
        }

        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with _LOCK:
            with _LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception as exc:
        print(f"⚠️ Error writing event log: {exc}")


def clear_event_log() -> dict:
    """
    Truncate the JSONL event log and return summary stats.
    """
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        removed_lines = 0
        removed_bytes = 0

        with _LOCK:
            if _LOG_PATH.exists():
                removed_bytes = _LOG_PATH.stat().st_size
                with _LOG_PATH.open("r", encoding="utf-8") as fh:
                    removed_lines = sum(1 for _ in fh)
                _LOG_PATH.write_text("", encoding="utf-8")
            else:
                _LOG_PATH.touch()

        return {
            "ok": True,
            "log_path": str(_LOG_PATH),
            "removed_lines": removed_lines,
            "removed_bytes": removed_bytes,
        }
    except Exception as exc:
        return {
            "ok": False,
            "log_path": str(_LOG_PATH),
            "error": str(exc),
        }
