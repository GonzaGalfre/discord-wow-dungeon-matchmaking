"""
Voice move service for the WoW Mythic+ LFG Bot.

Core business logic for moving members between voice channels.
Imported by both the /move slash command and the move panel UI view
so the logic lives in exactly one place.
"""

import asyncio

import discord

from config.settings import VOICE_MOVE_BATCH_DELAY_SECONDS, VOICE_MOVE_BATCH_SIZE

MoveChannel = discord.VoiceChannel | discord.StageChannel


async def move_member_async(member: discord.Member, destination: MoveChannel) -> bool:
    """
    Move a single member to a voice channel.

    Returns True if the move was attempted (member was in a different channel),
    False if the member was already in the destination or not in any channel.
    """
    if member.voice is None or member.voice.channel is None:
        return False
    if member.voice.channel.id == destination.id:
        return False
    await member.move_to(destination)
    return True


async def move_all_members(
    source: MoveChannel,
    destination: MoveChannel,
    batch_size: int = VOICE_MOVE_BATCH_SIZE,
    batch_delay_seconds: float = VOICE_MOVE_BATCH_DELAY_SECONDS,
) -> int:
    """
    Move all members from source to destination in throttled batches.

    Snapshots the member list before issuing requests so members that leave
    mid-operation are not re-processed.

    Returns the number of members successfully moved.
    """
    members = list(source.members)
    if not members:
        return 0

    safe_batch_size = max(1, batch_size)
    safe_batch_delay = max(0.0, batch_delay_seconds)
    moved_count = 0

    for index in range(0, len(members), safe_batch_size):
        batch = members[index : index + safe_batch_size]
        results = await asyncio.gather(
            *[move_member_async(member, destination) for member in batch],
            return_exceptions=True,
        )

        for result in results:
            if result is True:
                moved_count += 1
            elif isinstance(result, discord.Forbidden):
                raise result

        has_more_batches = index + safe_batch_size < len(members)
        if has_more_batches and safe_batch_delay > 0:
            await asyncio.sleep(safe_batch_delay)

    return moved_count


def build_move_embed(
    nb_moved: int,
    source: MoveChannel,
    destination: MoveChannel,
) -> discord.Embed:
    """
    Build the result embed for a move operation.
    """
    if nb_moved == 0:
        return discord.Embed(
            title="Sin cambios",
            description="Ningún miembro fue movido.",
            color=0xffeaa7,
        )
    word = "miembro" if nb_moved == 1 else "miembros"
    verb = "fue movido" if nb_moved == 1 else "fueron movidos"
    return discord.Embed(
        title="Listo",
        description=f"**{nb_moved}** {word} {verb} de {source.mention} a {destination.mention}.",
        color=0x55efc4,
    )


def build_error_embed(description: str) -> discord.Embed:
    """Build a standard error embed."""
    return discord.Embed(title="Error", description=description, color=0xff7675)
