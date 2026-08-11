from __future__ import annotations

from datetime import UTC, datetime, timedelta

from models import participation as repo
from services.participation import ParticipationCalculator, ParticipationRules
from services.attendance import AttendanceService, VoiceTransition
from tests.conftest import Member, Role


def configured_settings():
    repo.update_participation_roles(123, [10], [20])
    repo.add_tracked_voice_channel(123, 100)
    repo.add_tracked_voice_channel(123, 200)
    return repo.get_or_create_participation_settings(123)


def test_voice_transitions_and_idempotency() -> None:
    settings = configured_settings()
    member = Member(id=1, bot=False, roles=[Role(10)])
    service = AttendanceService(settings)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)

    service.handle_transition(VoiceTransition(123, member, None, 100, t0))
    service.handle_transition(VoiceTransition(123, member, None, 100, t0))
    service.handle_transition(VoiceTransition(123, member, 100, 200, t0 + timedelta(minutes=10)))
    open_session = repo.get_open_voice_session(123, 1)
    assert open_session is not None
    assert open_session.channel_id == 200
    assert open_session.started_at == t0

    service.handle_transition(VoiceTransition(123, member, 200, None, t0 + timedelta(hours=1)))
    service.handle_transition(VoiceTransition(123, member, 200, None, t0 + timedelta(hours=1)))
    rows = repo.voice_intervals_for_period(123, t0 - timedelta(minutes=1), t0 + timedelta(hours=2))
    closed = repo.get_voice_session(1)
    assert len(rows) == 1
    assert closed.duration_seconds == 3600


def test_mute_only_transition_is_ignored() -> None:
    settings = configured_settings()
    member = Member(id=1, bot=False, roles=[Role(10)])
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    AttendanceService(settings).handle_transition(VoiceTransition(123, member, 100, 100, t0))
    assert repo.get_open_voice_session(123, 1) is None


def test_officer_role_is_eligible_for_voice_tracking() -> None:
    settings = configured_settings()
    officer = Member(id=2, bot=False, roles=[Role(20)])
    t0 = datetime(2026, 1, 1, tzinfo=UTC)

    AttendanceService(settings).handle_transition(VoiceTransition(123, officer, None, 100, t0))

    assert repo.get_open_voice_session(123, officer.id) is not None


def test_negative_duration_is_clamped() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    assert repo.open_voice_session(123, 1, 100, t0)
    closed = repo.close_open_voice_session(123, 1, t0 - timedelta(minutes=5))
    assert closed is not None
    assert closed.duration_seconds == 0


def test_voice_time_accumulates_across_rejoins_in_same_period() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    calc = ParticipationCalculator(
        ParticipationRules(
            first_voice_minutes_per_ticket=15,
            voice_minutes_per_ticket=60,
            messages_per_ticket=10,
            max_voice_tickets=10,
            max_message_tickets=0,
        )
    )
    assert repo.open_voice_session(123, 7, 100, start)
    repo.close_open_voice_session(123, 7, start + timedelta(minutes=55))
    assert repo.open_voice_session(123, 7, 100, start + timedelta(minutes=65))
    totals = repo.totals_for_period(123, start, start + timedelta(days=14), start + timedelta(minutes=70), calc)
    user_total = next(item for item in totals if item.user_id == 7)
    assert user_total.voice_seconds == 60 * 60
    assert user_total.voice_tickets == 1


def test_panel_settings_are_persisted() -> None:
    repo.update_participation_roles(123, [10], [20])
    settings = repo.update_participation_panel(123, 555, 777)
    assert settings.panel_channel_id == 555
    assert settings.panel_message_id == 777
    assert settings.panel_last_updated_at is not None
    settings = repo.update_participation_panel_interval(123, 15)
    assert settings.panel_update_minutes == 15
    settings = repo.clear_participation_panel(123)
    assert settings.panel_channel_id is None
    assert settings.panel_message_id is None


def test_leaderboard_snapshot_exports_current_period_totals() -> None:
    settings = configured_settings()
    started_at = repo.utc_now() - timedelta(minutes=20)
    repo.ensure_open_period(settings.guild_id, started_at)
    assert repo.open_voice_session(settings.guild_id, 7, 100, started_at)

    leaderboards = repo.export_participation_leaderboards_snapshot()

    assert len(leaderboards) == 1
    entry = leaderboards[0]["entries"][0]
    assert leaderboards[0]["guild_id"] == "123"
    assert entry["user_id"] == "7"
    assert entry["voice_tickets"] == 1
    assert entry["total_tickets"] == 1


def test_live_voice_snapshot_includes_next_ticket_progress() -> None:
    settings = configured_settings()
    started_at = repo.utc_now() - timedelta(minutes=20)
    repo.ensure_open_period(settings.guild_id, started_at)
    assert repo.open_voice_session(settings.guild_id, 7, 100, started_at)

    live_voice = repo.export_live_voice_snapshot()

    member = live_voice[0]["members"][0]
    assert member["user_id"] == "7"
    assert member["channel_id"] == "100"
    assert member["voice_tickets"] == 1
    assert 0 < member["next_ticket_in_seconds"] <= 60 * 60
