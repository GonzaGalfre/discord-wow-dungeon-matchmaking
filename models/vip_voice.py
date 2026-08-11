"""SQLite repository for VIP voice channel access requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from models.database import get_connection


REQUEST_PENDING = "PENDING"
REQUEST_ACCEPTED = "ACCEPTED"
REQUEST_DENIED = "DENIED"
REQUEST_EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class VipVoiceChannel:
    guild_id: int
    channel_id: int
    role_id: int


@dataclass(frozen=True, slots=True)
class VipVoicePanel:
    guild_id: int
    channel_id: int
    message_id: int


@dataclass(frozen=True, slots=True)
class VipVoiceRequest:
    id: int
    guild_id: int
    channel_id: int
    requester_user_id: int
    status: str
    decided_by_user_id: int | None
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None


def utc_now() -> datetime:
    return datetime.now(UTC)


def _to_db_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _from_db_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _channel_from_row(row) -> VipVoiceChannel:
    return VipVoiceChannel(int(row["guild_id"]), int(row["channel_id"]), int(row["role_id"]))


def _panel_from_row(row) -> VipVoicePanel:
    return VipVoicePanel(int(row["guild_id"]), int(row["channel_id"]), int(row["message_id"]))


def _request_from_row(row) -> VipVoiceRequest:
    return VipVoiceRequest(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]),
        channel_id=int(row["channel_id"]),
        requester_user_id=int(row["requester_user_id"]),
        status=row["status"],
        decided_by_user_id=row["decided_by_user_id"],
        created_at=_from_db_time(row["created_at"]),
        expires_at=_from_db_time(row["expires_at"]),
        decided_at=_from_db_time(row["decided_at"]),
    )


def upsert_vip_channel(guild_id: int, channel_id: int, role_id: int) -> VipVoiceChannel:
    configured_for_role = get_vip_channel_by_role(guild_id, role_id)
    if configured_for_role is not None and configured_for_role.channel_id != channel_id:
        raise ValueError("a VIP role can only be assigned to one channel per guild")
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO vip_voice_channels (guild_id, channel_id, role_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, channel_id) DO UPDATE SET
            role_id = excluded.role_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (guild_id, channel_id, role_id),
    )
    conn.commit()
    channel = get_vip_channel(guild_id, channel_id)
    if channel is None:
        raise RuntimeError("failed to save VIP voice channel")
    return channel


def delete_vip_channel(guild_id: int, channel_id: int) -> bool:
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM vip_voice_channels WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_vip_channel(guild_id: int, channel_id: int) -> VipVoiceChannel | None:
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM vip_voice_channels WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    )
    row = cursor.fetchone()
    return _channel_from_row(row) if row else None


def get_vip_channel_by_role(guild_id: int, role_id: int) -> VipVoiceChannel | None:
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM vip_voice_channels WHERE guild_id = ? AND role_id = ?",
        (guild_id, role_id),
    )
    row = cursor.fetchone()
    return _channel_from_row(row) if row else None


def list_vip_channels(guild_id: int) -> list[VipVoiceChannel]:
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM vip_voice_channels WHERE guild_id = ? ORDER BY channel_id",
        (guild_id,),
    )
    return [_channel_from_row(row) for row in cursor.fetchall()]


def list_all_vip_channels() -> list[VipVoiceChannel]:
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM vip_voice_channels ORDER BY guild_id, channel_id")
    return [_channel_from_row(row) for row in cursor.fetchall()]


def set_vip_panel(guild_id: int, channel_id: int, message_id: int) -> VipVoicePanel:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO vip_voice_panels (guild_id, channel_id, message_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            message_id = excluded.message_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (guild_id, channel_id, message_id),
    )
    conn.commit()
    panel = get_vip_panel(guild_id)
    if panel is None:
        raise RuntimeError("failed to save VIP panel")
    return panel


def get_vip_panel(guild_id: int) -> VipVoicePanel | None:
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM vip_voice_panels WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    return _panel_from_row(row) if row else None


def clear_vip_panel(guild_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM vip_voice_panels WHERE guild_id = ?", (guild_id,))
    conn.commit()


def create_request(guild_id: int, channel_id: int, requester_user_id: int, ttl_seconds: int = 300) -> VipVoiceRequest:
    now = utc_now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO vip_voice_requests (guild_id, channel_id, requester_user_id, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (guild_id, channel_id, requester_user_id, _to_db_time(now), _to_db_time(expires_at)),
    )
    conn.commit()
    request = get_request(int(cursor.lastrowid))
    if request is None:
        raise RuntimeError("failed to create VIP request")
    return request


def get_request(request_id: int) -> VipVoiceRequest | None:
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM vip_voice_requests WHERE id = ?", (request_id,))
    row = cursor.fetchone()
    return _request_from_row(row) if row else None


def list_pending_requests(guild_id: int, channel_id: int) -> list[VipVoiceRequest]:
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT * FROM vip_voice_requests
        WHERE guild_id = ? AND channel_id = ? AND status = ?
        ORDER BY created_at
        """,
        (guild_id, channel_id, REQUEST_PENDING),
    )
    return [_request_from_row(row) for row in cursor.fetchall()]


def get_request_by_notification(message_id: int) -> VipVoiceRequest | None:
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT r.*
        FROM vip_voice_requests r
        JOIN vip_voice_request_notifications n ON n.request_id = r.id
        WHERE n.message_id = ?
        """,
        (message_id,),
    )
    row = cursor.fetchone()
    return _request_from_row(row) if row else None


def add_notification(request_id: int, user_id: int, message_id: int) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO vip_voice_request_notifications (request_id, user_id, message_id)
        VALUES (?, ?, ?)
        """,
        (request_id, user_id, message_id),
    )
    conn.commit()


def decide_request(request_id: int, status: str, decided_by_user_id: int, now: datetime | None = None) -> VipVoiceRequest | None:
    if status not in {REQUEST_ACCEPTED, REQUEST_DENIED, REQUEST_EXPIRED}:
        raise ValueError(f"invalid VIP request status: {status}")
    now = now or utc_now()
    conn = get_connection()
    conn.execute(
        """
        UPDATE vip_voice_requests
        SET status = ?, decided_by_user_id = ?, decided_at = ?
        WHERE id = ? AND status = ?
        """,
        (status, decided_by_user_id, _to_db_time(now), request_id, REQUEST_PENDING),
    )
    conn.commit()
    return get_request(request_id)


def expire_old_requests(now: datetime | None = None) -> int:
    now = now or utc_now()
    conn = get_connection()
    cursor = conn.execute(
        """
        UPDATE vip_voice_requests
        SET status = ?, decided_at = ?
        WHERE status = ? AND expires_at <= ?
        """,
        (REQUEST_EXPIRED, _to_db_time(now), REQUEST_PENDING, _to_db_time(now)),
    )
    conn.commit()
    return cursor.rowcount
