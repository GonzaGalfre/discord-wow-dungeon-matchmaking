"""Participation calculation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ParticipationRules:
    first_voice_minutes_per_ticket: int
    voice_minutes_per_ticket: int
    messages_per_ticket: int
    max_voice_tickets: int
    max_message_tickets: int


@dataclass(frozen=True, slots=True)
class ParticipationTotals:
    user_id: int
    voice_seconds: int
    message_count: int
    voice_tickets: int
    message_tickets: int
    debug_tickets: int = 0

    @property
    def total_tickets(self) -> int:
        return self.voice_tickets + self.message_tickets + self.debug_tickets


@dataclass(frozen=True, slots=True)
class VoiceInterval:
    user_id: int
    started_at: datetime
    ended_at: datetime | None


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ParticipationCalculator:
    def __init__(self, rules: ParticipationRules) -> None:
        self.rules = rules

    def ticket_totals(self, user_id: int, voice_seconds: int, message_count: int) -> ParticipationTotals:
        first_voice_threshold = self.rules.first_voice_minutes_per_ticket * 60
        voice_interval = self.rules.voice_minutes_per_ticket * 60
        if first_voice_threshold <= 0 or voice_interval <= 0 or voice_seconds < first_voice_threshold:
            voice_tickets = 0
        else:
            voice_tickets = 1 + ((voice_seconds - first_voice_threshold) // voice_interval)
        return ParticipationTotals(
            user_id=user_id,
            voice_seconds=voice_seconds,
            message_count=message_count,
            voice_tickets=min(voice_tickets, self.rules.max_voice_tickets),
            message_tickets=0,
        )

    def overlapping_seconds(
        self,
        interval: VoiceInterval,
        period_start: datetime,
        period_end: datetime,
        now: datetime,
    ) -> int:
        started_at = ensure_utc(interval.started_at)
        ended_at = ensure_utc(interval.ended_at or now)
        period_start = ensure_utc(period_start)
        period_end = ensure_utc(period_end)
        if ended_at < started_at:
            return 0
        overlap_start = max(started_at, period_start)
        overlap_end = min(ended_at, period_end)
        if overlap_end <= overlap_start:
            return 0
        return int((overlap_end - overlap_start).total_seconds())


def format_duration(seconds: int) -> str:
    seconds = max(0, seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_period(starts_at: datetime, ends_at: datetime) -> str:
    return f"{starts_at:%Y-%m-%d %H:%M UTC} to {ends_at:%Y-%m-%d %H:%M UTC}"


def participation_line(total: ParticipationTotals) -> str:
    return (
        f"<@{total.user_id}>: {format_duration(total.voice_seconds)}, "
        f"{total.message_count} messages, {total.total_tickets} tickets"
    )
