"""
Configuration settings for the WoW Mythic+ LFG Bot.

This module contains all configuration constants and environment variables.
Keep all bot configuration centralized here.

Note: Channel IDs are now stored per-guild in the database.
Use models.guild_settings to get/set guild-specific channels.
"""

import os
from dotenv import load_dotenv

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================

# Load environment variables from .env file
load_dotenv()

# Discord bot token - NEVER hardcode this!
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Dashboard settings (admin-only web view)
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

# =============================================================================
# ROLE DEFINITIONS
# =============================================================================

# Dictionary mapping role keys to display information
# This makes it easy to add/modify roles in one place
ROLES = {
    "tank": {"name": "Tanque", "emoji": "🛡️"},
    "healer": {"name": "Sanador", "emoji": "💚"},
    "dps": {"name": "DPS", "emoji": "⚔️"},
}

# =============================================================================
# KEY LEVEL CONFIGURATION
# =============================================================================

# Mythic+ key level range
# Keys typically go from +2 to +20+ for most players
MIN_KEY_LEVEL = 2
MAX_KEY_LEVEL = 20

# =============================================================================
# PARTY COMPOSITION
# =============================================================================

# Maximum players per role in a Mythic+ group
# Standard composition: 1 Tank, 1 Healer, 3 DPS = 5 total
PARTY_COMPOSITION = {
    "tank": 1,
    "healer": 1,
    "dps": 3,
}
