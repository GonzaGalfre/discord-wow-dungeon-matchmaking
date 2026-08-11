"""SQLite repositories for participation tracking and raffles."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable

from models.database import get_connection
from services.participation import ParticipationCalculator, ParticipationRules, ParticipationTotals, VoiceInterval


RAFFLE_OPEN = "OPEN"
RAFFLE_CLOSED = "CLOSED"
RAFFLE_DRAWN = "DRAWN"


@dataclass(frozen=True, slots=True)
class ParticipationSettings:
    guild_id: int
    enabled: bool
    eligible_role_ids: frozenset[int]
    officer_role_ids: frozenset[int]
    tracked_voice_channel_ids: frozenset[int]
    first_voice_minutes_per_ticket: int
    voice_minutes_per_ticket: int
    max_voice_tickets: int
    panel_channel_id: int | None
    panel_message_id: int | None
    panel_update_minutes: int
    panel_last_updated_at: datetime | None
    raffle_publish_channel_id: int | None

    @property
    def configured(self) -> bool:
        return bool(
            self.eligible_role_ids
            and self.officer_role_ids
            and self.tracked_voice_channel_ids
        )


@dataclass(frozen=True, slots=True)
class VoiceSession:
    id: int
    guild_id: int
    user_id: int
    channel_id: int
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None


@dataclass(frozen=True, slots=True)
class RafflePeriod:
    id: int
    guild_id: int
    starts_at: datetime
    ends_at: datetime
    status: str
    closed_at: datetime | None
    drawn_at: datetime | None
    winner_user_id: int | None
    total_tickets_at_draw: int | None
    winning_number: int | None


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_db_time(value: datetime) -> str:
    return ensure_utc(value).isoformat()


def _from_db_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return ensure_utc(datetime.fromisoformat(value))


def _ids_to_json(ids: Iterable[int]) -> str:
    return json.dumps(sorted({int(item) for item in ids}))


def _ids_from_json(value: str | None) -> frozenset[int]:
    if not value:
        return frozenset()
    try:
        return frozenset(int(item) for item in json.loads(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return frozenset()


def _settings_from_row(row) -> ParticipationSettings:
    return ParticipationSettings(
        guild_id=int(row["guild_id"]),
        enabled=bool(row["enabled"]),
        eligible_role_ids=_ids_from_json(row["eligible_role_ids"]),
        officer_role_ids=_ids_from_json(row["officer_role_ids"]),
        tracked_voice_channel_ids=_ids_from_json(row["tracked_voice_channel_ids"]),
        first_voice_minutes_per_ticket=int(row["first_voice_minutes_per_ticket"]),
        voice_minutes_per_ticket=int(row["voice_minutes_per_ticket"]),
        max_voice_tickets=int(row["max_voice_tickets"]),
        panel_channel_id=row["panel_channel_id"],
        panel_message_id=row["panel_message_id"],
        panel_update_minutes=int(row["panel_update_minutes"]),
        panel_last_updated_at=_from_db_time(row["panel_last_updated_at"]),
        raffle_publish_channel_id=row["raffle_publish_channel_id"],
    )


def _voice_session_from_row(row) -> VoiceSession:
    return VoiceSession(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]),
        user_id=int(row["user_id"]),
        channel_id=int(row["channel_id"]),
        started_at=_from_db_time(row["started_at"]),
        ended_at=_from_db_time(row["ended_at"]),
        duration_seconds=row["duration_seconds"],
    )


def _period_from_row(row) -> RafflePeriod:
    return RafflePeriod(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]),
        starts_at=_from_db_time(row["starts_at"]),
        ends_at=_from_db_time(row["ends_at"]),
        status=row["status"],
        closed_at=_from_db_time(row["closed_at"]),
        drawn_at=_from_db_time(row["drawn_at"]),
        winner_user_id=row["winner_user_id"],
        total_tickets_at_draw=row["total_tickets_at_draw"],
        winning_number=row["winning_number"],
    )


def get_participation_settings(guild_id: int) -> ParticipationSettings | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM participation_settings WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    return _settings_from_row(row) if row else None


def get_or_create_participation_settings(guild_id: int) -> ParticipationSettings:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO participation_settings (guild_id)
        VALUES (?)
        ON CONFLICT(guild_id) DO NOTHING
        """,
        (guild_id,),
    )
    conn.commit()
    settings = get_participation_settings(guild_id)
    if settings is None:
        raise RuntimeError("failed to create participation settings")
    return settings


def update_participation_roles(guild_id: int, eligible_role_ids: Iterable[int], officer_role_ids: Iterable[int]) -> None:
    get_or_create_participation_settings(guild_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE participation_settings
        SET eligible_role_ids = ?, officer_role_ids = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (_ids_to_json(eligible_role_ids), _ids_to_json(officer_role_ids), guild_id),
    )
    conn.commit()


def add_tracked_voice_channel(guild_id: int, channel_id: int) -> ParticipationSettings:
    settings = get_or_create_participation_settings(guild_id)
    channel_ids = set(settings.tracked_voice_channel_ids)
    channel_ids.add(channel_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE participation_settings
        SET tracked_voice_channel_ids = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (_ids_to_json(channel_ids), guild_id),
    )
    conn.commit()
    return get_or_create_participation_settings(guild_id)


def update_participation_rules(
    guild_id: int,
    first_voice_minutes_per_ticket: int,
    voice_minutes_per_ticket: int,
    max_voice_tickets: int,
) -> None:
    get_or_create_participation_settings(guild_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE participation_settings
        SET first_voice_minutes_per_ticket = ?, voice_minutes_per_ticket = ?, max_voice_tickets = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (
            first_voice_minutes_per_ticket,
            voice_minutes_per_ticket,
            max_voice_tickets,
            guild_id,
        ),
    )
    conn.commit()


def update_participation_panel(guild_id: int, channel_id: int, message_id: int) -> ParticipationSettings:
    get_or_create_participation_settings(guild_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE participation_settings
        SET panel_channel_id = ?, panel_message_id = ?, panel_last_updated_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (channel_id, message_id, _to_db_time(utc_now()), guild_id),
    )
    conn.commit()
    return get_or_create_participation_settings(guild_id)


def update_raffle_publish_channel(guild_id: int, channel_id: int | None) -> ParticipationSettings:
    get_or_create_participation_settings(guild_id)
    conn = get_connection()
    conn.execute(
        "UPDATE participation_settings SET raffle_publish_channel_id = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
        (channel_id, guild_id),
    )
    conn.commit()
    return get_or_create_participation_settings(guild_id)


def update_participation_panel_interval(guild_id: int, minutes: int) -> ParticipationSettings:
    get_or_create_participation_settings(guild_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE participation_settings
        SET panel_update_minutes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (minutes, guild_id),
    )
    conn.commit()
    return get_or_create_participation_settings(guild_id)


def clear_participation_panel(guild_id: int) -> ParticipationSettings:
    get_or_create_participation_settings(guild_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE participation_settings
        SET panel_channel_id = NULL, panel_message_id = NULL, panel_last_updated_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    conn.commit()
    return get_or_create_participation_settings(guild_id)


def mark_participation_panel_refreshed(guild_id: int, refreshed_at: datetime | None = None) -> None:
    conn = get_connection()
    conn.execute(
        """
        UPDATE participation_settings
        SET panel_last_updated_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (_to_db_time(refreshed_at or utc_now()), guild_id),
    )
    conn.commit()


def list_configured_participation_settings() -> list[ParticipationSettings]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM participation_settings WHERE enabled = 1")
    return [_settings_from_row(row) for row in cursor.fetchall() if _settings_from_row(row).configured]


def list_participation_settings() -> list[ParticipationSettings]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM participation_settings ORDER BY guild_id")
    return [_settings_from_row(row) for row in cursor.fetchall()]


def list_configured_participation_panels() -> list[ParticipationSettings]:
    return [
        settings
        for settings in list_configured_participation_settings()
        if settings.panel_channel_id and settings.panel_message_id and settings.panel_update_minutes > 0
    ]


def _string_ids(ids: Iterable[int]) -> list[str]:
    return [str(item) for item in sorted({int(value) for value in ids})]


def export_participation_settings_snapshot() -> list[dict]:
    return [
        {
            "guild_id": str(settings.guild_id),
            "enabled": settings.enabled,
            "eligible_role_ids": _string_ids(settings.eligible_role_ids),
            "officer_role_ids": _string_ids(settings.officer_role_ids),
            "tracked_voice_channel_ids": _string_ids(settings.tracked_voice_channel_ids),
            "first_voice_minutes_per_ticket": settings.first_voice_minutes_per_ticket,
            "voice_minutes_per_ticket": settings.voice_minutes_per_ticket,
            "max_voice_tickets": settings.max_voice_tickets,
            "raffle_publish_channel_id": str(settings.raffle_publish_channel_id) if settings.raffle_publish_channel_id else None,
            "panel_channel_id": str(settings.panel_channel_id) if settings.panel_channel_id else None,
            "panel_message_id": str(settings.panel_message_id) if settings.panel_message_id else None,
            "panel_update_minutes": settings.panel_update_minutes,
            "panel_last_updated_at": _to_db_time(settings.panel_last_updated_at) if settings.panel_last_updated_at else None,
        }
        for settings in list_participation_settings()
    ]


def export_participation_leaderboards_snapshot() -> list[dict]:
    """Export current-period totals; the bot remains authoritative for activity data."""
    now = utc_now()
    leaderboards: list[dict] = []
    for settings in list_configured_participation_settings():
        period = ensure_open_period(settings.guild_id, now)
        calculator = ParticipationCalculator(
            ParticipationRules(
                first_voice_minutes_per_ticket=settings.first_voice_minutes_per_ticket,
                voice_minutes_per_ticket=settings.voice_minutes_per_ticket,
                messages_per_ticket=10,
                max_voice_tickets=settings.max_voice_tickets,
                max_message_tickets=0,
            )
        )
        totals = totals_for_period(settings.guild_id, period.starts_at, period.ends_at, now, calculator)
        entries = sorted(
            totals,
            key=lambda item: (-item.total_tickets, -item.voice_seconds, -item.message_count, item.user_id),
        )
        leaderboards.append(
            {
                "guild_id": str(settings.guild_id),
                "starts_at": _to_db_time(period.starts_at),
                "ends_at": _to_db_time(period.ends_at),
                "entries": [
                    {
                        "user_id": str(item.user_id),
                        "voice_seconds": item.voice_seconds,
                        "voice_tickets": item.voice_tickets,
                        "total_tickets": item.total_tickets,
                    }
                    for item in entries
                ],
            }
        )
    return leaderboards


def export_live_voice_snapshot() -> list[dict]:
    """Export active tracked-channel sessions and progress toward the next ticket."""
    now = utc_now()
    live_voice: list[dict] = []
    for settings in list_configured_participation_settings():
        period = ensure_open_period(settings.guild_id, now)
        calculator = ParticipationCalculator(
            ParticipationRules(
                first_voice_minutes_per_ticket=settings.first_voice_minutes_per_ticket,
                voice_minutes_per_ticket=settings.voice_minutes_per_ticket,
                messages_per_ticket=10,
                max_voice_tickets=settings.max_voice_tickets,
                max_message_tickets=0,
            )
        )
        totals = {
            item.user_id: item
            for item in totals_for_period(settings.guild_id, period.starts_at, period.ends_at, now, calculator)
        }
        first_ticket_seconds = settings.first_voice_minutes_per_ticket * 60
        ticket_interval_seconds = settings.voice_minutes_per_ticket * 60
        members = []
        for session in list_open_voice_sessions(settings.guild_id):
            if session.channel_id not in settings.tracked_voice_channel_ids:
                continue
            total = totals.get(session.user_id)
            voice_seconds = total.voice_seconds if total else 0
            voice_tickets = total.voice_tickets if total else 0
            if voice_tickets >= settings.max_voice_tickets:
                next_ticket_in_seconds = None
            elif voice_seconds < first_ticket_seconds:
                next_ticket_in_seconds = first_ticket_seconds - voice_seconds
            else:
                next_ticket_in_seconds = max(
                    0,
                    first_ticket_seconds + (voice_tickets * ticket_interval_seconds) - voice_seconds,
                )
            members.append(
                {
                    "user_id": str(session.user_id),
                    "channel_id": str(session.channel_id),
                    "started_at": _to_db_time(session.started_at),
                    "session_seconds": max(0, int((now - session.started_at).total_seconds())),
                    "period_voice_seconds": voice_seconds,
                    "voice_tickets": voice_tickets,
                    "next_ticket_in_seconds": next_ticket_in_seconds,
                }
            )
        live_voice.append(
            {
                "guild_id": str(settings.guild_id),
                "generated_at": _to_db_time(now),
                "members": sorted(members, key=lambda item: (item["channel_id"], item["user_id"])),
            }
        )
    return live_voice


def _int_set(value: object) -> frozenset[int]:
    if not isinstance(value, list):
        return frozenset()
    result: set[int] = set()
    for item in value:
        text = str(item).strip()
        if text.isdigit():
            result.add(int(text))
    return frozenset(result)


def _int_value(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def upsert_participation_settings_from_snapshot(payload: dict) -> ParticipationSettings | None:
    guild_id = _optional_int(payload.get("guild_id"))
    if guild_id is None:
        return None
    current = get_or_create_participation_settings(guild_id)
    conn = get_connection()
    conn.execute(
        """
        UPDATE participation_settings
        SET enabled = ?, eligible_role_ids = ?, officer_role_ids = ?, tracked_voice_channel_ids = ?,
            first_voice_minutes_per_ticket = ?, voice_minutes_per_ticket = ?, max_voice_tickets = ?,
            panel_channel_id = ?, panel_message_id = ?, panel_update_minutes = ?, raffle_publish_channel_id = ?,
            panel_last_updated_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (
            1 if payload.get("enabled", True) else 0,
            _ids_to_json(_int_set(payload.get("eligible_role_ids"))),
            _ids_to_json(_int_set(payload.get("officer_role_ids"))),
            _ids_to_json(_int_set(payload.get("tracked_voice_channel_ids"))),
            max(1, _int_value(payload.get("first_voice_minutes_per_ticket"), current.first_voice_minutes_per_ticket)),
            max(1, _int_value(payload.get("voice_minutes_per_ticket"), current.voice_minutes_per_ticket)),
            _int_value(payload.get("max_voice_tickets"), current.max_voice_tickets),
            _optional_int(payload.get("panel_channel_id")),
            _optional_int(payload.get("panel_message_id")),
            max(1, _int_value(payload.get("panel_update_minutes"), current.panel_update_minutes)),
            _optional_int(payload.get("raffle_publish_channel_id")),
            payload.get("panel_last_updated_at") if isinstance(payload.get("panel_last_updated_at"), str) else None,
            guild_id,
        ),
    )
    conn.commit()
    return get_participation_settings(guild_id)


def get_open_voice_session(guild_id: int, user_id: int) -> VoiceSession | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM voice_sessions WHERE guild_id = ? AND user_id = ? AND ended_at IS NULL",
        (guild_id, user_id),
    )
    row = cursor.fetchone()
    return _voice_session_from_row(row) if row else None


def list_open_voice_sessions(guild_id: int) -> list[VoiceSession]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM voice_sessions WHERE guild_id = ? AND ended_at IS NULL", (guild_id,))
    return [_voice_session_from_row(row) for row in cursor.fetchall()]


def open_voice_session(guild_id: int, user_id: int, channel_id: int, started_at: datetime) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO voice_sessions (guild_id, user_id, channel_id, started_at)
        VALUES (?, ?, ?, ?)
        """,
        (guild_id, user_id, channel_id, _to_db_time(started_at)),
    )
    conn.commit()
    return cursor.rowcount == 1


def update_open_voice_channel(guild_id: int, user_id: int, channel_id: int) -> None:
    conn = get_connection()
    conn.execute(
        """
        UPDATE voice_sessions
        SET channel_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ? AND user_id = ? AND ended_at IS NULL
        """,
        (channel_id, guild_id, user_id),
    )
    conn.commit()


def close_open_voice_session(guild_id: int, user_id: int, ended_at: datetime) -> VoiceSession | None:
    session = get_open_voice_session(guild_id, user_id)
    if session is None:
        return None
    ended_at = ensure_utc(ended_at)
    effective_ended_at = max(ended_at, session.started_at)
    duration_seconds = max(0, int((ended_at - session.started_at).total_seconds()))
    conn = get_connection()
    conn.execute(
        """
        UPDATE voice_sessions
        SET ended_at = ?, duration_seconds = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_to_db_time(effective_ended_at), duration_seconds, session.id),
    )
    conn.commit()
    return get_voice_session(session.id)


def close_all_open_voice_sessions(guild_id: int, ended_at: datetime) -> int:
    sessions = list_open_voice_sessions(guild_id)
    for session in sessions:
        close_open_voice_session(guild_id, session.user_id, ended_at)
    return len(sessions)


def get_voice_session(session_id: int) -> VoiceSession | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM voice_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    return _voice_session_from_row(row) if row else None


def voice_intervals_for_period(guild_id: int, starts_at: datetime, ends_at: datetime) -> list[VoiceInterval]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, started_at, ended_at
        FROM voice_sessions
        WHERE guild_id = ? AND started_at < ? AND (ended_at IS NULL OR ended_at > ?)
        """,
        (guild_id, _to_db_time(ends_at), _to_db_time(starts_at)),
    )
    return [
        VoiceInterval(int(row["user_id"]), _from_db_time(row["started_at"]), _from_db_time(row["ended_at"]))
        for row in cursor.fetchall()
    ]


def latest_counted_message_at(guild_id: int, user_id: int) -> datetime | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(created_at) AS latest FROM counted_messages WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = cursor.fetchone()
    return _from_db_time(row["latest"] if row else None)


def count_message(
    discord_message_id: int,
    guild_id: int,
    user_id: int,
    channel_id: int,
    created_at: datetime,
    cooldown_seconds: int,
) -> bool:
    latest = latest_counted_message_at(guild_id, user_id)
    created_at = ensure_utc(created_at)
    if latest is not None and created_at < latest + timedelta(seconds=cooldown_seconds):
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO counted_messages (discord_message_id, guild_id, user_id, channel_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (discord_message_id, guild_id, user_id, channel_id, _to_db_time(created_at)),
    )
    conn.commit()
    return cursor.rowcount == 1


def message_counts_for_period(guild_id: int, starts_at: datetime, ends_at: datetime) -> dict[int, int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, COUNT(*) AS count
        FROM counted_messages
        WHERE guild_id = ? AND created_at >= ? AND created_at < ?
        GROUP BY user_id
        """,
        (guild_id, _to_db_time(starts_at), _to_db_time(ends_at)),
    )
    return {int(row["user_id"]): int(row["count"]) for row in cursor.fetchall()}


def totals_for_period(
    guild_id: int,
    starts_at: datetime,
    ends_at: datetime,
    now: datetime,
    calculator: ParticipationCalculator,
) -> list[ParticipationTotals]:
    voice_by_user: dict[int, int] = {}
    for interval in voice_intervals_for_period(guild_id, starts_at, ends_at):
        overlap = calculator.overlapping_seconds(interval, starts_at, ends_at, now)
        voice_by_user[interval.user_id] = voice_by_user.get(interval.user_id, 0) + overlap
    totals = {
        user_id: calculator.ticket_totals(user_id, voice_seconds, 0)
        for user_id, voice_seconds in voice_by_user.items()
    }
    period = get_current_open_period(guild_id)
    if period and period.starts_at == ensure_utc(starts_at):
        for user_id, tickets in list_debug_tickets(period.id).items():
            total = totals.get(user_id, calculator.ticket_totals(user_id, 0, 0))
            totals[user_id] = ParticipationTotals(
                user_id=total.user_id,
                voice_seconds=total.voice_seconds,
                message_count=total.message_count,
                voice_tickets=total.voice_tickets,
                message_tickets=total.message_tickets,
                debug_tickets=tickets,
            )
    return [
        totals[user_id]
        for user_id in sorted(totals)
    ]


def get_current_open_period(guild_id: int) -> RafflePeriod | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM raffle_periods
        WHERE guild_id = ? AND status = ?
        ORDER BY starts_at DESC
        LIMIT 1
        """,
        (guild_id, RAFFLE_OPEN),
    )
    row = cursor.fetchone()
    return _period_from_row(row) if row else None


def get_latest_closed_undrawn_period(guild_id: int) -> RafflePeriod | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM raffle_periods
        WHERE guild_id = ? AND status = ?
        ORDER BY ends_at DESC
        LIMIT 1
        """,
        (guild_id, RAFFLE_CLOSED),
    )
    row = cursor.fetchone()
    return _period_from_row(row) if row else None


def create_open_period(guild_id: int, starts_at: datetime) -> RafflePeriod:
    conn = get_connection()
    cursor = conn.cursor()
    # SQLite's legacy schema requires an end timestamp; manual periods never
    # close automatically, so this is only a sentinel until a draw/reset.
    ends_at = ensure_utc(starts_at) + timedelta(days=36500)
    cursor.execute(
        """
        INSERT INTO raffle_periods (guild_id, starts_at, ends_at, status)
        VALUES (?, ?, ?, ?)
        """,
        (guild_id, _to_db_time(starts_at), _to_db_time(ends_at), RAFFLE_OPEN),
    )
    conn.commit()
    return get_period(cursor.lastrowid)


def get_period(period_id: int) -> RafflePeriod | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM raffle_periods WHERE id = ?", (period_id,))
    row = cursor.fetchone()
    return _period_from_row(row) if row else None


def close_period(period_id: int, closed_at: datetime) -> RafflePeriod:
    conn = get_connection()
    conn.execute(
        """
        UPDATE raffle_periods
        SET status = ?, ends_at = ?, closed_at = ?
        WHERE id = ?
        """,
        (RAFFLE_CLOSED, _to_db_time(closed_at), _to_db_time(closed_at), period_id),
    )
    conn.commit()
    return get_period(period_id)


def ensure_open_period(guild_id: int, now: datetime) -> RafflePeriod:
    period = get_current_open_period(guild_id)
    if period is None:
        return create_open_period(guild_id, now)
    return period


def reset_current_period(guild_id: int, reset_at: datetime) -> tuple[RafflePeriod, RafflePeriod] | None:
    period = get_current_open_period(guild_id)
    if period is None:
        return None
    closed = close_period(period.id, reset_at)
    next_period = create_open_period(guild_id, reset_at)
    return closed, next_period


def get_preview_period(guild_id: int) -> RafflePeriod | None:
    return get_current_open_period(guild_id)


def list_debug_tickets(period_id: int) -> dict[int, int]:
    rows = get_connection().execute(
        "SELECT user_id, tickets FROM raffle_debug_tickets WHERE raffle_period_id = ?", (period_id,)
    ).fetchall()
    return {int(row["user_id"]): int(row["tickets"]) for row in rows}


def add_debug_tickets(guild_id: int, user_id: int, tickets: int, now: datetime) -> tuple[RafflePeriod, int]:
    if tickets <= 0:
        raise ValueError("tickets must be positive")
    period = ensure_open_period(guild_id, now)
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO raffle_debug_tickets (raffle_period_id, user_id, tickets)
            VALUES (?, ?, ?)
            ON CONFLICT(raffle_period_id, user_id) DO UPDATE SET tickets = tickets + excluded.tickets
            """,
            (period.id, user_id, tickets),
        )
    return period, list_debug_tickets(period.id)[user_id]


def mark_period_drawn(
    period: RafflePeriod,
    snapshots: Iterable[dict],
    winner_user_id: int,
    total_tickets: int,
    winning_number: int,
    drawn_at: datetime,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE raffle_periods
        SET status = ?, winner_user_id = ?, total_tickets_at_draw = ?, winning_number = ?, drawn_at = ?
        WHERE id = ?
        """,
        (RAFFLE_DRAWN, winner_user_id, total_tickets, winning_number, _to_db_time(drawn_at), period.id),
    )
    for snapshot in snapshots:
        cursor.execute(
            """
            INSERT INTO raffle_entry_snapshots (
                raffle_period_id, user_id, voice_seconds, message_count, voice_tickets, message_tickets,
                total_tickets, cumulative_ticket_start, cumulative_ticket_end
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                period.id,
                snapshot["user_id"],
                snapshot["voice_seconds"],
                snapshot["message_count"],
                snapshot["voice_tickets"],
                snapshot["message_tickets"],
                snapshot["total_tickets"],
                snapshot["cumulative_ticket_start"],
                snapshot["cumulative_ticket_end"],
            ),
        )
    conn.commit()


def list_exclusive_winner_ids(guild_id: int) -> list[int]:
    rows = get_connection().execute(
        "SELECT user_id FROM raffle_exclusive_winners WHERE guild_id = ? ORDER BY user_id", (guild_id,)
    ).fetchall()
    return [int(row["user_id"]) for row in rows]


def replace_exclusive_winner_ids(guild_id: int, user_ids: Iterable[int]) -> list[int]:
    ids = sorted({int(user_id) for user_id in user_ids})
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM raffle_exclusive_winners WHERE guild_id = ?", (guild_id,))
        conn.executemany(
            "INSERT INTO raffle_exclusive_winners (guild_id, user_id, created_at) VALUES (?, ?, ?)",
            [(guild_id, user_id, _to_db_time(utc_now())) for user_id in ids],
        )
    return ids


def draw_current_period(guild_id: int, now: datetime, calculator: ParticipationCalculator) -> dict:
    """Atomically snapshot, draw, exclude the winner, and open the next period."""
    conn = get_connection()
    now = ensure_utc(now)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM raffle_periods WHERE guild_id = ? AND status = ? ORDER BY starts_at DESC LIMIT 1",
            (guild_id, RAFFLE_OPEN),
        ).fetchone()
        if row is None:
            raise ValueError("no open raffle period")
        period = _period_from_row(row)
        excluded = set(list_exclusive_winner_ids(guild_id))
        voice_by_user: dict[int, int] = {}
        for interval in voice_intervals_for_period(guild_id, period.starts_at, now):
            overlap = calculator.overlapping_seconds(interval, period.starts_at, now, now)
            voice_by_user[interval.user_id] = voice_by_user.get(interval.user_id, 0) + overlap
        totals = []
        for user_id in set(voice_by_user) | set(list_debug_tickets(period.id)):
            total = calculator.ticket_totals(user_id, voice_by_user.get(user_id, 0), 0)
            totals.append(ParticipationTotals(
                user_id=total.user_id, voice_seconds=total.voice_seconds, message_count=total.message_count,
                voice_tickets=total.voice_tickets, message_tickets=total.message_tickets,
                debug_tickets=list_debug_tickets(period.id).get(user_id, 0),
            ))
        totals = [item for item in totals if item.user_id not in excluded]
        cumulative = 0
        snapshots: list[dict] = []
        for total in sorted((item for item in totals if item.total_tickets > 0), key=lambda item: item.user_id):
            start = cumulative + 1
            cumulative += total.total_tickets
            snapshots.append({"user_id": total.user_id, "voice_seconds": total.voice_seconds, "message_count": 0,
                              "voice_tickets": total.voice_tickets, "message_tickets": 0, "total_tickets": total.total_tickets,
                              "cumulative_ticket_start": start, "cumulative_ticket_end": cumulative})
        if not snapshots:
            raise ValueError("no eligible participants have tickets")
        winning_number = secrets.randbelow(cumulative) + 1
        winner = next(item for item in snapshots if item["cumulative_ticket_start"] <= winning_number <= item["cumulative_ticket_end"])
        conn.execute(
            "UPDATE raffle_periods SET status = ?, ends_at = ?, closed_at = ?, winner_user_id = ?, total_tickets_at_draw = ?, winning_number = ?, drawn_at = ? WHERE id = ?",
            (RAFFLE_DRAWN, _to_db_time(now), _to_db_time(now), winner["user_id"], cumulative, winning_number, _to_db_time(now), period.id),
        )
        conn.executemany(
            "INSERT INTO raffle_entry_snapshots (raffle_period_id, user_id, voice_seconds, message_count, voice_tickets, message_tickets, total_tickets, cumulative_ticket_start, cumulative_ticket_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(period.id, item["user_id"], item["voice_seconds"], 0, item["voice_tickets"], 0, item["total_tickets"], item["cumulative_ticket_start"], item["cumulative_ticket_end"]) for item in snapshots],
        )
        conn.execute("INSERT INTO raffle_exclusive_winners (guild_id, user_id, created_at) VALUES (?, ?, ?)", (guild_id, winner["user_id"], _to_db_time(now)))
        cursor = conn.execute("INSERT INTO raffle_periods (guild_id, starts_at, ends_at, status) VALUES (?, ?, ?, ?)", (guild_id, _to_db_time(now), _to_db_time(now + timedelta(days=36500)), RAFFLE_OPEN))
        return {"period_id": period.id, "next_period_id": cursor.lastrowid, "winner_user_id": winner["user_id"], "winner_tickets": winner["total_tickets"], "total_tickets": cumulative, "winning_number": winning_number, "participant_count": len(snapshots), "drawn_at": _to_db_time(now)}


def get_action_receipt(action_id: str) -> dict | None:
    row = get_connection().execute("SELECT result_json FROM raffle_action_receipts WHERE action_id = ?", (action_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def save_action_receipt(action_id: str, guild_id: int, action_type: str, result: dict) -> None:
    get_connection().execute(
        "INSERT OR IGNORE INTO raffle_action_receipts (action_id, guild_id, action_type, result_json, processed_at) VALUES (?, ?, ?, ?, ?)",
        (action_id, guild_id, action_type, json.dumps(result, sort_keys=True), _to_db_time(utc_now())),
    )
    get_connection().commit()


def export_raffle_state_snapshot() -> list[dict]:
    states = []
    for settings in list_participation_settings():
        period = ensure_open_period(settings.guild_id, utc_now())
        states.append({"guild_id": str(settings.guild_id), "open_period": {"id": str(period.id), "starts_at": _to_db_time(period.starts_at)}, "exclusive_winner_user_ids": [str(user_id) for user_id in list_exclusive_winner_ids(settings.guild_id)]})
    return states


def export_raffle_action_receipts() -> list[dict]:
    rows = get_connection().execute("SELECT action_id, guild_id, action_type, result_json, processed_at FROM raffle_action_receipts ORDER BY processed_at").fetchall()
    return [{"action_id": row["action_id"], "guild_id": str(row["guild_id"]), "type": row["action_type"], "result": json.loads(row["result_json"]), "processed_at": row["processed_at"]} for row in rows]


def get_pending_raffle_publications() -> list[RafflePeriod]:
    rows = get_connection().execute("SELECT p.* FROM raffle_periods p LEFT JOIN raffle_draw_publications d ON d.raffle_period_id = p.id WHERE p.status = ? AND d.raffle_period_id IS NULL", (RAFFLE_DRAWN,)).fetchall()
    return [_period_from_row(row) for row in rows]


def list_published_raffle_periods() -> list[RafflePeriod]:
    rows = get_connection().execute(
        "SELECT p.* FROM raffle_periods p JOIN raffle_draw_publications d ON d.raffle_period_id = p.id WHERE p.status = ?",
        (RAFFLE_DRAWN,),
    ).fetchall()
    return [_period_from_row(row) for row in rows]


def list_raffle_entry_snapshots(period_id: int) -> list[dict]:
    rows = get_connection().execute(
        "SELECT user_id, total_tickets FROM raffle_entry_snapshots WHERE raffle_period_id = ? ORDER BY user_id",
        (period_id,),
    ).fetchall()
    return [{"user_id": int(row["user_id"]), "total_tickets": int(row["total_tickets"])} for row in rows]


def mark_raffle_published(period_id: int, channel_id: int, message_id: int) -> None:
    get_connection().execute("INSERT OR IGNORE INTO raffle_draw_publications (raffle_period_id, channel_id, message_id, published_at) VALUES (?, ?, ?, ?)", (period_id, channel_id, message_id, _to_db_time(utc_now())))
    get_connection().commit()
