"""
Configuration module for the WoW Mythic+ LFG Bot.

This module contains all configuration constants and environment variables.

Note: Channel IDs are now stored per-guild in the database.
Use models.guild_settings to get/set guild-specific channels.
"""

from config.settings import (
    # Environment variables
    DISCORD_TOKEN,
    DASHBOARD_PASSWORD,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    # Constants
    ROLES,
    MIN_KEY_LEVEL,
    MAX_KEY_LEVEL,
    PARTY_COMPOSITION,
)

__all__ = [
    "DISCORD_TOKEN",
    "DASHBOARD_PASSWORD",
    "DASHBOARD_HOST",
    "DASHBOARD_PORT",
    "ROLES",
    "MIN_KEY_LEVEL",
    "MAX_KEY_LEVEL",
    "PARTY_COMPOSITION",
]
