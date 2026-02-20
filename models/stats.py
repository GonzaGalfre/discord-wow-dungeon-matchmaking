"""
Stats model for the WoW Mythic+ LFG Bot.

This module handles database operations for tracking completed keys
and player statistics.

Multi-guild support: Stats can be queried globally or per-guild.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from models.database import get_connection, get_role_id


# UTC-3 timezone for reset calculations
UTC_MINUS_3 = timezone(timedelta(hours=-3))

# Reset day and time (Tuesday 12:00 PM UTC-3)
RESET_WEEKDAY = 1  # Monday=0, Tuesday=1, ...
RESET_HOUR = 12


def get_current_week_number() -> int:
    """
    Get the current week number based on WoW reset schedule.
    
    Week changes on Tuesday at 12:00 PM UTC-3.
    
    Returns:
        Integer week number (ISO week adjusted for reset time)
    """
    now = datetime.now(UTC_MINUS_3)
    
    # Calculate the most recent reset time
    days_since_reset = (now.weekday() - RESET_WEEKDAY) % 7
    
    # If it's Tuesday but before 12:00, we're still in the previous week
    if now.weekday() == RESET_WEEKDAY and now.hour < RESET_HOUR:
        days_since_reset = 7
    
    last_reset = now - timedelta(days=days_since_reset)
    last_reset = last_reset.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    
    # Use ISO calendar year and week
    iso_cal = last_reset.isocalendar()
    # Combine year and week for unique identification
    return iso_cal[0] * 100 + iso_cal[1]


def get_week_start_end(week_number: int) -> Tuple[datetime, datetime]:
    """
    Get the start and end datetime for a given week number.
    
    Args:
        week_number: Week number in format YYYYWW
        
    Returns:
        Tuple of (start_datetime, end_datetime) in UTC-3
    """
    year = week_number // 100
    week = week_number % 100
    
    # Get the first day of this ISO week
    jan_4 = datetime(year, 1, 4, tzinfo=UTC_MINUS_3)
    start_of_week_1 = jan_4 - timedelta(days=jan_4.weekday())
    week_start = start_of_week_1 + timedelta(weeks=week - 1)
    
    # Adjust to Tuesday 12:00
    days_to_tuesday = (RESET_WEEKDAY - week_start.weekday()) % 7
    reset_start = week_start + timedelta(days=days_to_tuesday)
    reset_start = reset_start.replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)
    
    reset_end = reset_start + timedelta(weeks=1)
    
    return reset_start, reset_end


def record_completed_key(
    key_level: int,
    participants: List[Dict],
    guild_id: Optional[int] = None
) -> int:
    """
    Record a completed key with all participants.
    
    Args:
        key_level: The M+ key level completed
        participants: List of dicts with user_id, username, and optionally role
                     For groups, role may be None or a composition dict
        guild_id: Discord guild ID (for multi-guild tracking)
        
    Returns:
        The ID of the created key record
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    week_number = get_current_week_number()
    
    # Insert the completed key
    cursor.execute("""
        INSERT INTO completed_keys (guild_id, key_level, week_number)
        VALUES (?, ?, ?)
    """, (guild_id, key_level, week_number))
    
    key_id = cursor.lastrowid
    
    # Insert participants
    for participant in participants:
        user_id = participant["user_id"]
        username = participant["username"]
        
        # Handle solo players (have role string)
        role = participant.get("role")
        composition = participant.get("composition")
        
        if role and not composition:
            # Solo player with a specific role
            role_id = get_role_id(role)
            cursor.execute("""
                INSERT INTO key_participants (key_id, user_id, username, role_id)
                VALUES (?, ?, ?, ?)
            """, (key_id, user_id, username, role_id))
        elif composition:
            # Group - add multiple entries based on composition
            for role_name, count in composition.items():
                role_id = get_role_id(role_name)
                for _ in range(count):
                    cursor.execute("""
                        INSERT INTO key_participants (key_id, user_id, username, role_id)
                        VALUES (?, ?, ?, ?)
                    """, (key_id, user_id, username, role_id))
        else:
            # Unknown role
            cursor.execute("""
                INSERT INTO key_participants (key_id, user_id, username, role_id)
                VALUES (?, ?, ?, NULL)
            """, (key_id, user_id, username))
    
    conn.commit()
    return key_id


def get_weekly_stats(week_number: Optional[int] = None, guild_id: Optional[int] = None) -> Dict:
    """
    Get statistics for a specific week.
    
    Args:
        week_number: Week to get stats for (default: current week)
        guild_id: Filter by guild (None for global stats)
        
    Returns:
        Dict with total_keys, top_player, player_counts, etc.
    """
    if week_number is None:
        week_number = get_current_week_number()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build WHERE clause based on guild_id
    if guild_id is not None:
        week_filter = "WHERE week_number = ? AND guild_id = ?"
        week_params = (week_number, guild_id)
        join_filter = "WHERE ck.week_number = ? AND ck.guild_id = ?"
        join_params = (week_number, guild_id)
    else:
        week_filter = "WHERE week_number = ?"
        week_params = (week_number,)
        join_filter = "WHERE ck.week_number = ?"
        join_params = (week_number,)
    
    # Get total keys completed this week
    cursor.execute(f"""
        SELECT COUNT(*) as total
        FROM completed_keys
        {week_filter}
    """, week_params)
    total_keys = cursor.fetchone()["total"]
    
    # Get key count per player (unique participations)
    cursor.execute(f"""
        SELECT 
            kp.user_id,
            kp.username,
            COUNT(DISTINCT kp.key_id) as key_count
        FROM key_participants kp
        JOIN completed_keys ck ON kp.key_id = ck.id
        {join_filter}
        GROUP BY kp.user_id
        ORDER BY key_count DESC
    """, join_params)
    
    player_stats = [dict(row) for row in cursor.fetchall()]
    
    # Get average key level
    cursor.execute(f"""
        SELECT AVG(key_level) as avg_level, MAX(key_level) as max_level
        FROM completed_keys
        {week_filter}
    """, week_params)
    level_stats = cursor.fetchone()
    
    return {
        "week_number": week_number,
        "guild_id": guild_id,
        "total_keys": total_keys,
        "player_stats": player_stats,
        "top_player": player_stats[0] if player_stats else None,
        "avg_key_level": round(level_stats["avg_level"], 1) if level_stats["avg_level"] else 0,
        "max_key_level": level_stats["max_level"] or 0,
    }


def get_all_time_stats(guild_id: Optional[int] = None) -> Dict:
    """
    Get all-time statistics.
    
    Args:
        guild_id: Filter by guild (None for global stats)
    
    Returns:
        Dict with total keys, top players, etc.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build WHERE clause based on guild_id
    if guild_id is not None:
        where_clause = "WHERE guild_id = ?"
        where_params = (guild_id,)
        join_clause = "WHERE ck.guild_id = ?"
        join_params = (guild_id,)
    else:
        where_clause = ""
        where_params = ()
        join_clause = ""
        join_params = ()
    
    # Get total keys completed all time
    cursor.execute(f"SELECT COUNT(*) as total FROM completed_keys {where_clause}", where_params)
    total_keys = cursor.fetchone()["total"]
    
    # Get key count per player (all time)
    if guild_id is not None:
        cursor.execute(f"""
            SELECT 
                kp.user_id,
                kp.username,
                COUNT(DISTINCT kp.key_id) as key_count
            FROM key_participants kp
            JOIN completed_keys ck ON kp.key_id = ck.id
            {join_clause}
            GROUP BY kp.user_id
            ORDER BY key_count DESC
            LIMIT 10
        """, join_params)
    else:
        cursor.execute("""
            SELECT 
                kp.user_id,
                kp.username,
                COUNT(DISTINCT kp.key_id) as key_count
            FROM key_participants kp
            GROUP BY kp.user_id
            ORDER BY key_count DESC
            LIMIT 10
        """)
    
    top_players = [dict(row) for row in cursor.fetchall()]
    
    # Get average and max key level
    cursor.execute(f"""
        SELECT AVG(key_level) as avg_level, MAX(key_level) as max_level
        FROM completed_keys
        {where_clause}
    """, where_params)
    level_stats = cursor.fetchone()
    
    return {
        "guild_id": guild_id,
        "total_keys": total_keys,
        "top_players": top_players,
        "avg_key_level": round(level_stats["avg_level"], 1) if level_stats["avg_level"] else 0,
        "max_key_level": level_stats["max_level"] or 0,
    }


def get_player_stats(user_id: int, guild_id: Optional[int] = None) -> Dict:
    """
    Get statistics for a specific player.
    
    Args:
        user_id: Discord user ID
        guild_id: Filter by guild (None for global stats)
        
    Returns:
        Dict with player's key count, favorite role, etc.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build guild filter
    if guild_id is not None:
        join_filter = "AND ck.guild_id = ?"
        join_params_base = (user_id, guild_id)
    else:
        join_filter = ""
        join_params_base = (user_id,)
    
    # Get total keys for this player
    if guild_id is not None:
        cursor.execute(f"""
            SELECT COUNT(DISTINCT kp.key_id) as total
            FROM key_participants kp
            JOIN completed_keys ck ON kp.key_id = ck.id
            WHERE kp.user_id = ? AND ck.guild_id = ?
        """, (user_id, guild_id))
    else:
        cursor.execute("""
            SELECT COUNT(DISTINCT key_id) as total
            FROM key_participants
            WHERE user_id = ?
        """, (user_id,))
    total_keys = cursor.fetchone()["total"]
    
    # Get keys this week
    week_number = get_current_week_number()
    if guild_id is not None:
        cursor.execute(f"""
            SELECT COUNT(DISTINCT kp.key_id) as total
            FROM key_participants kp
            JOIN completed_keys ck ON kp.key_id = ck.id
            WHERE kp.user_id = ? AND ck.week_number = ? AND ck.guild_id = ?
        """, (user_id, week_number, guild_id))
    else:
        cursor.execute("""
            SELECT COUNT(DISTINCT kp.key_id) as total
            FROM key_participants kp
            JOIN completed_keys ck ON kp.key_id = ck.id
            WHERE kp.user_id = ? AND ck.week_number = ?
        """, (user_id, week_number))
    weekly_keys = cursor.fetchone()["total"]
    
    # Get favorite role (global, not filtered by guild)
    cursor.execute("""
        SELECT r.display_name, r.emoji, COUNT(*) as count
        FROM key_participants kp
        JOIN roles r ON kp.role_id = r.id
        WHERE kp.user_id = ?
        GROUP BY kp.role_id
        ORDER BY count DESC
        LIMIT 1
    """, (user_id,))
    role_row = cursor.fetchone()
    favorite_role = dict(role_row) if role_row else None
    
    # Get highest key level
    if guild_id is not None:
        cursor.execute(f"""
            SELECT MAX(ck.key_level) as max_level
            FROM key_participants kp
            JOIN completed_keys ck ON kp.key_id = ck.id
            WHERE kp.user_id = ? AND ck.guild_id = ?
        """, (user_id, guild_id))
    else:
        cursor.execute("""
            SELECT MAX(ck.key_level) as max_level
            FROM key_participants kp
            JOIN completed_keys ck ON kp.key_id = ck.id
            WHERE kp.user_id = ?
        """, (user_id,))
    max_level = cursor.fetchone()["max_level"] or 0
    
    return {
        "user_id": user_id,
        "guild_id": guild_id,
        "total_keys": total_keys,
        "weekly_keys": weekly_keys,
        "favorite_role": favorite_role,
        "max_key_level": max_level,
    }


def get_previous_week_number() -> int:
    """
    Get the previous week's number.
    
    Returns:
        Week number for the previous week
    """
    current = get_current_week_number()
    year = current // 100
    week = current % 100
    
    if week == 1:
        # Go to last week of previous year
        return (year - 1) * 100 + 52
    else:
        return year * 100 + (week - 1)
