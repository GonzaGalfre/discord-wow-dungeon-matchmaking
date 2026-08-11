"""Raid signup embed rendering and message refresh helpers."""

from __future__ import annotations

from collections import defaultdict

import discord

from config.emoji_overrides import STATUS_EMOJIS as STATUS_EMOJI_OVERRIDES
from models.raid_signup import get_raid_event, list_raid_signups
from services.raid_catalog import (
    CLASSES,
    ROLE_EMOJIS,
    ROLE_HEALER,
    ROLE_LABELS,
    ROLE_MELEE,
    ROLE_RANGED,
    ROLE_TANK,
    class_emoji,
    format_spec_icon_or_name,
    signup_role,
)

STATUS_ATTENDING = "attending"
STATUS_BENCH = "bench"
STATUS_LATE = "late"
STATUS_TENTATIVE = "tentative"
STATUS_ABSENCE = "absence"

STATUS_LABELS = {
    STATUS_ATTENDING: "Going",
    STATUS_BENCH: "Bench",
    STATUS_LATE: "Late",
    STATUS_TENTATIVE: "Tentative",
    STATUS_ABSENCE: "Absence",
}

STATUS_EMOJIS = {
    STATUS_ATTENDING: "✅",
    STATUS_BENCH: "🪑",
    STATUS_LATE: "🕘",
    STATUS_TENTATIVE: "⚖️",
    STATUS_ABSENCE: "🚫",
}


def status_emoji(status: str) -> str:
    return STATUS_EMOJI_OVERRIDES.get(status) or STATUS_EMOJIS[status]


def _spaced_title(title: str) -> str:
    words = [" ".join(word.upper()) for word in title.split()]
    return "   ".join(words)


def _display_name(signup: dict) -> str:
    return signup.get("display_name") or f"User {signup['user_id']}"


def _format_signup(signup: dict, guild: discord.Guild | None = None) -> str:
    spec_marker = format_spec_icon_or_name(
        signup.get("class_key"),
        signup.get("spec_key"),
        guild,
    )
    return f"{spec_marker} **{_display_name(signup)}**"


def _role_count(signups: list[dict], role: str) -> int:
    return sum(
        1
        for signup in signups
        if signup["status"] == STATUS_ATTENDING
        and signup_role(signup.get("class_key"), signup.get("spec_key")) == role
    )


def _status_line(signups: list[dict], status: str) -> str:
    entries = [signup for signup in signups if signup["status"] == status]
    if not entries:
        return f"{status_emoji(status)} {STATUS_LABELS[status]} (0): -"
    names = ", ".join(f"**{_display_name(signup)}**" for signup in entries)
    return f"{status_emoji(status)} {STATUS_LABELS[status]} ({len(entries)}): {names}"


def _custom_emoji(name: str, guild: discord.Guild | None = None) -> str | None:
    if guild is None:
        return None
    emoji = discord.utils.get(guild.emojis, name=name)
    return str(emoji) if emoji is not None else None


def _role_summary_values(signups: list[dict]) -> list[str]:
    healer_emoji = "✝️"
    dps_count = _role_count(signups, ROLE_RANGED) + _role_count(signups, ROLE_MELEE)
    return [
        f"{ROLE_EMOJIS[ROLE_TANK]} **{ROLE_LABELS[ROLE_TANK]} {_role_count(signups, ROLE_TANK)}**",
        f"🐒 **DPS {dps_count}**",
        f"{healer_emoji} **{ROLE_LABELS[ROLE_HEALER]} {_role_count(signups, ROLE_HEALER)}**",
    ]


def _add_role_summary_fields(embed: discord.Embed, signups: list[dict]) -> None:
    """Add counters as a fixed three-column row above class blocks."""
    for value in _role_summary_values(signups):
        embed.add_field(name="\u200b", value=value, inline=True)


def _add_class_columns(
    embed: discord.Embed,
    grouped: dict[str, list[dict]],
    guild: discord.Guild | None = None,
) -> None:
    """Render class blocks into fixed columns instead of Discord's flowing fields."""
    blocks: list[str] = []
    for class_key, class_data in CLASSES.items():
        class_signups = grouped.get(class_key, [])
        if not class_signups:
            continue

        lines = [_format_signup(signup, guild) for signup in class_signups]
        block = "\n".join(
            [
                f"{class_emoji(class_key, guild)} __*{class_data['name']} ({len(class_signups)})*__",
                *lines,
            ]
        )
        blocks.append(block)

    if not blocks:
        return

    columns = [[], [], []]
    column_heights = [0, 0, 0]
    for block in blocks:
        target = column_heights.index(min(column_heights))
        columns[target].append(block)
        column_heights[target] += block.count("\n") + 2

    for column in columns:
        value = "\n\n".join(column) if column else "\u200b"
        embed.add_field(name="\u200b", value=value[:1024], inline=True)


def build_raid_signup_embed(
    event: dict,
    signups: list[dict] | None = None,
    guild: discord.Guild | None = None,
) -> discord.Embed:
    """Build the dynamic signup status embed."""
    signups = signups if signups is not None else list_raid_signups(event["id"])
    attending = [signup for signup in signups if signup["status"] == STATUS_ATTENDING]
    color = 0xC8F000 if event.get("is_open", 1) else 0x6B7280

    header = [
        f"**{_spaced_title(event['title'])}**",
        "",
        f"🎌 {event.get('leader_name') or 'Raid Lead'}",
        f"🗓️ {event['starts_at']}",
        f"👥 {len(attending)} signed (+{len(signups) - len(attending)} other responses)",
    ]

    embed = discord.Embed(description="\n".join(header), color=color)
    _add_role_summary_fields(embed, signups)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for signup in attending:
        grouped[signup.get("class_key") or "unknown"].append(signup)

    _add_class_columns(embed, grouped, guild)

    bench_late = [
        _status_line(signups, STATUS_LATE),
        _status_line(signups, STATUS_BENCH),
        _status_line(signups, STATUS_TENTATIVE),
        _status_line(signups, STATUS_ABSENCE),
    ]
    embed.add_field(name="Other Responses", value="\n".join(bench_late), inline=False)
    footer_action = (
        "Event closed. Signups are no longer editable."
        if not event.get("is_open", 1)
        else "Select class/spec to sign up. Use buttons to change attendance status."
    )
    embed.set_footer(text=f"Raid event ID: {event['id']} | {footer_action}")
    return embed


async def refresh_raid_signup_message(client: discord.Client, event_id: int) -> None:
    """Fetch and edit the Discord signup message for an event."""
    event = get_raid_event(event_id)
    if not event or not event.get("message_id"):
        return

    channel = client.get_channel(event["channel_id"])
    if channel is None:
        try:
            channel = await client.fetch_channel(event["channel_id"])
        except (discord.NotFound, discord.Forbidden):
            return

    try:
        message = await channel.fetch_message(event["message_id"])
    except (discord.NotFound, discord.Forbidden):
        return

    if event.get("is_open", 1):
        from views.raid_signup import RaidSignupView

        await message.edit(
            content=None,
            embed=build_raid_signup_embed(event, guild=message.guild),
            view=RaidSignupView(),
        )
        return

    await message.edit(
        content="**Event closed**",
        embed=build_raid_signup_embed(event, guild=message.guild),
        view=None,
    )
