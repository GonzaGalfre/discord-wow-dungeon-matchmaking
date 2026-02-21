"""
API routes for the admin dashboard.
"""

from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from config.settings import MAX_KEY_LEVEL, MIN_KEY_LEVEL
from models.database import get_connection
from models.guild_settings import get_all_configured_guilds
from models.queue import queue_manager
from models.stats import get_all_time_stats, get_weekly_stats
from services.matchmaking import get_entry_player_count
from event_logger import clear_event_log, log_event
from views.party import ACTIVE_DM_CONFIRMATIONS
from web.routes.auth import require_dashboard_auth

router = APIRouter(dependencies=[Depends(require_dashboard_auth)])
FAKE_USER_ID_START = 900000000000000000
_fake_user_id_counter = FAKE_USER_ID_START
_fake_id_lock = Lock()


class QueueClearRequest(BaseModel):
    guild_id: Optional[int] = None


class FakePlayerRequest(BaseModel):
    guild_id: int
    username: str = Field(min_length=1, max_length=64)
    role: str
    key_min: int
    key_max: int


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
    if key_min < MIN_KEY_LEVEL or key_max > MAX_KEY_LEVEL or key_min > key_max:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid key range. It must be {MIN_KEY_LEVEL}-{MAX_KEY_LEVEL} and min <= max."
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


def _guild_name_map() -> Dict[int, str]:
    return {
        row["guild_id"]: row["guild_name"]
        for row in get_all_configured_guilds()
    }


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
    return get_all_configured_guilds()


@router.get("/api/queue")
def get_queue_status() -> Dict[str, Any]:
    """
    Return queue status for every known guild.
    """
    name_map = _guild_name_map()
    known_guild_ids = set(name_map.keys()) | set(queue_manager.get_guild_ids())

    guilds: List[Dict[str, Any]] = []
    total_in_queue = 0

    for guild_id in sorted(known_guild_ids):
        entries = queue_manager.get_all_entries(guild_id)
        queue_count = len(entries)
        total_in_queue += queue_count

        guilds.append(
            {
                "guild_id": guild_id,
                "guild_name": name_map.get(guild_id, f"Guild {guild_id}"),
                "count": queue_count,
                "entries": [_serialize_entry(entry) for entry in entries],
                "active_matches": _active_matches(guild_id),
                "pending_confirmations": _pending_confirmations(guild_id),
            }
        )

    return {"total_in_queue": total_in_queue, "guilds": guilds}


@router.get("/api/queue/{guild_id}")
def get_queue_by_guild(guild_id: int) -> Dict[str, Any]:
    """
    Return queue details for a single guild.
    """
    name_map = _guild_name_map()
    entries = queue_manager.get_all_entries(guild_id)

    return {
        "guild_id": guild_id,
        "guild_name": name_map.get(guild_id, f"Guild {guild_id}"),
        "count": len(entries),
        "entries": [_serialize_entry(entry) for entry in entries],
        "active_matches": _active_matches(guild_id),
        "pending_confirmations": _pending_confirmations(guild_id),
    }


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
        return {"period": period, **stats}

    stats = get_weekly_stats(guild_id=guild_id)
    return {"period": period, **stats}


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
        return {
            "period": period,
            "guild_id": guild_id,
            "total_keys": stats["total_keys"],
            "avg_key_level": stats["avg_key_level"],
            "max_key_level": stats["max_key_level"],
        }

    stats = get_weekly_stats(guild_id=guild_id)
    return {
        "period": period,
        "guild_id": guild_id,
        "week_number": stats["week_number"],
        "total_keys": stats["total_keys"],
        "avg_key_level": stats["avg_key_level"],
        "max_key_level": stats["max_key_level"],
    }


@router.post("/api/admin/queue/clear")
def clear_queue(payload: QueueClearRequest) -> Dict[str, Any]:
    """
    Clear queue entries for one guild or all guilds.
    """
    if payload.guild_id is not None:
        removed = queue_manager.count(payload.guild_id)
        queue_manager.clear(payload.guild_id)
        log_event(
            "dashboard_admin_clear_queue",
            scope="guild",
            guild_id=payload.guild_id,
            removed_entries=removed,
        )
        return {
            "scope": "guild",
            "guild_id": payload.guild_id,
            "removed_entries": removed,
        }

    removed = queue_manager.total_count()
    queue_manager.clear_all()
    log_event(
        "dashboard_admin_clear_queue",
        scope="all",
        removed_entries=removed,
    )
    return {"scope": "all", "removed_entries": removed}


@router.post("/api/admin/dev/add-fake-player")
def add_fake_player(payload: FakePlayerRequest) -> Dict[str, Any]:
    """
    Add a fake solo player to queue (dashboard helper for testing).
    """
    role = payload.role.lower().strip()
    if role not in {"tank", "healer", "dps"}:
        raise HTTPException(status_code=400, detail="Role must be tank, healer, or dps.")

    _validate_key_range(payload.key_min, payload.key_max)

    fake_user_id = _generate_fake_user_id()
    queue_manager.add(
        payload.guild_id,
        fake_user_id,
        payload.username.strip(),
        payload.key_min,
        payload.key_max,
        role=role,
    )
    log_event(
        "dashboard_dev_add_fake_player",
        guild_id=payload.guild_id,
        fake_user_id=fake_user_id,
        username=payload.username.strip(),
        role=role,
        key_min=payload.key_min,
        key_max=payload.key_max,
    )
    return {
        "ok": True,
        "guild_id": payload.guild_id,
        "entry_type": "solo",
        "fake_user_id": fake_user_id,
    }


@router.post("/api/admin/dev/add-fake-group")
def add_fake_group(payload: FakeGroupRequest) -> Dict[str, Any]:
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
    log_event(
        "dashboard_dev_add_fake_group",
        guild_id=payload.guild_id,
        fake_user_id=fake_user_id,
        leader_name=payload.leader_name.strip(),
        composition=composition,
        key_min=payload.key_min,
        key_max=payload.key_max,
    )
    return {
        "ok": True,
        "guild_id": payload.guild_id,
        "entry_type": "group",
        "fake_user_id": fake_user_id,
        "player_count": total,
    }


@router.post("/api/admin/dev/cleanup")
def cleanup_fake_players(payload: FakeCleanupRequest) -> Dict[str, Any]:
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

    log_event(
        "dashboard_dev_cleanup_fake_players",
        scope="guild" if payload.guild_id is not None else "all",
        guild_id=payload.guild_id,
        removed_entries=removed,
        touched_guilds=touched_guilds,
    )

    return {
        "scope": "guild" if payload.guild_id is not None else "all",
        "guild_id": payload.guild_id,
        "removed_entries": removed,
        "touched_guilds": touched_guilds,
    }


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

