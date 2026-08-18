"""Participation panel rendering helpers."""

from __future__ import annotations

from datetime import datetime

import discord

from models import participation as participation_repo
from services.participation import (
    ParticipationCalculator,
    ParticipationRules,
    format_duration,
    format_period,
    participation_line,
)


def calculator_for_settings(settings) -> ParticipationCalculator:
    return ParticipationCalculator(
        ParticipationRules(
            first_voice_minutes_per_ticket=settings.first_voice_minutes_per_ticket,
            voice_minutes_per_ticket=settings.voice_minutes_per_ticket,
            messages_per_ticket=10,
            max_voice_tickets=settings.max_voice_tickets,
            max_message_tickets=0,
        )
    )


def current_totals(settings, now: datetime | None = None):
    now = now or participation_repo.utc_now()
    period = participation_repo.ensure_open_period(settings.guild_id, now)
    totals = participation_repo.totals_for_period(settings.guild_id, period.starts_at, period.ends_at, now, calculator_for_settings(settings))
    return period, totals


def user_progress_text(settings, user_id: int) -> str:
    period, totals = current_totals(settings)
    total = next((item for item in totals if item.user_id == user_id), None)
    if total is None:
        total = calculator_for_settings(settings).ticket_totals(user_id, 0, 0)
    return "\n".join(
        [
            f"Period: {format_period(period.starts_at, period.ends_at)}",
            f"Voice: {format_duration(total.voice_seconds)}",
            f"Voice tickets: {total.voice_tickets}",
            f"Total tickets: {total.total_tickets}",
        ]
    )


def leaderboard_text(settings) -> str:
    period, totals = current_totals(settings)
    ordered = sorted(
        (item for item in totals if item.total_tickets > 0),
        key=lambda item: (-item.total_tickets, -item.voice_seconds, -item.message_count, item.user_id),
    )
    body = "\n".join(participation_line(total) for total in ordered) or "No participation yet."
    return f"Period: {format_period(period.starts_at, period.ends_at)}\n{body}"


def message_chunks(text: str, limit: int = 2000) -> list[str]:
    """Split line-based content without losing entries to Discord's message limit."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        if current and len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks or ["No participation yet."]


def rules_text(settings) -> str:
    eligible_roles = ", ".join(f"<@&{item}>" for item in sorted(settings.eligible_role_ids)) or "none"
    voice_channels = ", ".join(f"<#{item}>" for item in sorted(settings.tracked_voice_channel_ids)) or "none"
    return "\n".join(
        [
            f"Eligible roles: {eligible_roles}",
            f"Tracked voice: {voice_channels}",
            f"Voice: first ticket at {settings.first_voice_minutes_per_ticket} minutes, then 1 ticket per {settings.voice_minutes_per_ticket} minutes, max {settings.max_voice_tickets}",
            "Raffle: officers draw manually; winners remain excluded until history is edited.",
        ]
    )


def build_panel_embed(settings) -> discord.Embed:
    period, totals = current_totals(settings)
    ordered = sorted(
        (item for item in totals if item.total_tickets > 0),
        key=lambda item: (-item.total_tickets, -item.voice_seconds, -item.message_count, item.user_id),
    )
    lines = [
        f"{index}. <@{total.user_id}> - {total.total_tickets} tickets ({format_duration(total.voice_seconds)})"
        for index, total in enumerate(ordered, start=1)
    ]


    embed = discord.Embed(
        title="Participation Overview",
        description=f"Current period: {format_period(period.starts_at, period.ends_at)}",
        color=0x55EFC4,
    )
    if not lines:
        embed.add_field(name="Participation", value="No ticket holders yet.", inline=False)
    else:
        line_offset = 0
        for chunk in message_chunks("\n".join(lines), limit=1024):
            count = len(chunk.splitlines())
            embed.add_field(
                name=f"Participation ({line_offset + 1}-{line_offset + count})",
                value=chunk,
                inline=False,
            )
            line_offset += count
    embed.add_field(name="Raffle", value="Manual draw by officers", inline=True)
    embed.add_field(name="Panel refresh", value=f"Every {settings.panel_update_minutes} min", inline=True)
    embed.set_footer(text="Use the buttons below for personal progress, rules, and a detailed leaderboard.")
    return embed
