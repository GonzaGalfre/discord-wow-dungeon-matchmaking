"""Infrastructure API routes for the admin dashboard."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from event_logger import clear_event_log, get_event_log_path, log_event
from models.guild_settings import get_all_configured_guilds
from runtime import get_bot_client
from web.routes.auth import require_dashboard_auth

router = APIRouter(dependencies=[Depends(require_dashboard_auth)])
JS_SAFE_INTEGER_MAX = 9007199254740991


class ClearLogsRequest(BaseModel):
    confirm: bool = False


def _json_safe(value: Any) -> Any:
    """Convert Discord snowflakes to strings before returning JSON."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, int) and abs(value) > JS_SAFE_INTEGER_MAX:
        return str(value)
    return value


@router.get("/api/status")
def get_status() -> Dict[str, Any]:
    """Return basic runtime status for WipyBot."""
    bot = get_bot_client()
    if bot is None or not getattr(bot, "is_ready", lambda: False)():
        return {
            "bot_ready": False,
            "bot_user": None,
            "connected_guild_count": 0,
        }

    return _json_safe({
        "bot_ready": True,
        "bot_user": str(bot.user) if bot.user else None,
        "connected_guild_count": len(bot.guilds),
        "connected_guilds": [
            {"guild_id": guild.id, "guild_name": guild.name}
            for guild in bot.guilds
        ],
    })


@router.get("/api/guilds")
def get_guilds() -> List[Dict[str, Any]]:
    """Return configured guild list from SQLite."""
    return _json_safe(get_all_configured_guilds())


@router.post("/api/admin/logs/clear")
def clear_runtime_logs(payload: ClearLogsRequest) -> Dict[str, Any]:
    """Clear runtime event log file."""
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required. Send {\"confirm\": true}.",
        )

    result = clear_event_log()
    if not result.get("ok"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear logs: {result.get('error', 'unknown error')}",
        )

    log_event(
        "dashboard_admin_clear_logs",
        removed_lines=result.get("removed_lines", 0),
        removed_bytes=result.get("removed_bytes", 0),
    )
    result["logged_action"] = True
    return result


@router.get("/api/admin/logs/download")
def download_runtime_logs() -> FileResponse:
    """Download runtime event log file."""
    log_path = get_event_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.touch()

    return FileResponse(
        path=log_path,
        media_type="application/jsonl",
        filename="events.jsonl",
    )
