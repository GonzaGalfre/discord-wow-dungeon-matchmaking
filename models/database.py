"""SQLite database connection and schema initialization for WipyBot."""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

# Database file path (same directory as the project)
DATABASE_PATH = Path(__file__).parent.parent / "bot_data.db"

# Thread-local connections (one connection per thread)
_thread_local = threading.local()

# Schema initialization guard (shared across threads)
_schema_lock = threading.Lock()
_schema_initialized = False


def get_connection() -> sqlite3.Connection:
    """
    Get the database connection, creating it if needed.
    
    Uses a singleton pattern to reuse the same connection.
    
    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row
    """
    conn = getattr(_thread_local, "connection", None)

    if conn is None:
        # Each thread uses its own connection to avoid concurrent cursor misuse.
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Access columns by name
        conn.execute("PRAGMA foreign_keys = ON")  # Enable FK constraints
        _thread_local.connection = conn

    global _schema_initialized
    if not _schema_initialized:
        with _schema_lock:
            if not _schema_initialized:
                _init_schema(conn)
                _schema_initialized = True

    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """
    Initialize the database schema if tables don't exist.
    
    Schema:
    - guild_settings: Per-guild channel/message configuration.
    - raid_events: Raid signup messages created by admins.
    - raid_signups: Per-user attendance/class/spec selections.
    """
    cursor = conn.cursor()

    # Guild settings table
    cursor.execute("""
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
    """)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raid_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER UNIQUE,
            title TEXT NOT NULL,
            leader_name TEXT,
            starts_at TEXT NOT NULL,
            created_by_user_id INTEGER NOT NULL,
            is_open INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("PRAGMA table_info(raid_events)")
    raid_event_columns = {row[1] for row in cursor.fetchall()}
    if "external_id" not in raid_event_columns:
        cursor.execute("ALTER TABLE raid_events ADD COLUMN external_id TEXT")
    for column in (
        "confirmed_roster_json",
        "bench_roster_json",
        "roster_publish_channel_id",
        "roster_publish_requested_at",
        "roster_published_at",
    ):
        if column not in raid_event_columns:
            cursor.execute(f"ALTER TABLE raid_events ADD COLUMN {column} TEXT")

    cursor.execute("SELECT id FROM raid_events WHERE external_id IS NULL OR external_id = ''")
    missing_external_ids = [row[0] for row in cursor.fetchall()]
    for event_id in missing_external_ids:
        cursor.execute(
            "UPDATE raid_events SET external_id = ? WHERE id = ?",
            (f"discord-{event_id}", event_id),
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raid_signups (
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL,
            class_key TEXT,
            spec_key TEXT,
            note TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (event_id, user_id),
            FOREIGN KEY (event_id) REFERENCES raid_events(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_raid_events_guild
        ON raid_events(guild_id)
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_raid_events_external
        ON raid_events(external_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_raid_events_message
        ON raid_events(message_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_raid_signups_event_status
        ON raid_signups(event_id, status)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS participation_settings (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            eligible_role_ids TEXT NOT NULL DEFAULT '[]',
            officer_role_ids TEXT NOT NULL DEFAULT '[]',
            tracked_voice_channel_ids TEXT NOT NULL DEFAULT '[]',
            tracked_text_channel_ids TEXT NOT NULL DEFAULT '[]',
            first_voice_minutes_per_ticket INTEGER NOT NULL DEFAULT 15,
            voice_minutes_per_ticket INTEGER NOT NULL DEFAULT 60,
            messages_per_ticket INTEGER NOT NULL DEFAULT 10,
            message_cooldown_seconds INTEGER NOT NULL DEFAULT 30,
            max_voice_tickets INTEGER NOT NULL DEFAULT 10,
            max_message_tickets INTEGER NOT NULL DEFAULT 0,
            raffle_period_days INTEGER NOT NULL DEFAULT 14,
            panel_channel_id INTEGER,
            panel_message_id INTEGER,
            panel_update_minutes INTEGER NOT NULL DEFAULT 10,
            panel_last_updated_at TEXT,
            raffle_publish_channel_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("PRAGMA table_info(participation_settings)")
    participation_columns = {row[1] for row in cursor.fetchall()}
    participation_extra_columns = {
        "first_voice_minutes_per_ticket": "INTEGER NOT NULL DEFAULT 15",
        "panel_channel_id": "INTEGER",
        "panel_message_id": "INTEGER",
        "panel_update_minutes": "INTEGER NOT NULL DEFAULT 10",
        "panel_last_updated_at": "TEXT",
        "raffle_publish_channel_id": "INTEGER",
    }
    for column, definition in participation_extra_columns.items():
        if column not in participation_columns:
            cursor.execute(f"ALTER TABLE participation_settings ADD COLUMN {column} {definition}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_seconds INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (ended_at IS NULL OR ended_at >= started_at),
            CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_voice_open_guild_user
        ON voice_sessions(guild_id, user_id)
        WHERE ended_at IS NULL
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_voice_guild_user_started
        ON voice_sessions(guild_id, user_id, started_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_voice_guild_ended
        ON voice_sessions(guild_id, ended_at)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS counted_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_message_id INTEGER NOT NULL UNIQUE,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_guild_user_created
        ON counted_messages(guild_id, user_id, created_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_guild_channel_created
        ON counted_messages(guild_id, channel_id, created_at)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raffle_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            status TEXT NOT NULL,
            closed_at TEXT,
            drawn_at TEXT,
            winner_user_id INTEGER,
            total_tickets_at_draw INTEGER,
            winning_number INTEGER,
            CHECK (ends_at > starts_at),
            CHECK (status IN ('OPEN', 'CLOSED', 'DRAWN'))
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_period_open_guild
        ON raffle_periods(guild_id)
        WHERE status = 'OPEN'
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_period_guild_range
        ON raffle_periods(guild_id, starts_at, ends_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_period_guild_status
        ON raffle_periods(guild_id, status)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raffle_entry_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raffle_period_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            voice_seconds INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            voice_tickets INTEGER NOT NULL,
            message_tickets INTEGER NOT NULL,
            total_tickets INTEGER NOT NULL,
            cumulative_ticket_start INTEGER NOT NULL,
            cumulative_ticket_end INTEGER NOT NULL,
            CHECK (voice_seconds >= 0),
            CHECK (message_count >= 0),
            CHECK (voice_tickets >= 0),
            CHECK (message_tickets >= 0),
            CHECK (total_tickets > 0),
            CHECK (cumulative_ticket_start > 0 AND cumulative_ticket_end >= cumulative_ticket_start),
            FOREIGN KEY (raffle_period_id) REFERENCES raffle_periods(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshot_period_user
        ON raffle_entry_snapshots(raffle_period_id, user_id)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raffle_debug_tickets (
            raffle_period_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            tickets INTEGER NOT NULL,
            PRIMARY KEY (raffle_period_id, user_id),
            CHECK (tickets > 0),
            FOREIGN KEY (raffle_period_id) REFERENCES raffle_periods(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raffle_exclusive_winners (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raffle_action_receipts (
            action_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            result_json TEXT NOT NULL,
            processed_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raffle_draw_publications (
            raffle_period_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            published_at TEXT,
            FOREIGN KEY (raffle_period_id) REFERENCES raffle_periods(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vip_voice_channels (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, channel_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vip_voice_panels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vip_voice_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            requester_user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            decided_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            decided_at TEXT,
            CHECK (status IN ('PENDING', 'ACCEPTED', 'DENIED', 'EXPIRED'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_vip_requests_status_expires
        ON vip_voice_requests(guild_id, status, expires_at)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vip_voice_request_notifications (
            request_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (request_id, user_id),
            FOREIGN KEY (request_id) REFERENCES vip_voice_requests(id) ON DELETE CASCADE
        )
    """)

    conn.commit()


def close_connection() -> None:
    """Close the database connection if open."""
    conn = getattr(_thread_local, "connection", None)
    if conn is not None:
        conn.close()
        _thread_local.connection = None
