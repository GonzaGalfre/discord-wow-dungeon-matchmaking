"""Per-guild settings storage for WipyBot."""

from typing import Dict, Optional

from models.database import get_connection


def _ensure_guild_settings_table() -> None:
    """Ensure the guild_settings table and current columns exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            guild_name TEXT NOT NULL,
            signup_channel_id INTEGER,
            signup_message_id INTEGER,
            admin_channel_id INTEGER,
            move_panel_channel_id INTEGER,
            move_panel_message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute("PRAGMA table_info(guild_settings)")
    columns = {row[1] for row in cursor.fetchall()}
    for column in (
        "signup_channel_id",
        "signup_message_id",
        "admin_channel_id",
        "move_panel_channel_id",
        "move_panel_message_id",
    ):
        if column not in columns:
            cursor.execute(f"ALTER TABLE guild_settings ADD COLUMN {column} INTEGER")

    conn.commit()


def get_guild_settings(guild_id: int) -> Optional[Dict]:
    """Get settings for a Discord guild."""
    _ensure_guild_settings_table()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT guild_id,
               guild_name,
               signup_channel_id,
               signup_message_id,
               admin_channel_id,
               move_panel_channel_id,
               move_panel_message_id
        FROM guild_settings
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def save_guild_settings(
    guild_id: int,
    guild_name: str,
    signup_channel_id: Optional[int] = None,
    signup_message_id: Optional[int] = None,
    admin_channel_id: Optional[int] = None,
) -> None:
    """Create or update neutral guild settings."""
    _ensure_guild_settings_table()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO guild_settings (
            guild_id,
            guild_name,
            signup_channel_id,
            signup_message_id,
            admin_channel_id
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            guild_name = excluded.guild_name,
            signup_channel_id = COALESCE(excluded.signup_channel_id, guild_settings.signup_channel_id),
            signup_message_id = COALESCE(excluded.signup_message_id, guild_settings.signup_message_id),
            admin_channel_id = COALESCE(excluded.admin_channel_id, guild_settings.admin_channel_id),
            updated_at = CURRENT_TIMESTAMP
        """,
        (guild_id, guild_name, signup_channel_id, signup_message_id, admin_channel_id),
    )
    conn.commit()


def update_guild_channel(guild_id: int, channel_type: str, channel_id: int) -> bool:
    """Update a configured channel for a guild."""
    _ensure_guild_settings_table()
    column_map = {
        "signup": "signup_channel_id",
        "admin": "admin_channel_id",
    }
    column = column_map.get(channel_type)
    if not column:
        raise ValueError(f"Invalid channel_type: {channel_type}")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        UPDATE guild_settings
        SET {column} = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (channel_id, guild_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_all_configured_guilds() -> list:
    """Return all configured guild settings."""
    _ensure_guild_settings_table()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT guild_id,
               guild_name,
               signup_channel_id,
               signup_message_id,
               admin_channel_id,
               move_panel_channel_id,
               move_panel_message_id
        FROM guild_settings
        ORDER BY guild_name COLLATE NOCASE
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def update_signup_message_id(guild_id: int, message_id: int) -> bool:
    """Store the active raid signup message ID for a guild."""
    _ensure_guild_settings_table()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE guild_settings
        SET signup_message_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (message_id, guild_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_move_panel_ids(guild_id: int) -> Optional[tuple]:
    """Return saved move panel channel/message IDs for a guild."""
    settings = get_guild_settings(guild_id)
    if not settings:
        return None

    channel_id = settings.get("move_panel_channel_id")
    message_id = settings.get("move_panel_message_id")
    if channel_id and message_id:
        return (channel_id, message_id)
    return None


def update_move_panel_ids(guild_id: int, channel_id: int, message_id: int) -> bool:
    """Save or update the move panel channel/message IDs for a guild."""
    _ensure_guild_settings_table()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE guild_settings
        SET move_panel_channel_id = ?, move_panel_message_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
        """,
        (channel_id, message_id, guild_id),
    )
    conn.commit()
    return cursor.rowcount > 0
