"""
Read-only API routes for the admin dashboard.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from models.guild_settings import get_all_configured_guilds
from models.queue import queue_manager
from models.stats import get_all_time_stats, get_weekly_stats
from services.matchmaking import get_entry_player_count
from web.routes.auth import require_dashboard_auth

router = APIRouter(dependencies=[Depends(require_dashboard_auth)])


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

