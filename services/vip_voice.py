"""Business logic for temporary VIP voice channel access."""

from __future__ import annotations

import discord

from models import vip_voice as vip_repo

VipChannel = discord.VoiceChannel | discord.StageChannel


def build_panel_embed() -> discord.Embed:
    return discord.Embed(
        title="VIP Voice Access",
        description=(
            "Select an occupied VIP voice channel below to request access.\n"
            "The bot will DM the people currently inside so one of them can accept or deny."
        ),
        color=0x8e44ad,
    )


def build_request_embed(requester: discord.abc.User, channel: VipChannel) -> discord.Embed:
    return discord.Embed(
        title="VIP voice request",
        description=f"**{requester.display_name}** wants to join **{channel.name}**.",
        color=0x8e44ad,
    )


def build_error_embed(description: str) -> discord.Embed:
    return discord.Embed(title="VIP voice error", description=description, color=0xff7675)


def build_status_embed(guild_id: int) -> discord.Embed:
    channels = vip_repo.list_vip_channels(guild_id)
    panel = vip_repo.get_vip_panel(guild_id)
    lines = ["Configured VIP channels:"]
    if channels:
        lines.extend(f"<#{item.channel_id}> uses <@&{item.role_id}>" for item in channels)
    else:
        lines.append("none")
    lines.append("")
    lines.append(f"Panel: <#{panel.channel_id}> / `{panel.message_id}`" if panel else "Panel: not posted")
    return discord.Embed(title="VIP Voice Status", description="\n".join(lines), color=0x8e44ad)


async def lock_channel(channel: VipChannel, role: discord.Role) -> None:
    overwrites = channel.overwrites
    everyone = channel.guild.default_role
    everyone_overwrite = overwrites.get(everyone, discord.PermissionOverwrite())
    role_overwrite = overwrites.get(role, discord.PermissionOverwrite())
    everyone_overwrite.connect = False
    role_overwrite.connect = True
    await channel.set_permissions(everyone, overwrite=everyone_overwrite)
    await channel.set_permissions(role, overwrite=role_overwrite)


async def unlock_channel(channel: VipChannel, role: discord.Role) -> None:
    everyone = channel.guild.default_role
    everyone_overwrite = channel.overwrites_for(everyone)
    role_overwrite = channel.overwrites_for(role)
    everyone_overwrite.connect = None
    role_overwrite.connect = None
    await channel.set_permissions(everyone, overwrite=everyone_overwrite if not everyone_overwrite.is_empty() else None)
    await channel.set_permissions(role, overwrite=role_overwrite if not role_overwrite.is_empty() else None)


async def sync_channel_lock(channel: VipChannel, role: discord.Role) -> None:
    if channel.members:
        await lock_channel(channel, role)
    else:
        await unlock_channel(channel, role)


def member_is_in_channel(member: discord.Member, channel_id: int) -> bool:
    return bool(member.voice and member.voice.channel and member.voice.channel.id == channel_id)


async def grant_access(member: discord.Member, role: discord.Role) -> None:
    if role not in member.roles:
        await member.add_roles(role, reason="VIP voice request accepted")


async def revoke_access(member: discord.Member, role: discord.Role) -> None:
    if role in member.roles:
        await member.remove_roles(role, reason="VIP voice access expired after leaving")


async def notify_channel_members(
    request: vip_repo.VipVoiceRequest,
    requester: discord.Member,
    channel: VipChannel,
    view: discord.ui.View,
) -> int:
    sent = 0
    for occupant in list(channel.members):
        if occupant.bot or occupant.id == requester.id:
            continue
        try:
            message = await occupant.send(embed=build_request_embed(requester, channel), view=view)
        except discord.Forbidden:
            continue
        vip_repo.add_notification(request.id, occupant.id, message.id)
        sent += 1
    return sent
