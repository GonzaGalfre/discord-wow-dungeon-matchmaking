"""
Guild settings model for the WoW Mythic+ LFG Bot.

This module handles per-guild configuration storage.
Each guild can have its own LFG, match, and announcement channels.
"""

from typing import Dict, Optional

from models.database import get_connection


def _ensure_guild_settings_table() -> None:
    """
    Ensure the guild_settings table exists.
    
    Called automatically when needed.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
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
    
    conn.commit()


def get_guild_settings(guild_id: int) -> Optional[Dict]:
    """
    Get the settings for a specific guild.
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        Dict with guild settings, or None if not configured
    """
    _ensure_guild_settings_table()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT guild_id, guild_name, lfg_channel_id, match_channel_id, announcement_channel_id
        FROM guild_settings
        WHERE guild_id = ?
    """, (guild_id,))
    
    row = cursor.fetchone()
    return dict(row) if row else None


def save_guild_settings(
    guild_id: int,
    guild_name: str,
    lfg_channel_id: Optional[int] = None,
    match_channel_id: Optional[int] = None,
    announcement_channel_id: Optional[int] = None
) -> None:
    """
    Save or update guild settings.
    
    Args:
        guild_id: Discord guild ID
        guild_name: Guild name for reference
        lfg_channel_id: Channel where the LFG button is posted
        match_channel_id: Channel where match notifications are posted
        announcement_channel_id: Channel for weekly announcements
    """
    _ensure_guild_settings_table()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if guild exists
    cursor.execute("SELECT guild_id FROM guild_settings WHERE guild_id = ?", (guild_id,))
    exists = cursor.fetchone() is not None
    
    if exists:
        # Update existing
        cursor.execute("""
            UPDATE guild_settings
            SET guild_name = ?,
                lfg_channel_id = COALESCE(?, lfg_channel_id),
                match_channel_id = COALESCE(?, match_channel_id),
                announcement_channel_id = COALESCE(?, announcement_channel_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ?
        """, (guild_name, lfg_channel_id, match_channel_id, announcement_channel_id, guild_id))
    else:
        # Insert new
        cursor.execute("""
            INSERT INTO guild_settings (guild_id, guild_name, lfg_channel_id, match_channel_id, announcement_channel_id)
            VALUES (?, ?, ?, ?, ?)
        """, (guild_id, guild_name, lfg_channel_id, match_channel_id, announcement_channel_id))
    
    conn.commit()


def update_guild_channel(
    guild_id: int,
    channel_type: str,
    channel_id: int
) -> bool:
    """
    Update a specific channel for a guild.
    
    Args:
        guild_id: Discord guild ID
        channel_type: One of 'lfg', 'match', 'announcement'
        channel_id: The new channel ID
        
    Returns:
        True if updated, False if guild not found
    """
    _ensure_guild_settings_table()
    
    column_map = {
        'lfg': 'lfg_channel_id',
        'match': 'match_channel_id',
        'announcement': 'announcement_channel_id',
    }
    
    column = column_map.get(channel_type)
    if not column:
        raise ValueError(f"Invalid channel_type: {channel_type}")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(f"""
        UPDATE guild_settings
        SET {column} = ?, updated_at = CURRENT_TIMESTAMP
        WHERE guild_id = ?
    """, (channel_id, guild_id))
    
    conn.commit()
    return cursor.rowcount > 0


def get_all_configured_guilds() -> list:
    """
    Get all guilds that have been configured.
    
    Returns:
        List of guild settings dicts
    """
    _ensure_guild_settings_table()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT guild_id, guild_name, lfg_channel_id, match_channel_id, announcement_channel_id
        FROM guild_settings
    """)
    
    return [dict(row) for row in cursor.fetchall()]


def get_match_channel_id(guild_id: int) -> Optional[int]:
    """
    Get the match channel ID for a guild.
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        Match channel ID, or None if not configured
    """
    settings = get_guild_settings(guild_id)
    if settings:
        return settings.get("match_channel_id")
    return None


def get_announcement_channel_id(guild_id: int) -> Optional[int]:
    """
    Get the announcement channel ID for a guild.
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        Announcement channel ID, or None if not configured
    """
    settings = get_guild_settings(guild_id)
    if settings:
        return settings.get("announcement_channel_id")
    return None



