"""
Models module for the WoW Mythic+ LFG Bot.

This module contains data structures and storage classes.
"""

from models.queue import QueueManager, queue_manager
from models.database import get_connection, close_connection, get_role_id
from models.stats import (
    record_completed_key,
    get_weekly_stats,
    get_all_time_stats,
    get_player_stats,
    get_current_week_number,
)
from models.guild_settings import (
    get_guild_settings,
    save_guild_settings,
    update_guild_channel,
    get_all_configured_guilds,
    get_match_channel_id,
    get_announcement_channel_id,
)

__all__ = [
    # Queue
    "QueueManager",
    "queue_manager",
    # Database
    "get_connection",
    "close_connection",
    "get_role_id",
    # Stats
    "record_completed_key",
    "get_weekly_stats",
    "get_all_time_stats",
    "get_player_stats",
    "get_current_week_number",
    # Guild Settings
    "get_guild_settings",
    "save_guild_settings",
    "update_guild_channel",
    "get_all_configured_guilds",
    "get_match_channel_id",
    "get_announcement_channel_id",
]
