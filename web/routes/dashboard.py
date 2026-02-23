"""
API routes for the admin dashboard.
"""

from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config.settings import MAX_KEY_LEVEL, MIN_KEY_LEVEL
from models.database import get_connection
from models.guild_settings import get_all_configured_guilds
from models.queue import queue_manager
from models.stats import get_all_time_stats, get_weekly_stats
from runtime import get_bot_client
from services.match_flow import trigger_matchmaking_for_entry_threadsafe
from services.matchmaking import get_entry_player_count
from services.queue_status import refresh_lfg_setup_message
from services.queue_preferences import (
    normalize_roles,
    validate_keystone_input,
    validate_queue_key_range,
)
from event_logger import clear_event_log, get_event_log_path, log_event
from views.party import ACTIVE_DM_CONFIRMATIONS
from web.routes.auth import require_dashboard_auth

router = APIRouter(dependencies=[Depends(require_dashboard_auth)])
FAKE_USER_ID_START = 900000000000000000
JS_SAFE_INTEGER_MAX = 9007199254740991
_fake_user_id_counter = FAKE_USER_ID_START
_fake_id_lock = Lock()


class QueueClearRequest(BaseModel):
    guild_id: Optional[int] = None


class FakePlayerRequest(BaseModel):
    guild_id: int
    username: str = Field(min_length=1, max_length=64)
    role: Optional[str] = "dps"
    roles: Optional[List[str]] = None
    key_min: int
    key_max: int
    has_keystone: bool = False
    keystone_level: Optional[int] = None
    force_match: bool = True


class FakeGroupRequest(BaseModel):
    guild_id: int
    leader_name: str = Field(min_length=1, max_length=64)
    tanks: int = Field(ge=0, le=1)
    healers: int = Field(ge=0, le=1)
    dps: int = Field(ge=0, le=3)
    key_min: int
    key_max: int


class FakeCleanupRequest(BaseModel):
    guild_id: Optional[int] = None


class ClearHistoryRequest(BaseModel):
    confirm: bool = False


class ClearLogsRequest(BaseModel):
    confirm: bool = False


def _generate_fake_user_id() -> int:
    global _fake_user_id_counter
    with _fake_id_lock:
        _fake_user_id_counter += 1
        return _fake_user_id_counter


def _validate_key_range(key_min: int, key_max: int) -> None:
    try:
        validate_queue_key_range(key_min, key_max)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid key range. It must be 0 or {MIN_KEY_LEVEL}-{MAX_KEY_LEVEL}, and min <= max."
            ),
        )


def _serialize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert queue entry values to JSON-safe primitives.
    """
    value = dict(entry)
    timestamp = value.get("timestamp")
    if isinstance(timestamp, datetime):
        value["timestamp"] = timestamp.isoformat()
    return value


def _json_safe(value: Any) -> Any:
    """
    Convert values to JSON-safe primitives for JavaScript clients.

    Discord snowflake IDs exceed JS safe integer range, so convert those
    large integers to strings to avoid precision loss in the browser.
    """
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, int) and abs(value) > JS_SAFE_INTEGER_MAX:
        return str(value)
    return value


def _guild_name_map() -> Dict[int, str]:
    return {
        row["guild_id"]: row["guild_name"]
        for row in get_all_configured_guilds()
    }


def _entry_player_total(entries: List[Dict[str, Any]]) -> int:
    """
    Count represented players for queue entries (solo=1, groups=sum composition).
    """
    return sum(get_entry_player_count(entry) for entry in entries)


async def _refresh_lfg_embed_if_possible(guild_id: int) -> None:
    """
    Refresh persistent LFG setup embed if bot client is available.
    """
    bot_client = get_bot_client()
    if bot_client is None:
        return
    await refresh_lfg_setup_message(bot_client, guild_id)


def _active_matches(guild_id: int) -> List[Dict[str, Any]]:
    """
    Build active-match groups from queue entries that share match_message_id.
    """
    grouped: Dict[int, List[Dict[str, Any]]] = {}

    for user_id, data in queue_manager.items(guild_id):
        match_id = data.get("match_message_id")
        if match_id is None:
            continue
        grouped.setdefault(match_id, []).append({"user_id": user_id, **data})

    result: List[Dict[str, Any]] = []
    for match_id, entries in grouped.items():
        total_players = sum(get_entry_player_count(entry) for entry in entries)
        result.append(
            {
                "match_id": match_id,
                "total_players": total_players,
                "entries": [_serialize_entry(entry) for entry in entries],
            }
        )
    return result


def _pending_confirmations(guild_id: int) -> List[Dict[str, Any]]:
    """
    Build groups currently waiting for unanimous confirmation.
    """
    result: List[Dict[str, Any]] = []

    for session in ACTIVE_DM_CONFIRMATIONS.values():
        if session.guild_id != guild_id:
            continue
        if session.cancelled or session.completed:
            continue

        users_still = session.users_still_in_queue()
        if len(users_still) < 2:
            continue

        entries: List[Dict[str, Any]] = []
        total_players = 0
        for user_id in users_still:
            entry = queue_manager.get(guild_id, user_id)
            if not entry:
                continue
            entries.append(_serialize_entry({"user_id": user_id, **entry}))
            total_players += get_entry_player_count(entry)

        if len(entries) < 2:
            continue

        confirmed_targets = sum(1 for uid in users_still if uid in session.confirmed_ids)
        fallback_targets = sum(
            1 for uid in users_still if uid in getattr(session, "channel_fallback_user_ids", set())
        )

        result.append(
            {
                "phase": "awaiting_confirmation",
                "user_ids": users_still,
                "total_players": total_players,
                "confirmation_targets_total": len(users_still),
                "confirmation_targets_confirmed": confirmed_targets,
                "confirmation_targets_pending": len(users_still) - confirmed_targets,
                "channel_fallback_count": fallback_targets,
                "entries": entries,
            }
        )

    return result


@router.get("/api/guilds")
def get_guilds() -> List[Dict[str, Any]]:
    """
    Return configured guild list from database.
    """
    return _json_safe(get_all_configured_guilds())


@router.get("/api/queue")
def get_queue_status() -> Dict[str, Any]:
    """
    Return queue status for every known guild.
    """
    name_map = _guild_name_map()
    known_guild_ids = set(name_map.keys()) | set(queue_manager.get_guild_ids())

    guilds: List[Dict[str, Any]] = []
    total_players_in_queue = 0
    total_entries_in_queue = 0

    for guild_id in sorted(known_guild_ids):
        entries = queue_manager.get_all_entries(guild_id)
        entry_count = len(entries)
        player_count = _entry_player_total(entries)
        total_entries_in_queue += entry_count
        total_players_in_queue += player_count

        guilds.append(
            {
                "guild_id": guild_id,
                "guild_name": name_map.get(guild_id, f"Guild {guild_id}"),
                "count": player_count,
                "entry_count": entry_count,
                "player_count": player_count,
                "entries": [_serialize_entry(entry) for entry in entries],
                "active_matches": _active_matches(guild_id),
                "pending_confirmations": _pending_confirmations(guild_id),
            }
        )

    return _json_safe({
        "total_in_queue": total_players_in_queue,
        "total_players_in_queue": total_players_in_queue,
        "total_entries_in_queue": total_entries_in_queue,
        "guilds": guilds,
    })


@router.get("/api/queue/{guild_id}")
def get_queue_by_guild(guild_id: int) -> Dict[str, Any]:
    """
    Return queue details for a single guild.
    """
    name_map = _guild_name_map()
    entries = queue_manager.get_all_entries(guild_id)
    entry_count = len(entries)
    player_count = _entry_player_total(entries)

    return _json_safe({
        "guild_id": guild_id,
        "guild_name": name_map.get(guild_id, f"Guild {guild_id}"),
        "count": player_count,
        "entry_count": entry_count,
        "player_count": player_count,
        "entries": [_serialize_entry(entry) for entry in entries],
        "active_matches": _active_matches(guild_id),
        "pending_confirmations": _pending_confirmations(guild_id),
    })


@router.get("/api/leaderboard")
def get_leaderboard(
    period: str = Query(default="weekly", pattern="^(weekly|alltime)$"),
    guild_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Return leaderboard data for weekly/all-time period.
    """
    if period == "alltime":
        stats = get_all_time_stats(guild_id=guild_id)
        return _json_safe({"period": period, **stats})

    stats = get_weekly_stats(guild_id=guild_id)
    return _json_safe({"period": period, **stats})


@router.get("/api/completed")
def get_completed_keys(
    period: str = Query(default="weekly", pattern="^(weekly|alltime)$"),
    guild_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Return aggregate completed-key data (used as "groups formed").
    """
    if period == "alltime":
        stats = get_all_time_stats(guild_id=guild_id)
        return _json_safe({
            "period": period,
            "guild_id": guild_id,
            "total_keys": stats["total_keys"],
            "avg_key_level": stats["avg_key_level"],
            "max_key_level": stats["max_key_level"],
        })

    stats = get_weekly_stats(guild_id=guild_id)
    return _json_safe({
        "period": period,
        "guild_id": guild_id,
        "week_number": stats["week_number"],
        "total_keys": stats["total_keys"],
        "avg_key_level": stats["avg_key_level"],
        "max_key_level": stats["max_key_level"],
    })


@router.post("/api/admin/queue/clear")
async def clear_queue(payload: QueueClearRequest) -> Dict[str, Any]:
    """
    Clear queue entries for one guild or all guilds.
    """
    if payload.guild_id is not None:
        removed = queue_manager.count(payload.guild_id)
        queue_manager.clear(payload.guild_id)
        await _refresh_lfg_embed_if_possible(payload.guild_id)
        log_event(
            "dashboard_admin_clear_queue",
            scope="guild",
            guild_id=payload.guild_id,
            removed_entries=removed,
        )
        return _json_safe({
            "scope": "guild",
            "guild_id": payload.guild_id,
            "removed_entries": removed,
        })

    removed = queue_manager.total_count()
    guild_ids = list(queue_manager.get_guild_ids())
    queue_manager.clear_all()
    for guild_id in guild_ids:
        await _refresh_lfg_embed_if_possible(guild_id)
    log_event(
        "dashboard_admin_clear_queue",
        scope="all",
        removed_entries=removed,
    )
    return _json_safe({"scope": "all", "removed_entries": removed})


@router.post("/api/admin/dev/add-fake-player")
async def add_fake_player(payload: FakePlayerRequest) -> Dict[str, Any]:
    """
    Add a fake solo player to queue (dashboard helper for testing).
    """
    roles = normalize_roles(roles=payload.roles, role=payload.role)
    if not roles:
        raise HTTPException(status_code=400, detail="At least one valid role is required.")

    _validate_key_range(payload.key_min, payload.key_max)
    try:
        validate_keystone_input(payload.has_keystone, payload.keystone_level)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    fake_user_id = _generate_fake_user_id()
    queue_manager.add(
        payload.guild_id,
        fake_user_id,
        payload.username.strip(),
        payload.key_min,
        payload.key_max,
        roles=roles,
        has_keystone=payload.has_keystone,
        keystone_level=payload.keystone_level,
    )
    await _refresh_lfg_embed_if_possible(payload.guild_id)
    force_match_result: Dict[str, Any] = {"forced": False}
    if payload.force_match:
        bot_client = get_bot_client()
        if bot_client is None:
            force_match_result = {
                "forced": True,
                "matched": False,
                "error": "Bot client is not available yet.",
            }
        else:
            result = await trigger_matchmaking_for_entry_threadsafe(
                bot_client,
                payload.guild_id,
                fake_user_id,
                payload.key_min,
                payload.key_max,
                source="dashboard_add_fake_player",
                triggered_by_user_id=None,
                mention_fake_users=True,
                message_prefix="🧪 **[DASHBOARD AUTO]** ",
            )
            force_match_result = {
                "forced": True,
                "matched": bool(result.get("matched")),
                "user_count": result.get("user_count", 0),
                "error": result.get("error"),
            }

    log_event(
        "dashboard_dev_add_fake_player",
        guild_id=payload.guild_id,
        fake_user_id=fake_user_id,
        username=payload.username.strip(),
        roles=roles,
        key_min=payload.key_min,
        key_max=payload.key_max,
        has_keystone=payload.has_keystone,
        keystone_level=payload.keystone_level,
        force_match=payload.force_match,
        force_match_result=force_match_result,
    )
    return _json_safe({
        "ok": True,
        "guild_id": payload.guild_id,
        "entry_type": "solo",
        "fake_user_id": fake_user_id,
        "roles": roles,
        "force_match": force_match_result,
    })


@router.post("/api/admin/dev/add-fake-group")
async def add_fake_group(payload: FakeGroupRequest) -> Dict[str, Any]:
    """
    Add a fake group to queue (dashboard helper for testing).
    """
    _validate_key_range(payload.key_min, payload.key_max)

    total = payload.tanks + payload.healers + payload.dps
    if total <= 0 or total > 5:
        raise HTTPException(status_code=400, detail="Group size must be between 1 and 5.")

    composition = {
        "tank": payload.tanks,
        "healer": payload.healers,
        "dps": payload.dps,
    }
    fake_user_id = _generate_fake_user_id()
    queue_manager.add(
        payload.guild_id,
        fake_user_id,
        payload.leader_name.strip(),
        payload.key_min,
        payload.key_max,
        composition=composition,
    )
    await _refresh_lfg_embed_if_possible(payload.guild_id)
    log_event(
        "dashboard_dev_add_fake_group",
        guild_id=payload.guild_id,
        fake_user_id=fake_user_id,
        leader_name=payload.leader_name.strip(),
        composition=composition,
        key_min=payload.key_min,
        key_max=payload.key_max,
    )
    return _json_safe({
        "ok": True,
        "guild_id": payload.guild_id,
        "entry_type": "group",
        "fake_user_id": fake_user_id,
        "player_count": total,
    })


@router.post("/api/admin/dev/cleanup")
async def cleanup_fake_players(payload: FakeCleanupRequest) -> Dict[str, Any]:
    """
    Remove all fake players/groups from queue for one guild or all guilds.
    """
    guild_ids = (
        [payload.guild_id]
        if payload.guild_id is not None
        else list(queue_manager.get_guild_ids())
    )

    removed = 0
    touched_guilds = 0
    for guild_id in guild_ids:
        guild_touched = False
        fake_user_ids = [
            user_id
            for user_id, _entry in list(queue_manager.items(guild_id))
            if user_id > FAKE_USER_ID_START
        ]
        if fake_user_ids:
            touched_guilds += 1
        for user_id in fake_user_ids:
            if queue_manager.remove(guild_id, user_id):
                removed += 1
                guild_touched = True
        if guild_touched:
            await _refresh_lfg_embed_if_possible(guild_id)

    log_event(
        "dashboard_dev_cleanup_fake_players",
        scope="guild" if payload.guild_id is not None else "all",
        guild_id=payload.guild_id,
        removed_entries=removed,
        touched_guilds=touched_guilds,
    )

    return _json_safe({
        "scope": "guild" if payload.guild_id is not None else "all",
        "guild_id": payload.guild_id,
        "removed_entries": removed,
        "touched_guilds": touched_guilds,
    })


@router.post("/api/admin/database/clear-history")
def clear_history_data(payload: ClearHistoryRequest) -> Dict[str, Any]:
    """
    Clear leaderboard and key history data only.
    """
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required. Send {\"confirm\": true}.",
        )

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM completed_keys")
    completed_keys_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM key_participants")
    key_participants_count = cursor.fetchone()["total"]

    # Clear child/parent tables in safe order.
    cursor.execute("DELETE FROM key_participants")
    cursor.execute("DELETE FROM completed_keys")
    conn.commit()
    log_event(
        "dashboard_admin_clear_history",
        deleted_completed_keys=completed_keys_count,
        deleted_key_participants=key_participants_count,
    )

    return {
        "ok": True,
        "deleted": {
            "completed_keys": completed_keys_count,
            "key_participants": key_participants_count,
        },
        "preserved": {
            "guild_settings": True,
            "queue_entries": True,
        },
    }


@router.post("/api/admin/logs/clear")
def clear_runtime_logs(payload: ClearLogsRequest) -> Dict[str, Any]:
    """
    Clear runtime event log file (logs/events.jsonl).
    """
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

    # Record this action after truncation so the fresh file has an audit entry.
    log_event(
        "dashboard_admin_clear_logs",
        removed_lines=result.get("removed_lines", 0),
        removed_bytes=result.get("removed_bytes", 0),
    )
    result["logged_action"] = True
    return result


@router.get("/api/admin/logs/download")
def download_runtime_logs() -> FileResponse:
    """
    Download runtime event log file (logs/events.jsonl).
    """
    log_path = get_event_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.touch()

    return FileResponse(
        path=log_path,
        media_type="application/jsonl",
        filename="events.jsonl",
    )

