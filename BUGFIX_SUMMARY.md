# Bug Fix Summary: Multiple Group Membership Prevention

## Issues Fixed

### 1. Players Could Be In Multiple Groups Simultaneously
**Problem**: When a new player joined the queue, the matchmaking system would create a new match that could include players who were already in an existing match. This resulted in players appearing in multiple match notifications at the same time.

**Root Cause**: The `get_users_with_overlap()` function in `services/matchmaking.py` did not check if players already had an active match before including them in a new match.

**Solution**: Added a check to skip players who already have an active match (identified by `match_message_id` being set).

### 2. Only One Group Active at a Time
**Problem**: The system would constantly rebuild matches as new players joined, causing existing match messages to be deleted and recreated with different player combinations.

**Solution**: Players with active matches are now excluded from new matchmaking, allowing multiple independent groups to exist simultaneously.

### 3. Match State Not Cleared When Group Dissolved
**Problem**: When a match was dissolved (e.g., someone rejected and less than 2 players remained), the remaining players still had their `match_message_id` set, preventing them from being matched again.

**Solution**: When a match has less than 2 players remaining, we now clear the `match_message_id` for all remaining players so they can find new matches.

### 4. Players Could Accidentally Join Multiple Times
**Problem**: Players could click "Join Queue" while already in an active match, which would overwrite their entry and remove them from the existing match without notifying other players.

**Solution**: Added validation to prevent players from re-joining the queue while they have an active match. They must leave the current match first.

## Files Modified

### `services/matchmaking.py`
- Modified `get_users_with_overlap()` to skip players with active matches
- Added `count_total_players()` helper function
- Added `find_all_independent_groups()` for future multi-group support

### `views/party.py`
- Updated `reject_button()` in `ConfirmationView` to clear `match_message_id` when less than 2 players remain
- Updated `leave_queue_button()` in `PartyCompleteView` to clear `match_message_id` when less than 2 players remain

### `views/join_queue.py`
- Added validation in `join_queue_button()` to prevent re-joining while in an active match

### `cogs/lfg.py`
- Updated `/salir` command to provide helpful guidance when leaving an active match

## How It Works Now

### Player States
1. **Not in queue**: No entry in queue
2. **In queue, waiting**: Entry in queue with `match_message_id = None`
3. **In active match**: Entry in queue with `match_message_id = <message_id>`

### Matchmaking Flow
```
Player A joins queue
  → No matches found
  → State: "In queue, waiting" (match_message_id = None)

Player B joins queue
  → Searches for compatible players WITHOUT active matches
  → Finds Player A (no match_message_id)
  → Creates match with A and B
  → Both A and B: State: "In active match" (match_message_id = 1234)

Player C joins queue
  → Searches for compatible players WITHOUT active matches
  → Skips A and B (they have match_message_id)
  → State: "In queue, waiting" (match_message_id = None)

Player D joins queue
  → Searches for compatible players WITHOUT active matches
  → Skips A and B (they have match_message_id)
  → Finds Player C (no match_message_id)
  → Creates match with C and D
  → Both C and D: State: "In active match" (match_message_id = 5678)
```

Now we have two independent groups:
- **Group 1**: Players A and B (match message 1234)
- **Group 2**: Players C and D (match message 5678)

### Match Dissolution
When a player leaves or rejects a match:

**Scenario 1: Enough players remain (2+)**
```
Player A rejects in Group 1 (A, B, C)
  → A is removed from queue
  → B and C still in match (message updated or recreated)
  → B and C keep their match_message_id
```

**Scenario 2: Not enough players remain (<2)**
```
Player A rejects in Group 1 (A, B)
  → A is removed from queue
  → Only B remains (less than 2 players)
  → B's match_message_id is CLEARED
  → B's state changes to "In queue, waiting"
  → Match message is deleted
  → B can now be matched with new players
```

## Testing Scenarios

### Test 1: No More Multiple Groups
1. Alice joins (Tank, 5-10) → waiting
2. Bob joins (Healer, 5-10) → Match 1 formed (Alice + Bob)
3. Charlie joins (DPS, 5-10) → Should NOT be added to Match 1, waiting alone
4. **Expected**: Alice and Bob have one match, Charlie is waiting

### Test 2: Multiple Independent Groups
1. Alice joins (Tank, 5-10) → waiting
2. Bob joins (Healer, 5-10) → Match 1 formed
3. Charlie joins (DPS, 5-10) → waiting
4. David joins (DPS, 5-10) → Match 2 formed (Charlie + David)
5. **Expected**: Match 1 (Alice + Bob) and Match 2 (Charlie + David) exist independently

### Test 3: Match Dissolution and Re-matching
1. Alice joins (Tank, 5-10) → waiting
2. Bob joins (Healer, 5-10) → Match 1 formed
3. Bob rejects → Bob removed, Alice's match_message_id cleared
4. Charlie joins (Healer, 5-10) → Match 2 formed (Alice + Charlie)
5. **Expected**: Alice can be matched again after Bob left

### Test 4: Cannot Join While In Match
1. Alice joins (Tank, 5-10) → waiting
2. Bob joins (Healer, 5-10) → Match 1 formed
3. Alice tries to join again → Should be blocked with message
4. **Expected**: Error message telling Alice to leave current match first

## Future Enhancements

### Batch Matchmaking
The new `find_all_independent_groups()` function in `matchmaking.py` can be used to implement batch matchmaking:
- Instead of matching only when someone joins
- Periodically scan the entire queue
- Form all possible independent groups at once

This would be useful for:
- Scheduled matchmaking events
- "Find all matches" command
- Better utilization of available players

### Match Persistence
Currently, matches are only stored in memory. Future improvements:
- Store active matches in database
- Restore matches after bot restart
- Track match history and duration

## Notes

- The `match_message_id` field is the key indicator of whether a player is in an active match
- Players can still use `/salir` to leave the queue, but are encouraged to use the "Leave Queue" button on match messages for better UX
- Match messages may become stale if players leave via `/salir`, but buttons will handle this gracefully by checking if players are still in queue
