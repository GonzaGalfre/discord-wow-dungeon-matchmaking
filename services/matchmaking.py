"""
Matchmaking service for the WoW Mythic+ LFG Bot.

This module contains all the business logic for matching players
based on their roles, key ranges, and party composition rules.

Multi-guild support: Matchmaking is now guild-aware.
"""

from typing import Dict, List, Optional, Tuple

from config.settings import PARTY_COMPOSITION
from models.queue import queue_manager
from services.queue_preferences import normalize_roles, requires_keystone_for_range


def is_valid_composition(users: List[dict]) -> bool:
    """
    Verify if a group of users/groups forms a valid M+ composition.
    
    A valid composition doesn't exceed the limits:
    - Maximum 1 Tank
    - Maximum 1 Healer
    - Maximum 3 DPS
    
    Supports both solo entries (with "role") and groups (with "composition").
    
    Args:
        users: List of users/groups with their role or composition info
        
    Returns:
        True if the composition is valid, False otherwise
        
    Examples:
        >>> is_valid_composition([{"role": "tank"}, {"role": "healer"}])
        True
        >>> is_valid_composition([{"composition": {"tank": 1, "healer": 1, "dps": 2}}])
        True
        >>> is_valid_composition([{"role": "tank"}, {"role": "tank"}])
        False  # 2 tanks is invalid
    """
    return resolve_role_assignments(users) is not None


def get_entry_roles(entry: dict) -> List[str]:
    """
    Return ordered role preferences for a solo entry.
    """
    return normalize_roles(roles=entry.get("roles"), role=entry.get("role"))


def _entry_assignment_key(entry: dict, index: int) -> str:
    """
    Stable key for tracking resolved roles in temporary matchmaking groups.
    """
    user_id = entry.get("user_id")
    if user_id is not None:
        return str(user_id)
    return f"idx:{index}"


def resolve_role_assignments(users: List[dict]) -> Optional[Dict[str, str]]:
    """
    Resolve one role per solo entry while respecting party composition limits.
    """
    fixed_counts = {"tank": 0, "healer": 0, "dps": 0}
    variable_entries = []

    for idx, user in enumerate(users):
        composition = user.get("composition")
        if composition:
            for role, count in composition.items():
                if role in fixed_counts:
                    fixed_counts[role] += count
            continue

        roles = get_entry_roles(user)
        if not roles:
            return None
        variable_entries.append((idx, user, roles))

    for role, count in fixed_counts.items():
        if count > PARTY_COMPOSITION[role]:
            return None

    # Lower branching factor first.
    variable_entries.sort(key=lambda item: len(item[2]))
    assigned: Dict[str, str] = {}

    def _backtrack(position: int, running_counts: Dict[str, int]) -> bool:
        if position >= len(variable_entries):
            return True

        idx, entry, roles = variable_entries[position]
        entry_key = _entry_assignment_key(entry, idx)

        for role in roles:
            if running_counts[role] >= PARTY_COMPOSITION[role]:
                continue
            running_counts[role] += 1
            assigned[entry_key] = role
            if _backtrack(position + 1, running_counts):
                return True
            running_counts[role] -= 1
            assigned.pop(entry_key, None)
        return False

    if not _backtrack(0, dict(fixed_counts)):
        return None
    return assigned


def get_role_counts(users: List[dict]) -> Dict[str, int]:
    """
    Count how many slots of each role are present in total.
    
    Supports both solo entries (with "role") and groups (with "composition").
    - Solo: has "role" (string) → counts as 1 of that role
    - Group: has "composition" (dict) → sums the dict values
    
    Args:
        users: List of users/groups
        
    Returns:
        Dictionary with total count of each role
    """
    counts = {"tank": 0, "healer": 0, "dps": 0}
    assignments = resolve_role_assignments(users)

    for idx, user in enumerate(users):
        composition = user.get("composition")
        if composition:
            # It's a group: sum the full composition
            for role, count in composition.items():
                if role in counts:
                    counts[role] += count
        else:
            # It's solo: add 1 to resolved role
            key = _entry_assignment_key(user, idx)
            role = assignments.get(key) if assignments else None
            if not role:
                roles = get_entry_roles(user)
                role = roles[0] if roles else None
            if role in counts:
                counts[role] += 1

    return counts


def group_requires_keystone(users: List[dict]) -> bool:
    """
    Return True if group's common range includes Mythic+ 2 or higher.
    """
    common_min, common_max = calculate_common_range(users)
    return requires_keystone_for_range(common_min, common_max)


def group_has_keystone(users: List[dict]) -> bool:
    """
    Return True when at least one queue entry provides a keystone.
    """
    return any(bool(entry.get("has_keystone")) for entry in users)


def is_valid_keystone_requirement(users: List[dict]) -> bool:
    """
    Keystone rule: if group range includes 2+, at least one member must have a key.
    """
    if not group_requires_keystone(users):
        return True
    return group_has_keystone(users)


def is_group_entry(entry: dict) -> bool:
    """
    Check if a queue entry is a group.
    
    Args:
        entry: Queue entry
        
    Returns:
        True if it's a group (has composition), False if solo
    """
    return entry.get("composition") is not None


def get_entry_player_count(entry: dict) -> int:
    """
    Get the total number of players that an entry represents.
    
    Args:
        entry: Queue entry
        
    Returns:
        Number of players (1 for solo, sum of composition for group)
    """
    composition = entry.get("composition")
    if composition:
        return sum(composition.values())
    return 1


def ranges_overlap(range1: Tuple[int, int], range2: Tuple[int, int]) -> bool:
    """
    Check if two key ranges overlap.
    
    Two ranges [a, b] and [c, d] overlap if max(a,c) <= min(b,d)
    
    Args:
        range1: Tuple (min, max) of the first range
        range2: Tuple (min, max) of the second range
        
    Returns:
        True if there's overlap, False otherwise
        
    Examples:
        >>> ranges_overlap((9, 11), (10, 14))  # Overlap at 10-11
        True
        >>> ranges_overlap((2, 5), (10, 15))   # No overlap
        False
        >>> ranges_overlap((5, 10), (8, 12))   # Overlap at 8-10
        True
    """
    min1, max1 = range1
    min2, max2 = range2
    return max(min1, min2) <= min(max1, max2)


def get_overlapping_range(
    range1: Tuple[int, int], 
    range2: Tuple[int, int]
) -> Optional[Tuple[int, int]]:
    """
    Calculate the overlapping range between two ranges.
    
    Args:
        range1: Tuple (min, max) of the first range
        range2: Tuple (min, max) of the second range
        
    Returns:
        Tuple (min, max) of the overlap, or None if no overlap
    """
    if not ranges_overlap(range1, range2):
        return None
    
    min1, max1 = range1
    min2, max2 = range2
    return (max(min1, min2), min(max1, max2))


def get_users_with_overlap(guild_id: int, key_min: int, key_max: int, new_user_id: int) -> List[dict]:
    """
    Find entries in the guild's queue with overlapping range AND valid group composition.
    
    NEW BEHAVIOR: Tries to join existing incomplete matches before forming new groups.
    
    Strategy:
    1. Check if new user can join any existing incomplete match (< 5 players)
    2. If yes, return that match + new user
    3. If no, form a new group with available players (no match_message_id)
    
    This allows matches to grow (2 → 3 → 4 → 5 players) while preventing
    players from being in multiple different matches.
    
    Args:
        guild_id: Discord guild ID
        key_min: Minimum key level being searched
        key_max: Maximum key level being searched
        new_user_id: ID of the user/leader who just joined (to include first)
        
    Returns:
        List of entries that form a valid group with overlapping ranges
    """
    target_range = (key_min, key_max)
    
    # Start with the new user
    if not queue_manager.contains(guild_id, new_user_id):
        return []
    
    new_user_data = queue_manager.get(guild_id, new_user_id)
    
    # STEP 1: Try to join an existing incomplete match
    existing_match = try_join_existing_match(guild_id, new_user_id, new_user_data, target_range)
    if existing_match:
        return existing_match
    
    # STEP 2: Form a new group with available players (no active match)
    matched_group = [{"user_id": new_user_id, **new_user_data}]
    
    # Search for other compatible users in the same guild
    for user_id, data in queue_manager.items(guild_id):
        if user_id == new_user_id:
            continue  # Already in the group
        
        # Skip users who already have an active match
        if data.get("match_message_id") is not None:
            continue
        
        user_range = (data["key_min"], data["key_max"])
        
        # Check range overlap
        if not ranges_overlap(target_range, user_range):
            continue
        
        # Create temporary group to verify composition
        potential_user = {"user_id": user_id, **data}
        temp_group = matched_group + [potential_user]
        
        # Only add if composition remains valid
        if is_valid_composition(temp_group) and is_valid_keystone_requirement(temp_group):
            matched_group.append(potential_user)
    
    return matched_group


def try_join_existing_match(
    guild_id: int, 
    new_user_id: int, 
    new_user_data: dict,
    target_range: Tuple[int, int]
) -> Optional[List[dict]]:
    """
    Try to add new user to an existing incomplete match.
    
    Searches for matches that:
    - Have compatible key ranges
    - Have < 5 total players
    - Would still have valid composition with new user
    - Share the same match_message_id
    
    If multiple matches are possible, picks the first one found (oldest match).
    
    Args:
        guild_id: Discord guild ID
        new_user_id: ID of the new user
        new_user_data: Queue data for the new user
        target_range: Key range tuple (min, max)
        
    Returns:
        List of entries forming the updated match, or None if can't join any
    """
    # Group all entries by their match_message_id
    matches = {}  # {match_message_id: [entries]}
    
    for user_id, data in queue_manager.items(guild_id):
        if user_id == new_user_id:
            continue
        
        match_id = data.get("match_message_id")
        if match_id is None:
            continue  # Not in a match
        
        if match_id not in matches:
            matches[match_id] = []
        
        matches[match_id].append({"user_id": user_id, **data})
    
    # Try each existing match
    for match_id, match_entries in matches.items():
        # Check if match is incomplete (< 5 players)
        total_players = count_total_players(match_entries)
        if total_players >= 5:
            continue  # Match is full
        
        # Check if all entries in match have overlapping ranges with new user
        all_overlap = all(
            ranges_overlap(
                target_range,
                (entry["key_min"], entry["key_max"])
            )
            for entry in match_entries
        )
        if not all_overlap:
            continue  # Ranges don't work
        
        # Check if adding new user keeps composition valid
        new_user_entry = {"user_id": new_user_id, **new_user_data}
        potential_match = match_entries + [new_user_entry]
        
        if is_valid_composition(potential_match) and is_valid_keystone_requirement(potential_match):
            # This match works! Return it
            return potential_match
    
    # No existing match can accept this player
    return None


def calculate_common_range(users: List[dict]) -> Tuple[int, int]:
    """
    Calculate the common range where ALL users overlap.
    
    Args:
        users: List of users with their ranges
        
    Returns:
        Tuple (min, max) of the common range
    """
    from config.settings import MIN_KEY_LEVEL, MAX_KEY_LEVEL
    
    if not users:
        return (MIN_KEY_LEVEL, MAX_KEY_LEVEL)
    
    # Common range is max of mins and min of maxs
    common_min = max(u["key_min"] for u in users)
    common_max = min(u["key_max"] for u in users)
    
    return (common_min, common_max)


def count_total_players(entries: List[dict]) -> int:
    """
    Count the total number of players represented by a list of entries.
    
    Args:
        entries: List of queue entries (can be solo players or groups)
        
    Returns:
        Total number of players
    """
    total = 0
    for entry in entries:
        total += get_entry_player_count(entry)
    return total


def find_all_independent_groups(guild_id: int) -> List[List[dict]]:
    """
    Find all possible independent groups from the current queue.
    
    This function tries to form multiple complete groups (5 players) or
    partial groups (2+ players) that don't share any players.
    
    Priority:
    1. Complete groups (exactly 5 players) with valid composition
    2. Larger partial groups (closer to 5)
    3. Groups without active matches
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        List of groups, where each group is a list of entries
    """
    # Get all queue entries without active matches
    available_entries = []
    for user_id, data in queue_manager.items(guild_id):
        # Skip entries that already have an active match
        if data.get("match_message_id") is None:
            available_entries.append({"user_id": user_id, **data})
    
    if len(available_entries) < 2:
        return []
    
    # Try to form groups greedily
    # Sort by timestamp (oldest first) to be fair
    available_entries.sort(key=lambda x: x["timestamp"])
    
    groups = []
    used_indices = set()
    
    # Try to form groups starting with each available entry
    for i, entry in enumerate(available_entries):
        if i in used_indices:
            continue
        
        # Start a new group with this entry
        current_group = [entry]
        current_group_indices = {i}
        
        # Try to add more compatible entries
        for j, other_entry in enumerate(available_entries):
            if j in used_indices or j in current_group_indices:
                continue
            
            # Check if this entry is compatible
            # 1. Range must overlap with ALL current group members
            ranges_compatible = all(
                ranges_overlap(
                    (other_entry["key_min"], other_entry["key_max"]),
                    (member["key_min"], member["key_max"])
                )
                for member in current_group
            )
            
            if not ranges_compatible:
                continue
            
            # 2. Composition must remain valid
            temp_group = current_group + [other_entry]
            if not is_valid_composition(temp_group):
                continue
            
            # 3. Must not exceed 5 players
            if count_total_players(temp_group) > 5:
                continue
            
            # Add this entry to the group
            current_group.append(other_entry)
            current_group_indices.add(j)
            
            # If we have exactly 5 players, this group is complete
            if count_total_players(current_group) == 5:
                break
        
        # Only add groups with at least 2 players worth of entries
        if count_total_players(current_group) >= 2 and is_valid_keystone_requirement(current_group):
            groups.append(current_group)
            used_indices.update(current_group_indices)
    
    return groups
