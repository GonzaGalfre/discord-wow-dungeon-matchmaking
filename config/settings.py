"""Configuration settings for WipyBot."""

import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Dashboard settings (admin-only web view)
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

# Optional raid-report-hub integration.
HUB_API_BASE_URL = os.getenv("HUB_API_BASE_URL", "").rstrip("/")
HUB_API_SECRET = os.getenv("HUB_API_SECRET", os.getenv("APP_API_SECRET", ""))
HUB_SYNC_INTERVAL_SECONDS = int(os.getenv("HUB_SYNC_INTERVAL_SECONDS", "15"))

# =============================================================================
# VOICE MOVE BEHAVIOR
# =============================================================================

VOICE_MOVE_BATCH_SIZE = 5
VOICE_MOVE_BATCH_DELAY_SECONDS = 1.0
