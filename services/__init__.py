"""
Services module for the WoW Mythic+ LFG Bot.

This module contains business logic for matchmaking and embed building.
"""

from services.matchmaking import (
    is_valid_composition,
    get_role_counts,
    is_group_entry,
    get_entry_player_count,
    ranges_overlap,
    get_overlapping_range,
    get_users_with_overlap,
    calculate_common_range,
)

from services.embeds import (
    build_match_embed,
    build_confirmation_embed,
    format_entry_composition,
)

from services.leaderboard import (
    build_weekly_leaderboard_embed,
    build_alltime_leaderboard_embed,
    build_player_stats_embed,
    build_weekly_announcement_embed,
)

__all__ = [
    # Matchmaking
    "is_valid_composition",
    "get_role_counts",
    "is_group_entry",
    "get_entry_player_count",
    "ranges_overlap",
    "get_overlapping_range",
    "get_users_with_overlap",
    "calculate_common_range",
    # Embeds
    "build_match_embed",
    "build_confirmation_embed",
    "format_entry_composition",
    # Leaderboard
    "build_weekly_leaderboard_embed",
    "build_alltime_leaderboard_embed",
    "build_player_stats_embed",
    "build_weekly_announcement_embed",
]

