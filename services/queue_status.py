"""
Helpers to keep the public LFG setup message in sync with queue state.
"""

from typing import Optional

import discord

from models.guild_settings import get_guild_settings
from services.embeds import build_lfg_setup_embed


async def refresh_lfg_setup_message(
    client: discord.Client,
    guild_id: int,
    fallback_channel: Optional[discord.abc.Messageable] = None,
) -> None:
    """
    Edit the persistent LFG setup message with fresh queue counters.

    If the configured message or channel cannot be found, this function exits
    quietly to avoid interrupting user interactions.
    """
    settings = get_guild_settings(guild_id)
    if not settings:
        return

    channel_id = settings.get("lfg_channel_id")
    message_id = settings.get("lfg_message_id")
    if not channel_id or not message_id:
        return

    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            channel = None

    if channel is None and fallback_channel is not None:
        channel = fallback_channel

    if channel is None:
        return

    try:
        message = await channel.fetch_message(message_id)
        await message.edit(embed=build_lfg_setup_embed(guild_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return
