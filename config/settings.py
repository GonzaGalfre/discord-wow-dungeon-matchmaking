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

# Queue can also represent Mythic 0 as level 0.
M0_KEY_LEVEL = 0

# Preset key brackets used in queue flow.
KEY_BRACKETS = {
    "0": {"label": "0", "min": 0, "max": 0},
    "2-5": {"label": "2-5", "min": 2, "max": 5},
    "6-9": {"label": "6-9", "min": 6, "max": 9},
    "10+": {"label": "10+", "min": 10, "max": MAX_KEY_LEVEL},
    "anything": {"label": "Anything", "min": 0, "max": MAX_KEY_LEVEL},
}

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

# =============================================================================
# QUEUE ENGAGEMENT
# =============================================================================

# After this many seconds waiting (without active match), ask via DM if user
# still wants to remain in queue.
QUEUE_STAY_PROMPT_AFTER_SECONDS = 180

# How long we wait for DM response before auto-removing from queue.
QUEUE_STAY_RESPONSE_TIMEOUT_SECONDS = 90
