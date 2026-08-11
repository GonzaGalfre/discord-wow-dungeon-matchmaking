"""Weighted raffle drawing based on participation totals."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from models import participation as participation_repo
from services.participation import ParticipationCalculator, ParticipationTotals


class RaffleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DrawResult:
    period_id: int
    winner_user_id: int
    winner_tickets: int
    total_tickets: int
    winning_number: int
    participant_count: int


def build_snapshots(totals: list[ParticipationTotals]) -> tuple[list[dict], int]:
    cumulative = 0
    snapshots: list[dict] = []
    for total in sorted((item for item in totals if item.total_tickets > 0), key=lambda item: item.user_id):
        start = cumulative + 1
        cumulative += total.total_tickets
        snapshots.append(
            {
                "user_id": total.user_id,
                "voice_seconds": total.voice_seconds,
                "message_count": total.message_count,
                "voice_tickets": total.voice_tickets,
                "message_tickets": total.message_tickets,
                "total_tickets": total.total_tickets,
                "cumulative_ticket_start": start,
                "cumulative_ticket_end": cumulative,
            }
        )
    return snapshots, cumulative


def draw_raffle(guild_id: int, now: datetime, calculator: ParticipationCalculator) -> DrawResult:
    try:
        result = participation_repo.draw_current_period(guild_id, now, calculator)
    except ValueError as exc:
        raise RaffleError(str(exc)) from exc
    return DrawResult(**{key: result[key] for key in DrawResult.__dataclass_fields__})
