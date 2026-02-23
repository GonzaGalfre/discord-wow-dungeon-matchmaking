"""
Process-wide runtime references shared across bot and dashboard.
"""

from typing import Optional

import discord

_bot_client: Optional[discord.Client] = None


def set_bot_client(client: discord.Client) -> None:
    global _bot_client
    _bot_client = client


def get_bot_client() -> Optional[discord.Client]:
    return _bot_client
