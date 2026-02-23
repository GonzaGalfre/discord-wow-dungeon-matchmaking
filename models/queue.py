"""
Queue management for the WoW Mythic+ LFG Bot.

This module provides the QueueManager class for managing the LFG queue.
The queue stores users/groups that are looking for a Mythic+ group.

Multi-guild support: Each guild has its own separate queue.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from event_logger import log_event
from services.queue_preferences import (
    key_range_to_bracket,
    normalize_roles,
    validate_keystone_input,
    validate_queue_key_range,
)


class QueueManager:
    """
    Manages the LFG queue for Mythic+ matchmaking across multiple guilds.
    
    The queue is organized by guild_id, with each guild having its own
    independent queue. This allows the bot to work with multiple Discord
    servers simultaneously.
    
    Structure:
    {guild_id: {user_id: entry_data, ...}, ...}
    
    Solo entry structure:
    {user_id: {"username": str, "role": str, "composition": None,
               "key_min": int, "key_max": int, "timestamp": datetime,
               "match_message_id": int|None, "match_channel_id": int|None}}
    
    Group entry structure (leader_id as key):
    {leader_id: {"username": str, "role": None, 
                 "composition": {"tank": int, "healer": int, "dps": int},
                 "key_min": int, "key_max": int, "timestamp": datetime,
                 "match_message_id": int|None, "match_channel_id": int|None}}
    
    The match_message_id and match_channel_id track the current match notification
    message so it can be deleted when a new match forms.
    """
    
    def __init__(self):
        """Initialize an empty multi-guild queue."""
        # {guild_id: {user_id: entry_data}}
        self._queues: Dict[int, Dict[int, dict]] = {}
    
    def _get_guild_queue(self, guild_id: int) -> Dict[int, dict]:
        """
        Get or create the queue for a specific guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            The queue dictionary for that guild
        """
        if guild_id not in self._queues:
            self._queues[guild_id] = {}
        return self._queues[guild_id]
    
    def add(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        key_min: int,
        key_max: int,
        role: Optional[str] = None,
        roles: Optional[List[str]] = None,
        composition: Optional[Dict[str, int]] = None,
        has_keystone: bool = False,
        keystone_level: Optional[int] = None,
        key_bracket: Optional[str] = None,
    ) -> None:
        """
        Add or update a user/group in the queue for a specific guild.
        
        If the user already exists, their entry is overwritten.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID (or leader ID for groups)
            username: Display name for notifications
            key_min: Minimum key level
            key_max: Maximum key level
            role: Legacy role for solo players (tank/healer/dps)
            roles: Ordered role preferences for solo players
            composition: Role composition for groups {"tank": n, "healer": n, "dps": n}
            has_keystone: Whether the entry has at least one keystone available
            keystone_level: Keystone level available for this entry
            key_bracket: Optional source bracket label/key
        """
        validate_queue_key_range(key_min, key_max)
        validate_keystone_input(has_keystone, keystone_level)
        normalized_roles = normalize_roles(roles=roles, role=role)
        primary_role = normalized_roles[0] if normalized_roles else None

        queue = self._get_guild_queue(guild_id)
        queue[user_id] = {
            "username": username,
            "role": primary_role,
            "roles": normalized_roles,
            "composition": composition,
            "key_min": key_min,
            "key_max": key_max,
            "key_bracket": key_bracket or key_range_to_bracket(key_min, key_max),
            "has_keystone": has_keystone,
            "keystone_level": keystone_level,
            "timestamp": datetime.now(),
            "match_message_id": None,
            "match_channel_id": None,
        }
        log_event(
            "queue_entry_added_or_updated",
            guild_id=guild_id,
            user_id=user_id,
            username=username,
            role=primary_role,
            roles=normalized_roles,
            composition=composition,
            key_min=key_min,
            key_max=key_max,
            key_bracket=queue[user_id]["key_bracket"],
            has_keystone=has_keystone,
            keystone_level=keystone_level,
            queue_size_after=len(queue),
        )
    
    def remove(self, guild_id: int, user_id: int) -> bool:
        """
        Remove a user/group from the queue for a specific guild.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID to remove
            
        Returns:
            True if the user was removed, False if they weren't in the queue
        """
        queue = self._get_guild_queue(guild_id)
        removed = queue.pop(user_id, None) is not None
        log_event(
            "queue_entry_removed",
            guild_id=guild_id,
            user_id=user_id,
            removed=removed,
            queue_size_after=len(queue),
        )
        return removed
    
    def get(self, guild_id: int, user_id: int) -> Optional[dict]:
        """
        Get a user's queue entry from a specific guild.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID to look up
            
        Returns:
            The user's queue entry, or None if not in queue
        """
        queue = self._get_guild_queue(guild_id)
        return queue.get(user_id)
    
    def set_match_message(
        self,
        guild_id: int,
        user_id: int,
        message_id: int,
        channel_id: int
    ) -> None:
        """
        Set the match message reference for a user.
        
        Called when a match notification is posted to track the message
        so it can be deleted when a new match forms.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            message_id: The match notification message ID
            channel_id: The channel where the message was posted
        """
        queue = self._get_guild_queue(guild_id)
        if user_id in queue:
            queue[user_id]["match_message_id"] = message_id
            queue[user_id]["match_channel_id"] = channel_id
            log_event(
                "match_message_linked_to_entry",
                guild_id=guild_id,
                user_id=user_id,
                message_id=message_id,
                channel_id=channel_id,
            )
    
    def get_match_message(self, guild_id: int, user_id: int) -> Optional[Tuple[int, int]]:
        """
        Get the match message reference for a user.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
            
        Returns:
            Tuple of (message_id, channel_id) or None if no match message
        """
        queue = self._get_guild_queue(guild_id)
        entry = queue.get(user_id)
        if entry and entry.get("match_message_id"):
            return (entry["match_message_id"], entry["match_channel_id"])
        return None
    
    def clear_match_message(self, guild_id: int, user_id: int) -> None:
        """
        Clear the match message reference for a user.
        
        Called after the message has been deleted.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID
        """
        queue = self._get_guild_queue(guild_id)
        if user_id in queue:
            had_match_message = queue[user_id].get("match_message_id")
            queue[user_id]["match_message_id"] = None
            queue[user_id]["match_channel_id"] = None
            log_event(
                "match_message_unlinked_from_entry",
                guild_id=guild_id,
                user_id=user_id,
                had_match_message=had_match_message is not None,
            )
    
    def contains(self, guild_id: int, user_id: int) -> bool:
        """
        Check if a user is in the queue for a specific guild.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID to check
            
        Returns:
            True if the user is in the queue
        """
        queue = self._get_guild_queue(guild_id)
        return user_id in queue

    def touch_timestamp(self, guild_id: int, user_id: int) -> bool:
        """
        Refresh queue timestamp for an entry to "now".

        Useful when user explicitly confirms they want to keep waiting.
        """
        queue = self._get_guild_queue(guild_id)
        if user_id not in queue:
            return False

        queue[user_id]["timestamp"] = datetime.now()
        log_event(
            "queue_entry_timestamp_refreshed",
            guild_id=guild_id,
            user_id=user_id,
        )
        return True
    
    def is_empty(self, guild_id: int) -> bool:
        """
        Check if the queue for a specific guild is empty.
        
        Args:
            guild_id: Discord guild ID
        """
        queue = self._get_guild_queue(guild_id)
        return len(queue) == 0
    
    def count(self, guild_id: int) -> int:
        """
        Get the number of entries in the queue for a specific guild.
        
        Args:
            guild_id: Discord guild ID
        """
        queue = self._get_guild_queue(guild_id)
        return len(queue)
    
    def get_all_entries(self, guild_id: int) -> List[dict]:
        """
        Get all queue entries with their user IDs included for a specific guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            List of entries with "user_id" added to each entry
        """
        queue = self._get_guild_queue(guild_id)
        return [
            {"user_id": user_id, **data}
            for user_id, data in queue.items()
        ]
    
    def clear(self, guild_id: int) -> None:
        """
        Remove all entries from the queue for a specific guild.
        
        Args:
            guild_id: Discord guild ID
        """
        if guild_id in self._queues:
            removed_entries = len(self._queues[guild_id])
            self._queues[guild_id].clear()
            log_event(
                "queue_cleared_for_guild",
                guild_id=guild_id,
                removed_entries=removed_entries,
            )
    
    def clear_all(self) -> None:
        """Remove all entries from all guild queues."""
        removed_entries = self.total_count()
        self._queues.clear()
        log_event(
            "queue_cleared_all_guilds",
            removed_entries=removed_entries,
        )
    
    def items(self, guild_id: int):
        """
        Iterate over (user_id, data) pairs in the queue for a specific guild.
        
        Args:
            guild_id: Discord guild ID
        """
        queue = self._get_guild_queue(guild_id)
        return queue.items()
    
    def get_guild_ids(self) -> List[int]:
        """
        Get all guild IDs that have queues.
        
        Returns:
            List of guild IDs with active queues
        """
        return list(self._queues.keys())
    
    def total_count(self) -> int:
        """
        Get the total number of entries across all guilds.
        
        Returns:
            Total count of all queue entries
        """
        return sum(len(q) for q in self._queues.values())


# Singleton instance - use this throughout the application
queue_manager = QueueManager()
