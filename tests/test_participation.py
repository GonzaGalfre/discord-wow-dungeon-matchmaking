from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.participation import ParticipationCalculator, ParticipationRules, VoiceInterval


def calculator() -> ParticipationCalculator:
    return ParticipationCalculator(
        ParticipationRules(
            first_voice_minutes_per_ticket=15,
            voice_minutes_per_ticket=60,
            messages_per_ticket=10,
            max_voice_tickets=3,
            max_message_tickets=2,
        )
    )


def test_ticket_thresholds_and_caps() -> None:
    calc = calculator()
    assert calc.ticket_totals(1, 899, 100).total_tickets == 0
    assert calc.ticket_totals(1, 900, 100).total_tickets == 1
    assert calc.ticket_totals(1, 3600, 100).total_tickets == 1
    assert calc.ticket_totals(1, 4500, 100).total_tickets == 2
    totals = calc.ticket_totals(1, 3600 * 10, 100)
    assert totals.voice_tickets == 3
    assert totals.message_tickets == 0


def test_voice_overlap_boundaries() -> None:
    calc = calculator()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=14)
    assert calc.overlapping_seconds(VoiceInterval(1, start - timedelta(hours=1), start + timedelta(hours=1)), start, end, end) == 3600
    assert calc.overlapping_seconds(VoiceInterval(1, end - timedelta(hours=1), end + timedelta(hours=1)), start, end, end) == 3600
    assert calc.overlapping_seconds(VoiceInterval(1, start - timedelta(hours=1), end + timedelta(hours=1)), start, end, end) == int((end - start).total_seconds())
    assert calc.overlapping_seconds(VoiceInterval(1, end, end + timedelta(minutes=1)), start, end, end) == 0


def test_open_voice_session_uses_now() -> None:
    calc = calculator()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    now = start + timedelta(minutes=90)
    assert calc.overlapping_seconds(VoiceInterval(1, start, None), start, start + timedelta(days=1), now) == 5400
