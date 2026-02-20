"""
Database module for the WoW Mythic+ LFG Bot.

This module handles SQLite database connection and schema initialization.
SQLite is an embedded database - no separate server needed.
"""

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
    - roles: Normalized role definitions (tank, healer, dps)
    - completed_keys: Each M+ key completion (with guild_id)
    - key_participants: Who participated in each key
    - guild_settings: Per-guild channel configuration
    """
    cursor = conn.cursor()
    
    # Roles table (normalized)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            emoji TEXT NOT NULL
        )
    """)
    
    # Insert default roles if not exists
    cursor.execute("""
        INSERT OR IGNORE INTO roles (id, name, display_name, emoji)
        VALUES 
            (1, 'tank', 'Tanque', '🛡️'),
            (2, 'healer', 'Sanador', '💚'),
            (3, 'dps', 'DPS', '⚔️')
    """)
    
    # Guild settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            guild_name TEXT NOT NULL,
            lfg_channel_id INTEGER,
            match_channel_id INTEGER,
            announcement_channel_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Completed keys table (without guild_id initially for migration support)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS completed_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_level INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            week_number INTEGER NOT NULL
        )
    """)
    
    # Key participants table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS key_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            role_id INTEGER,
            FOREIGN KEY (key_id) REFERENCES completed_keys(id) ON DELETE CASCADE,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        )
    """)
    
    # =========================================================================
    # MIGRATION: Add guild_id column to completed_keys if it doesn't exist
    # =========================================================================
    try:
        cursor.execute("SELECT guild_id FROM completed_keys LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        cursor.execute("ALTER TABLE completed_keys ADD COLUMN guild_id INTEGER")
        print("✅ Migrated completed_keys table to add guild_id column")
    
    # =========================================================================
    # CREATE INDEXES (after migration so guild_id exists)
    # =========================================================================
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_completed_keys_week 
        ON completed_keys(week_number)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_completed_keys_guild 
        ON completed_keys(guild_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_completed_keys_guild_week 
        ON completed_keys(guild_id, week_number)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_participants_user 
        ON key_participants(user_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_participants_key 
        ON key_participants(key_id)
    """)
    
    conn.commit()


def close_connection() -> None:
    """Close the database connection if open."""
    conn = getattr(_thread_local, "connection", None)
    if conn is not None:
        conn.close()
        _thread_local.connection = None


def get_role_id(role_name: str) -> Optional[int]:
    """
    Get the role ID for a role name.
    
    Args:
        role_name: Role name (tank, healer, dps)
        
    Returns:
        Role ID or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
    row = cursor.fetchone()
    return row["id"] if row else None
