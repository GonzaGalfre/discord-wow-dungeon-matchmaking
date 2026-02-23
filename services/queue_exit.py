"""
Shared queue-exit helpers.
"""

from typing import Dict, Optional

import discord

from models.queue import queue_manager
from services.queue_status import refresh_lfg_setup_message


async def _try_delete_match_message(
    client: discord.Client,
    channel_id: Optional[int],
    message_id: Optional[int],
) -> None:
    if not channel_id or not message_id:
        return

    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            return

    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
        return


async def leave_queue_entry(
    client: discord.Client,
    guild_id: int,
    user_id: int,
    *,
    fallback_channel: Optional[discord.abc.Messageable] = None,
) -> Dict[str, object]:
    """
    Remove one queue entry and cleanup related match message state when needed.
    """
    entry = queue_manager.get(guild_id, user_id)
    if entry is None:
        return {"removed": False, "was_group": False, "had_active_match": False}

    was_group = entry.get("composition") is not None
    match_message_id = entry.get("match_message_id")
    match_channel_id = entry.get("match_channel_id")
    had_active_match = match_message_id is not None

    removed = queue_manager.remove(guild_id, user_id)
    if not removed:
        return {"removed": False, "was_group": was_group, "had_active_match": had_active_match}

    await refresh_lfg_setup_message(client, guild_id, fallback_channel)

    if had_active_match:
        users_still_in_match = []
        for uid, data in queue_manager.items(guild_id):
            if data.get("match_message_id") == match_message_id:
                users_still_in_match.append(uid)

        if len(users_still_in_match) < 2:
            for uid in users_still_in_match:
                queue_manager.clear_match_message(guild_id, uid)
            await _try_delete_match_message(client, match_channel_id, match_message_id)

    return {
        "removed": True,
        "was_group": was_group,
        "had_active_match": had_active_match,
    }
