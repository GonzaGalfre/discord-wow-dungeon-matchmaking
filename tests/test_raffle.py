from __future__ import annotations

from datetime import UTC, datetime, timedelta
import asyncio

from models import participation as repo
from services.participation import ParticipationCalculator, ParticipationRules
from services.raffle import RaffleError, draw_raffle
from services.hub_sync import apply_hub_snapshot
from views.raffle_details import RaffleDetailsView


def calc() -> ParticipationCalculator:
    return ParticipationCalculator(
        ParticipationRules(
            first_voice_minutes_per_ticket=15,
            voice_minutes_per_ticket=60,
            messages_per_ticket=10,
            max_voice_tickets=10,
            max_message_tickets=5,
        )
    )


def test_manual_draw_excludes_winner_and_opens_next_period() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    period = repo.create_open_period(123, start)
    assert repo.open_voice_session(123, 5, 100, start)
    repo.close_open_voice_session(123, 5, start + timedelta(hours=2))
    result = draw_raffle(123, start + timedelta(days=14), calc())
    drawn = repo.get_period(period.id)
    assert result.total_tickets == 2
    assert result.participant_count == 1
    assert drawn.status == repo.RAFFLE_DRAWN
    assert drawn.winner_user_id == 5
    assert repo.list_exclusive_winner_ids(123) == [5]
    assert repo.get_current_open_period(123).id != period.id


def test_zero_ticket_users_are_rejected() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    repo.create_open_period(123, start)
    try:
        draw_raffle(123, start + timedelta(days=14), calc())
    except RaffleError as exc:
        assert str(exc) == "no eligible participants have tickets"
    else:
        raise AssertionError("expected no eligible participants error")


def test_exclusive_winner_history_can_be_replaced() -> None:
    assert repo.replace_exclusive_winner_ids(123, [7, 2, 7]) == [2, 7]
    assert repo.list_exclusive_winner_ids(123) == [2, 7]


def test_action_receipt_is_idempotent() -> None:
    repo.save_action_receipt("action-1", 123, "RESET", {"reset": True})
    repo.save_action_receipt("action-1", 123, "DRAW", {"winner_user_id": "7"})
    assert repo.get_action_receipt("action-1") == {"reset": True}


def test_debug_tickets_accumulate_in_open_period_and_draw_snapshot() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    period = repo.create_open_period(123, start)
    assert repo.add_debug_tickets(123, 5, 2, start)[1] == 2
    assert repo.add_debug_tickets(123, 5, 3, start)[1] == 5
    totals = repo.totals_for_period(123, period.starts_at, period.ends_at, start, calc())
    assert [(item.user_id, item.total_tickets) for item in totals] == [(5, 5)]
    result = repo.draw_current_period(123, start + timedelta(days=1), calc())
    assert result["total_tickets"] == 5
    assert repo.list_raffle_entry_snapshots(period.id) == [{"user_id": 5, "total_tickets": 5}]
    assert repo.list_debug_tickets(result["next_period_id"]) == {}


def test_hub_reset_action_writes_receipt_and_is_idempotent() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = repo.create_open_period(123, start)
    snapshot = {"participation_raffle": {"actions": [{"action_id": "reset-1", "type": "RESET", "guild_id": "123"}]}}
    asyncio.run(apply_hub_snapshot(object(), snapshot))
    assert repo.get_action_receipt("reset-1") == {"reset": True}
    assert repo.get_period(old.id).status == repo.RAFFLE_CLOSED
    current = repo.get_current_open_period(123)
    asyncio.run(apply_hub_snapshot(object(), snapshot))
    assert repo.get_current_open_period(123).id == current.id


def test_hub_add_debug_tickets_action_is_idempotent() -> None:
    snapshot = {"participation_raffle": {"actions": [{"action_id": "debug-1", "type": "ADD_DEBUG_TICKETS", "guild_id": "123", "user_id": "5", "tickets": 3}]}}
    asyncio.run(apply_hub_snapshot(object(), snapshot))
    assert repo.get_action_receipt("debug-1")["tickets"] == 3
    asyncio.run(apply_hub_snapshot(object(), snapshot))
    assert repo.list_debug_tickets(repo.get_current_open_period(123).id) == {5: 3}


def test_raffle_details_view_uses_a_period_specific_persistent_id() -> None:
    async def exercise() -> None:
        view = RaffleDetailsView(42)
        assert view.timeout is None
        assert view.children[0].custom_id == "raffle_details:42"

    asyncio.run(exercise())
