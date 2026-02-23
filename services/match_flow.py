"""
Shared async matchmaking trigger + notification helpers.
"""

import asyncio
from typing import Dict, List, Optional

import discord

from event_logger import log_event
from models.guild_settings import get_match_channel_id
from models.queue import queue_manager
from services.embeds import build_match_embed
from services.matchmaking import get_users_with_overlap


async def delete_old_match_messages(client: discord.Client, guild_id: int, user_ids: List[int]) -> None:
    """
    Delete previous match messages for these users and clear pointers.
    """
    messages_to_delete = {}

    for uid in user_ids:
        match_info = queue_manager.get_match_message(guild_id, uid)
        if match_info:
            message_id, channel_id = match_info
            messages_to_delete[(channel_id, message_id)] = True
            queue_manager.clear_match_message(guild_id, uid)

    for (channel_id, message_id) in messages_to_delete.keys():
        try:
            channel = client.get_channel(channel_id)
            if channel:
                message = await channel.fetch_message(message_id)
                await message.delete()
                log_event(
                    "match_message_deleted_for_refresh",
                    guild_id=guild_id,
                    channel_id=channel_id,
                    message_id=message_id,
                    affected_user_ids=user_ids,
                )
        except (discord.errors.NotFound, discord.errors.Forbidden):
            pass
        except Exception as exc:
            print(f"⚠️ Error deleting old match message: {exc}")


def _format_mentions(guild_id: int, user_ids: List[int], mention_fake_users: bool) -> str:
    parts = []
    for uid in user_ids:
        if mention_fake_users and uid > 900000000000000000:
            entry = queue_manager.get(guild_id, uid)
            if entry:
                parts.append(f"`{entry['username']}`")
                continue
        parts.append(f"<@{uid}>")
    return " ".join(parts)


async def trigger_matchmaking_for_entry(
    client: discord.Client,
    guild_id: int,
    new_user_id: int,
    key_min: int,
    key_max: int,
    *,
    source: str,
    fallback_channel: Optional[discord.abc.Messageable] = None,
    triggered_by_user_id: Optional[int] = None,
    mention_fake_users: bool = False,
    message_prefix: str = "",
) -> Dict[str, object]:
    """
    Try to match queue entry and create/update match notification if needed.
    """
    matches = get_users_with_overlap(guild_id, key_min, key_max, new_user_id)
    if len(matches) <= 1:
        return {"matched": False, "matches": matches, "user_count": len(matches)}

    joining_existing = False
    for entry in matches:
        if entry["user_id"] == new_user_id:
            continue
        queued = queue_manager.get(guild_id, entry["user_id"])
        if queued and queued.get("match_message_id") is not None:
            joining_existing = True
            break

    match_channel_id = get_match_channel_id(guild_id)
    match_channel = client.get_channel(match_channel_id) if match_channel_id else None
    if not match_channel:
        match_channel = fallback_channel
    if not match_channel:
        return {
            "matched": False,
            "matches": matches,
            "user_count": len(matches),
            "error": "No channel available for match notifications.",
        }

    matched_user_ids = [u["user_id"] for u in matches]
    await delete_old_match_messages(client, guild_id, matched_user_ids)

    # Avoid circular import at module import time.
    from views.party import PartyCompleteView

    mentions = _format_mentions(guild_id, matched_user_ids, mention_fake_users)
    content = f"{message_prefix}{mentions}".strip()
    match_message = await match_channel.send(
        content=content,
        embed=build_match_embed(matches),
        view=PartyCompleteView(guild_id, matched_user_ids),
    )
    log_event(
        "match_message_created",
        guild_id=guild_id,
        channel_id=match_channel.id,
        message_id=match_message.id,
        matched_user_ids=matched_user_ids,
        triggered_by_user_id=triggered_by_user_id,
        source=source,
    )

    for uid in matched_user_ids:
        queue_manager.set_match_message(guild_id, uid, match_message.id, match_channel.id)

    return {
        "matched": True,
        "matches": matches,
        "user_count": len(matches),
        "joining_existing": joining_existing,
        "match_message_id": match_message.id,
        "match_channel_id": match_channel.id,
    }


async def trigger_matchmaking_for_entry_threadsafe(
    client: discord.Client,
    guild_id: int,
    new_user_id: int,
    key_min: int,
    key_max: int,
    *,
    source: str,
    fallback_channel: Optional[discord.abc.Messageable] = None,
    triggered_by_user_id: Optional[int] = None,
    mention_fake_users: bool = False,
    message_prefix: str = "",
) -> Dict[str, object]:
    """
    Run matchmaking trigger on the bot's loop when called from another loop/thread.
    """
    bot_loop = client.loop
    current_loop = asyncio.get_running_loop()

    if bot_loop is current_loop:
        return await trigger_matchmaking_for_entry(
            client,
            guild_id,
            new_user_id,
            key_min,
            key_max,
            source=source,
            fallback_channel=fallback_channel,
            triggered_by_user_id=triggered_by_user_id,
            mention_fake_users=mention_fake_users,
            message_prefix=message_prefix,
        )

    future = asyncio.run_coroutine_threadsafe(
        trigger_matchmaking_for_entry(
            client,
            guild_id,
            new_user_id,
            key_min,
            key_max,
            source=source,
            fallback_channel=fallback_channel,
            triggered_by_user_id=triggered_by_user_id,
            mention_fake_users=mention_fake_users,
            message_prefix=message_prefix,
        ),
        bot_loop,
    )
    return await asyncio.wrap_future(future)
