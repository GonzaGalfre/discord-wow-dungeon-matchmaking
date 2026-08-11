"""SQLite data access for raid signup events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from models.database import get_connection


def create_raid_event(
    guild_id: int,
    channel_id: int,
    title: str,
    starts_at: str,
    created_by_user_id: int,
    leader_name: Optional[str] = None,
    external_id: Optional[str] = None,
) -> int:
    """Create a raid event and return its database ID."""
    external_id = external_id or f"raid-{uuid4().hex}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO raid_events (
            external_id,
            guild_id,
            channel_id,
            title,
            leader_name,
            starts_at,
            created_by_user_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (external_id, guild_id, channel_id, title, leader_name, starts_at, created_by_user_id),
    )
    conn.commit()
    return int(cursor.lastrowid)


def attach_raid_message(event_id: int, message_id: int) -> None:
    """Attach the Discord message ID after the signup message is sent."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE raid_events
        SET message_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (message_id, event_id),
    )
    conn.commit()


def get_raid_event(event_id: int) -> Optional[dict]:
    """Return a raid event by database ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM raid_events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_raid_event_by_message(message_id: int) -> Optional[dict]:
    """Return a raid event by Discord signup message ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM raid_events WHERE message_id = ?", (message_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_raid_event_by_external_id(external_id: str) -> Optional[dict]:
    """Return a raid event by shared website/bot ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM raid_events WHERE external_id = ?", (external_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def list_raid_events() -> list[dict]:
    """Return all raid events."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM raid_events
        ORDER BY created_at DESC, id DESC
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def list_raid_signups(event_id: int) -> list[dict]:
    """Return all signups for an event, ordered by latest update."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM raid_signups
        WHERE event_id = ?
        ORDER BY updated_at ASC, display_name COLLATE NOCASE ASC
        """,
        (event_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_raid_signup(event_id: int, user_id: int) -> Optional[dict]:
    """Return one user's signup for an event."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM raid_signups
        WHERE event_id = ? AND user_id = ?
        """,
        (event_id, user_id),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def upsert_raid_signup(
    event_id: int,
    user_id: int,
    display_name: str,
    status: str,
    class_key: Optional[str] = None,
    spec_key: Optional[str] = None,
    note: Optional[str] = None,
) -> None:
    """Create or update a user's signup."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO raid_signups (
            event_id,
            user_id,
            display_name,
            status,
            class_key,
            spec_key,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id, user_id) DO UPDATE SET
            display_name = excluded.display_name,
            status = excluded.status,
            class_key = excluded.class_key,
            spec_key = excluded.spec_key,
            note = COALESCE(excluded.note, raid_signups.note),
            updated_at = CURRENT_TIMESTAMP
        """,
        (event_id, user_id, display_name, status, class_key, spec_key, note),
    )
    conn.commit()


def update_raid_signup_status(
    event_id: int,
    user_id: int,
    display_name: str,
    status: str,
) -> None:
    """Update attendance status while preserving class/spec when present."""
    existing = get_raid_signup(event_id, user_id)
    upsert_raid_signup(
        event_id=event_id,
        user_id=user_id,
        display_name=display_name,
        status=status,
        class_key=existing.get("class_key") if existing else None,
        spec_key=existing.get("spec_key") if existing else None,
        note=existing.get("note") if existing else None,
    )


def delete_raid_signup(event_id: int, user_id: int) -> bool:
    """Remove a signup. Returns True when a row was deleted."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM raid_signups WHERE event_id = ? AND user_id = ?",
        (event_id, user_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_raid_event_by_external_id(external_id: str) -> bool:
    """Delete a raid event and its signups by shared external ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM raid_events WHERE external_id = ?", (external_id,))
    conn.commit()
    return cursor.rowcount > 0


def delete_dummy_raid_signups(event_id: int, user_id_minimum: int) -> int:
    """Delete dummy signups for an event and return the number removed."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM raid_signups
        WHERE event_id = ? AND user_id >= ?
        """,
        (event_id, user_id_minimum),
    )
    conn.commit()
    return cursor.rowcount


def set_raid_event_open(event_id: int, is_open: bool) -> bool:
    """Open or close signup interactions for an event."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE raid_events
        SET is_open = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (1 if is_open else 0, event_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def mark_roster_published(event_id: int, published_at: str) -> None:
    """Mark a confirmed roster publish request as handled."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE raid_events
        SET roster_published_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (published_at, event_id),
    )
    conn.commit()


def update_raid_event_from_snapshot(event: dict) -> int:
    """Create/update a local event from a shared hub snapshot."""
    external_id = str(event["external_id"])
    existing = get_raid_event_by_external_id(external_id)
    guild_id = int(event.get("guild_id") or 0)
    channel_id = int(event.get("channel_id") or 0)
    message_id = event.get("message_id")
    created_by_user_id = int(event.get("created_by_user_id") or 0)
    title = str(event.get("title") or "Raid")
    leader_name = event.get("leader_name")
    starts_at = str(event.get("starts_at") or "TBD")
    is_open = 1 if event.get("is_open", True) else 0
    confirmed_roster = event.get("confirmed_roster")
    confirmed_roster_json = json.dumps(confirmed_roster if isinstance(confirmed_roster, list) else [])
    bench_roster = event.get("bench_roster")
    bench_roster_json = json.dumps(bench_roster if isinstance(bench_roster, list) else [])
    roster_publish_channel_id = event.get("roster_publish_channel_id")
    roster_publish_requested_at = event.get("roster_publish_requested_at")
    roster_published_at = event.get("roster_published_at")

    conn = get_connection()
    cursor = conn.cursor()
    if existing:
        cursor.execute(
            """
            UPDATE raid_events
            SET guild_id = ?,
                channel_id = ?,
                message_id = COALESCE(?, message_id),
                title = ?,
                leader_name = ?,
                starts_at = ?,
                created_by_user_id = ?,
                is_open = ?,
                confirmed_roster_json = ?,
                bench_roster_json = ?,
                roster_publish_channel_id = ?,
                roster_publish_requested_at = ?,
                roster_published_at = COALESCE(?, roster_published_at),
                updated_at = CURRENT_TIMESTAMP
            WHERE external_id = ?
            """,
            (
                guild_id,
                channel_id,
                message_id,
                title,
                leader_name,
                starts_at,
                created_by_user_id,
                is_open,
                confirmed_roster_json,
                bench_roster_json,
                str(roster_publish_channel_id) if roster_publish_channel_id else None,
                str(roster_publish_requested_at) if roster_publish_requested_at else None,
                str(roster_published_at) if roster_published_at else None,
                external_id,
            ),
        )
        conn.commit()
        return int(existing["id"])

    cursor.execute(
        """
        INSERT INTO raid_events (
            external_id,
            guild_id,
            channel_id,
            message_id,
            title,
            leader_name,
            starts_at,
            created_by_user_id,
            is_open,
            confirmed_roster_json,
            bench_roster_json,
            roster_publish_channel_id,
            roster_publish_requested_at,
            roster_published_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            external_id,
            guild_id,
            channel_id,
            message_id,
            title,
            leader_name,
            starts_at,
            created_by_user_id,
            is_open,
            confirmed_roster_json,
            bench_roster_json,
            str(roster_publish_channel_id) if roster_publish_channel_id else None,
            str(roster_publish_requested_at) if roster_publish_requested_at else None,
            str(roster_published_at) if roster_published_at else None,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def replace_raid_signups_from_snapshot(event_id: int, signups: list[dict]) -> None:
    """Replace all signups for an event from a shared hub snapshot."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM raid_signups WHERE event_id = ?", (event_id,))
    for signup in signups:
        cursor.execute(
            """
            INSERT INTO raid_signups (
                event_id,
                user_id,
                display_name,
                status,
                class_key,
                spec_key,
                note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                int(signup.get("user_id") or 0),
                str(signup.get("display_name") or "Unknown"),
                str(signup.get("status") or "attending"),
                signup.get("class_key"),
                signup.get("spec_key"),
                signup.get("note"),
            ),
        )
    conn.commit()


def export_raid_signup_snapshot() -> dict:
    """Export all raid signup data in a website-friendly shape."""
    events = []
    for event in list_raid_events():
        event_id = event["id"]
        try:
            confirmed_roster = json.loads(event.get("confirmed_roster_json") or "[]")
        except json.JSONDecodeError:
            confirmed_roster = []
        try:
            bench_roster = json.loads(event.get("bench_roster_json") or "[]")
        except json.JSONDecodeError:
            bench_roster = []
        events.append(
            {
                "id": event_id,
                "external_id": event.get("external_id") or f"discord-{event_id}",
                "guild_id": str(event["guild_id"]),
                "channel_id": str(event["channel_id"]),
                "message_id": str(event["message_id"]) if event.get("message_id") else None,
                "title": event["title"],
                "leader_name": event.get("leader_name"),
                "starts_at": event["starts_at"],
                "created_by_user_id": str(event["created_by_user_id"]),
                "is_open": bool(event.get("is_open", 1)),
                "created_at": event.get("created_at"),
                "updated_at": event.get("updated_at"),
                "confirmed_roster": confirmed_roster if isinstance(confirmed_roster, list) else [],
                "bench_roster": bench_roster if isinstance(bench_roster, list) else [],
                "roster_publish_channel_id": event.get("roster_publish_channel_id"),
                "roster_publish_requested_at": event.get("roster_publish_requested_at"),
                "roster_published_at": event.get("roster_published_at"),
                "signups": [
                    {
                        "user_id": str(signup["user_id"]),
                        "display_name": signup["display_name"],
                        "status": signup["status"],
                        "class_key": signup.get("class_key"),
                        "spec_key": signup.get("spec_key"),
                        "note": signup.get("note"),
                        "updated_at": signup.get("updated_at"),
                    }
                    for signup in list_raid_signups(event_id)
                ],
            }
        )

    return {
        "source": "wipybot",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "events": events,
    }
