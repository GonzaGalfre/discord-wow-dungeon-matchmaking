# Development Mode Guide

## Overview

Testing multi-user scenarios in Discord bots is challenging without multiple accounts. The dev mode provides admin-only commands to simulate multiple users and inspect internal bot state.

## Available Commands

All dev commands are prefixed with `dev_` and are **admin-only**.

### 🎮 Player Simulation

#### `/dev_add_player`
Add a fake solo player to the queue.

**Parameters:**
- `nombre` - Name for the fake player (e.g., "Alice")
- `rol` - Role (Tank/Healer/DPS)
- `key_min` - Minimum key level (2-20)
- `key_max` - Maximum key level (2-20)

**Example:**
```
/dev_add_player nombre:Alice rol:tank key_min:5 key_max:10
```

#### `/dev_add_group`
Add a fake group to the queue.

**Parameters:**
- `nombre` - Group leader name (e.g., "BobGroup")
- `tanks` - Number of tanks (0-1)
- `healers` - Number of healers (0-1)
- `dps` - Number of DPS (0-3)
- `key_min` - Minimum key level (2-20)
- `key_max` - Maximum key level (2-20)

**Example:**
```
/dev_add_group nombre:BobGroup tanks:1 healers:0 dps:2 key_min:8 key_max:12
```

#### `/dev_simulate_scenario`
Create a complete test scenario with predefined players.

**Available Scenarios:**

1. **Simple Match** - 2 players with overlapping ranges
   - Alice (Tank, 5-10)
   - Bob (Healer, 5-10)

2. **Multiple Independent Groups** - Should form 2 separate matches
   - Alice (Tank, 5-10) + Bob (Healer, 5-10)
   - Charlie (DPS, 8-15) + Diana (DPS, 8-15)

3. **Complex Composition** - Full 5-player group
   - 1 Tank, 1 Healer, 3 DPS (all 10-15)

4. **No Overlapping** - Players who shouldn't match
   - LowKey (2-5), MidKey (8-12), HighKey (15-20)

### 🔍 Inspection

#### `/dev_queue_state`
View detailed internal state of the queue.

**Shows:**
- All entries with their user IDs
- Whether they have active matches (match_message_id)
- Their roles/compositions
- Key ranges
- Entry type (Solo/Group)

**Example Output:**
```
Entrada #1
├ ID: 900000000000000001
├ Tipo: Solo
├ Rol: 🛡️ Tanque
├ Llaves: 5-10
└ Estado: ✓ Match: 123456789
```

#### `/cola`
View the queue as a normal user would see it (standard command).

### ⚙️ Actions

#### `/dev_force_match`
Force matchmaking for all available players.

This simulates what happens when a new player joins - it searches for compatible players without active matches and creates match notifications.

**When to use:**
- After adding fake players
- Testing matchmaking logic
- Verifying multiple independent groups form correctly

#### `/dev_remove_player`
Remove a specific player by their user ID.

**Parameters:**
- `user_id` - The user ID (get this from `/dev_queue_state`)

**Example:**
```
/dev_remove_player user_id:900000000000000001
```

#### `/dev_clear_queue`
Clear the entire queue for the current server.

**⚠️ Warning:** This removes ALL entries, including real players!

### ℹ️ Help

#### `/dev_info`
Display information about all dev commands.

Shows a comprehensive guide with examples and recommended workflow.

---

## Testing Workflows

### Workflow 1: Test Basic Matching

**Goal:** Verify that two players form a match correctly.

```
1. /dev_clear_queue                          # Start fresh
2. /dev_add_player nombre:Alice rol:tank key_min:5 key_max:10
3. /dev_add_player nombre:Bob rol:healer key_min:5 key_max:10
4. /dev_queue_state                          # Verify both in queue, no matches
5. /dev_force_match                          # Create the match
6. Check match notification in channel       # Both should be mentioned
7. /dev_queue_state                          # Both should have match_message_id
```

**Expected:** Match notification appears with Alice and Bob.

---

### Workflow 2: Test Multiple Independent Groups (Bug Fix)

**Goal:** Verify players can't be in multiple groups simultaneously.

```
1. /dev_clear_queue
2. /dev_simulate_scenario escenario:Múltiples Grupos Independientes
3. /dev_queue_state                          # 4 players, no matches
4. /dev_force_match                          # Should create 2 matches
5. /dev_queue_state                          # All 4 should have match_message_id
6. Check both match messages                 # Should be independent
```

**Expected:**
- Match 1: Alice + Bob
- Match 2: Charlie + Diana
- NO player appears in both matches

---

### Workflow 3: Test Match Dissolution

**Goal:** Verify players can re-match after their match is dissolved.

```
1. /dev_clear_queue
2. /dev_add_player nombre:Alice rol:tank key_min:5 key_max:10
3. /dev_add_player nombre:Bob rol:healer key_min:5 key_max:10
4. /dev_force_match                          # Match 1: Alice + Bob
5. /dev_queue_state                          # Both have match_message_id
6. /dev_remove_player user_id:<Bob's ID>     # Simulate Bob leaving
7. /dev_queue_state                          # Alice should have match_message_id cleared
8. /dev_add_player nombre:Charlie rol:healer key_min:5 key_max:10
9. /dev_force_match                          # Should create Match 2: Alice + Charlie
```

**Expected:** Alice can be matched again after Bob left (and message was deleted because <2 players).

**Note:** Currently `dev_remove_player` doesn't auto-clear match_message_id. You'll need to manually test with the "Salir de Cola" button or observe in real usage.

---

### Workflow 4: Test Complex Composition

**Goal:** Verify full 5-player groups form correctly.

```
1. /dev_clear_queue
2. /dev_simulate_scenario escenario:Composición Compleja
3. /dev_queue_state                          # 5 players, no matches
4. /dev_force_match                          # Should create 1 match with all 5
5. Check match notification                  # All 5 should be mentioned
```

**Expected:** One match with 1 Tank, 1 Healer, 3 DPS.

---

### Workflow 5: Mix Fake and Real Players

**Goal:** Test with a combination of fake and real users.

```
1. /dev_clear_queue
2. /dev_add_player nombre:FakeAlice rol:tank key_min:5 key_max:10
3. <Real user> clicks "Join Queue" → Healer, 5-10
4. /dev_queue_state                          # Should see both fake and real
5. /dev_force_match                          # Match should form
6. Check match notification                  # Fake user shown as `FakeAlice`, real user as mention
```

**Expected:** Match notification includes both fake player (by name) and real player (mentioned).

---

## Identifying Fake vs Real Players

### In Queue State
- **Fake Players:** User ID > 900000000000000000
- **Real Players:** User ID < 900000000000000000

### In Match Messages
- **Fake Players:** Shown as `` `Username` `` (backticks, no mention)
- **Real Players:** Shown as `<@UserID>` (proper mention)

### Match Messages
- Dev-created matches are prefixed with `[DEV MATCH]` in the content

---

## Important Notes

### Match Message Cleanup
- Match messages are NOT automatically deleted when you clear the queue
- They remain visible but their buttons will gracefully handle missing players
- Consider manually deleting old test matches to keep channels clean

### Mixing with Real Users
- ✅ You CAN mix fake and real players in the same queue
- ✅ Fake players will appear in normal queue views (`/cola`)
- ⚠️ Real users might get confused seeing fake usernames - communicate with your testers!

### Production Use
- These commands are admin-only for safety
- Consider creating a dedicated test server
- Or use a dedicated test channel in production
- Clear fake players before going fully live

### Limitations
- Fake players can't click buttons (they're not real Discord users)
- To test button interactions, you'll still need real accounts or alts
- Match confirmations won't work with fake players (buttons require interaction)
- Use fake players primarily for testing matchmaking logic, not full flows

---

## Testing the Bug Fixes

### Test Case: Players Can't Be in Multiple Groups

**Before the fix:** If Alice and Bob have a match, and Charlie joins, Charlie might get matched WITH Alice and Bob, creating a duplicate.

**After the fix:**

```
1. /dev_clear_queue
2. /dev_add_player nombre:Alice rol:tank key_min:5 key_max:10
3. /dev_add_player nombre:Bob rol:healer key_min:5 key_max:10
4. /dev_force_match                          # Match 1: Alice + Bob
5. /dev_queue_state                          # Both have match_message_id
6. /dev_add_player nombre:Charlie rol:dps key_min:5 key_max:10
7. /dev_force_match                          # Charlie should NOT match with Alice/Bob
8. /dev_queue_state                          # Charlie has NO match_message_id
```

**Expected:** Charlie waits alone. Alice and Bob stay in their original match.

---

### Test Case: Multiple Groups Form Simultaneously

**Before the fix:** Only one big group would form.

**After the fix:**

```
1. /dev_clear_queue
2. Add 4 players with overlapping ranges (2 tanks + 2 healers)
3. /dev_force_match
4. Should create 2 independent matches: Tank1+Healer1, Tank2+Healer2
```

---

## Troubleshooting

### "No players found" when forcing match
- Check `/dev_queue_state` - are players already in matches?
- Players with `match_message_id` set won't be matched again
- Use `/dev_clear_queue` and re-add players

### Match messages not appearing
- Check guild configuration with `/verconfig`
- Ensure match channel is set (or it falls back to current channel)
- Check bot permissions in the match channel

### Can't remove fake players
- Get the exact user ID from `/dev_queue_state`
- Copy the entire number (900000000000000XXX)
- Use `/dev_remove_player user_id:<paste ID here>`

### Real players mixed with fake players
- This is OK! It's a feature for testing
- Real players can interact normally
- Fake players just sit in queue and matches

---

## Quick Reference

**Common Workflow:**
```
/dev_clear_queue          → Start fresh
/dev_simulate_scenario    → Create test players
/dev_queue_state          → Verify setup
/dev_force_match          → Create matches
/cola                     → View as user
/dev_clear_queue          → Clean up
```

**Inspection Stack:**
```
/dev_queue_state          → Internal view (admin)
/cola                     → User view
Check match channel       → See match messages
```

**Cleanup Stack:**
```
/dev_remove_player        → Remove one
/dev_clear_queue          → Remove all
[Manual delete]           → Match messages
```

---

## Safety Tips

1. **Test in a dedicated channel** - Don't confuse real users
2. **Communicate with testers** - Let them know you're adding fake players
3. **Clear fake players** - Before live demos or real usage
4. **Label test matches** - Dev matches are auto-labeled `[DEV MATCH]`
5. **Don't rely on fake players for button tests** - They can't interact

---

## Examples for Common Bugs

### Bug: Player in multiple groups
```bash
# Setup
/dev_add_player nombre:A rol:tank key_min:5 key_max:10
/dev_add_player nombre:B rol:healer key_min:5 key_max:10
/dev_force_match  # Match 1 created

# Try to reproduce bug
/dev_add_player nombre:C rol:dps key_min:5 key_max:10
/dev_force_match  # Should NOT add C to Match 1

# Verify fix
/dev_queue_state  # A and B have match_message_id, C doesn't
```

### Bug: Match not clearing after dissolution
```bash
# Setup
/dev_add_player nombre:A rol:tank key_min:5 key_max:10
/dev_add_player nombre:B rol:healer key_min:5 key_max:10
/dev_force_match

# Simulate one leaving
Click "Salir de Cola" button in match message

# Verify fix
/dev_queue_state  # Remaining player should have match_message_id cleared
```

---

## Need More Help?

Run `/dev_info` in Discord for a quick command reference.

For code-level debugging, check:
- `models/queue.py` - Queue state management
- `services/matchmaking.py` - Matching logic
- `views/party.py` - Match button handlers
