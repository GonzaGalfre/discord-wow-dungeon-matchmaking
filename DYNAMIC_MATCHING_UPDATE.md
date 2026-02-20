# Dynamic Matching Update

## What Changed

The matchmaking system has been upgraded to allow **incomplete matches to grow** while still preventing duplicate group membership.

## Old Behavior (❌ Problematic)

```
1. Tank joins → waiting
2. Healer joins → MATCH formed (2 players, match_id: 123)
   Both locked with match_message_id = 123
3. DPS1 joins → searches queue
   Finds Tank+Healer but SKIPS them (have match_message_id)
   Waits alone
4. DPS2 joins → same, waits alone
5. DPS3 joins → same, waits alone

Result: One 2-player match, three solo players waiting ❌
```

## New Behavior (✅ Better!)

```
1. Tank joins → waiting
2. Healer joins → MATCH formed (2 players, match_id: 123)
3. DPS1 joins → searches queue
   Finds existing match (Tank+Healer)
   JOINS that match → old message deleted, new message created
   All 3 now have match_message_id = 456
4. DPS2 joins → finds the 3-player match
   JOINS that match → message updated again
   All 4 now have match_message_id = 789
5. DPS3 joins → finds the 4-player match
   JOINS that match → complete group of 5! ✅

Result: One complete 5-player group!
```

## Key Features

### 1. **Matches Can Grow**
- 2 players → 3 players → 4 players → 5 players
- Old match message is deleted
- New match message created with updated composition
- All players get the new match_message_id

### 2. **No Duplicate Group Membership**
- Players can only be in ONE match at a time
- Identified by having the same `match_message_id`
- Different matches have different message IDs

### 3. **Multiple Independent Groups**
```
Match 1: Tank1 + Healer1 (match_id: 100)
Match 2: Tank2 + Healer2 (match_id: 200)

DPS1 joins → has compatible range with both matches
Algorithm picks Match 1 (first found)
DPS1 joins Match 1 → now 3 players (new match_id: 300)

Match 1: Tank1 + Healer1 + DPS1 (match_id: 300)
Match 2: Tank2 + Healer2 (match_id: 200)  ← Still independent
```

### 4. **Smart Selection**
When multiple matches could accept a player:
- Picks the **first eligible match** found
- This ensures fairness (older matches get priority)
- Future: Could be enhanced with better logic (e.g., prefer matches closer to 5 players)

## Technical Implementation

### New Function: `try_join_existing_match()`

Located in `services/matchmaking.py`:

```python
def try_join_existing_match(
    guild_id: int, 
    new_user_id: int, 
    new_user_data: dict,
    target_range: Tuple[int, int]
) -> Optional[List[dict]]:
    """
    Try to add new user to an existing incomplete match.
    
    Returns the updated match if successful, None otherwise.
    """
```

**Logic:**
1. Groups all queue entries by `match_message_id`
2. For each existing match:
   - Check if < 5 total players
   - Check if ranges overlap
   - Check if composition stays valid with new player
3. Returns first compatible match, or None

### Modified Function: `get_users_with_overlap()`

Now has two-step strategy:

```python
def get_users_with_overlap(...):
    # STEP 1: Try to join existing match
    existing_match = try_join_existing_match(...)
    if existing_match:
        return existing_match
    
    # STEP 2: Form new group with available players
    # (original logic)
```

### View Updates

Both `role_selection.py` and `group_selection.py` now:
1. Detect if joining an existing match
2. Show appropriate user feedback
3. Delete old match messages
4. Create new match message
5. Update `match_message_id` for all players

## Testing Scenarios

### Scenario 1: Growing a Match

```bash
/dev_clear_queue
/dev_add_player nombre:Tank rol:tank key_min:10 key_max:15
/dev_add_player nombre:Healer rol:healer key_min:10 key_max:15
# Match 1 formed: Tank + Healer (2 players)

/dev_queue_state
# Both should have match_message_id

/dev_add_player nombre:DPS1 rol:dps key_min:10 key_max:15
# DPS1 should JOIN existing match → old message deleted, new one created

/dev_queue_state
# All 3 should have the SAME (new) match_message_id

/dev_add_player nombre:DPS2 rol:dps key_min:10 key_max:15
/dev_add_player nombre:DPS3 rol:dps key_min:10 key_max:15
# Match grows to 5 players
```

**Expected:** One match message that updates as players join (old deleted, new created).

### Scenario 2: Multiple Independent Groups

```bash
/dev_clear_queue
/dev_add_player nombre:Tank1 rol:tank key_min:10 key_max:15
/dev_add_player nombre:Healer1 rol:healer key_min:10 key_max:15
# Match 1: Tank1 + Healer1

/dev_add_player nombre:Tank2 rol:tank key_min:10 key_max:15
/dev_add_player nombre:Healer2 rol:healer key_min:10 key_max:15
# Match 2: Tank2 + Healer2

/dev_queue_state
# Should see 2 different match_message_id values

/dev_add_player nombre:DPS1 rol:dps key_min:10 key_max:15
# DPS1 joins Match 1 (first eligible)

/dev_queue_state
# Match 1: 3 players (Tank1 + Healer1 + DPS1), one match_message_id
# Match 2: 2 players (Tank2 + Healer2), different match_message_id
```

**Expected:** Two independent matches, DPS1 joins the first one.

### Scenario 3: Can't Join Full Match

```bash
# Setup: Create a full 5-player match
/dev_clear_queue
/dev_add_player nombre:Tank rol:tank key_min:10 key_max:15
/dev_add_player nombre:Healer rol:healer key_min:10 key_max:15
/dev_add_player nombre:DPS1 rol:dps key_min:10 key_max:15
/dev_add_player nombre:DPS2 rol:dps key_min:10 key_max:15
/dev_add_player nombre:DPS3 rol:dps key_min:10 key_max:15
# Match: 5 players (full)

/dev_add_player nombre:DPS4 rol:dps key_min:10 key_max:15
# DPS4 can't join (match is full)

/dev_queue_state
# Match: 5 players with match_message_id
# DPS4: waiting alone, no match_message_id
```

**Expected:** DPS4 waits alone, full match stays as-is.

### Scenario 4: Composition Validation

```bash
/dev_clear_queue
/dev_add_player nombre:Tank1 rol:tank key_min:10 key_max:15
/dev_add_player nombre:Healer rol:healer key_min:10 key_max:15
# Match: Tank1 + Healer

/dev_add_player nombre:Tank2 rol:tank key_min:10 key_max:15
# Tank2 can't join (would have 2 tanks = invalid)

/dev_queue_state
# Match: Tank1 + Healer (2 players)
# Tank2: waiting alone
```

**Expected:** Tank2 waits alone, can't violate composition rules.

## User Experience Improvements

### Feedback Messages

Players now see different messages:

**Joining new match:**
```
🎉 ¡Nuevo grupo formado con 3 jugadores!
```

**Joining existing match:**
```
🎉 ¡Te has unido a un grupo existente!
```

### Match Message Updates

When a player joins an existing match:
1. Old match message disappears (deleted)
2. New match message appears immediately
3. All players see updated composition
4. Everyone is mentioned in the new message (notification)

## Edge Cases Handled

### 1. **Match Between Joins**
If a match forms while a player is selecting their role:
- Player completes selection
- `get_users_with_overlap()` finds the match
- Player joins that match (if compatible)

### 2. **Simultaneous Joins**
If two players join at nearly the same time:
- Both check for existing matches
- First one might form a new match
- Second one joins that new match
- Or both form separate matches if incompatible

### 3. **Group Joining Match**
A pre-made group can join an existing match:
```
Match: Tank + Healer (2 players)
Group joins: 3 DPS
Result: Complete 5-player group!
```

### 4. **Player Leaves Incomplete Match**
```
Match: Tank + Healer + DPS1 (3 players)
DPS1 clicks "Salir de Cola"
Result: Match updates to Tank + Healer (2 players)
```

Note: Currently, leaving doesn't auto-update the match message. The match message becomes stale but buttons handle it gracefully by checking if players are still in queue.

## Future Enhancements

### 1. **Smart Match Selection**
Instead of "first match found", could prioritize:
- Matches closest to 5 players
- Matches with best role fit
- Oldest/newest matches

### 2. **Match Message Updates on Leave**
When someone leaves a match with 3+ players remaining:
- Don't delete the match
- Update the match message to show new composition
- Keep remaining players together

### 3. **Match Preferences**
Allow players to:
- Prefer joining existing matches vs forming new ones
- Set maximum group size they're comfortable with
- Request specific compositions

### 4. **Match Expiration**
Auto-dissolve matches that have been incomplete for too long:
- E.g., 2-player match older than 30 minutes
- Release players back to "waiting" state

## Compatibility

### Real Players
✅ Works exactly as before, just grows matches dynamically

### Fake Players (Dev Commands)
✅ Updated to support growing matches
✅ `auto_match: True` (default) simulates real player behavior

### Existing Matches
✅ No migration needed
✅ Queue is in-memory, so restart = clean slate

## Performance

**Impact:** Minimal
- One additional function call (`try_join_existing_match`)
- Complexity: O(M × P) where M = number of existing matches, P = players per match
- Typical case: M ≤ 5 matches, P ≤ 5 players = negligible

## Summary

This update makes the matchmaking system **much more user-friendly** by allowing matches to grow naturally from 2 → 3 → 4 → 5 players, while still maintaining the critical guarantee that **no player can be in multiple groups simultaneously**.

The implementation is clean, backward-compatible, and handles all edge cases gracefully. 🎉
