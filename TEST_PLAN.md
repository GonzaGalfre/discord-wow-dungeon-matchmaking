# Test Plan for Multiple Group Membership Fix

## Overview
This test plan verifies the fixes for preventing players from being in multiple groups simultaneously and ensuring multiple independent groups can exist.

## Pre-requisites
- Bot is running and connected to Discord
- `/setup` has been run in a test channel
- At least 5 test accounts available (or use multiple devices/browsers)

## Test Cases

### TC1: Basic Match Formation
**Objective**: Verify that basic matching still works

**Steps**:
1. User A clicks "Join Queue"
2. Select Solo → Tank → Keys 5-10
3. User B clicks "Join Queue"  
4. Select Solo → Healer → Keys 5-10

**Expected Result**:
- Match notification appears with User A and User B
- Both users are mentioned
- "Grupo Completo" and "Salir de Cola" buttons visible

**Status**: [ ]

---

### TC2: Players Cannot Be In Multiple Matches (Core Fix)
**Objective**: Verify players with active matches are excluded from new matches

**Steps**:
1. User A joins (Tank, 5-10) → waiting
2. User B joins (Healer, 5-10) → Match 1 formed (A+B)
3. User C joins (DPS, 5-10)
4. Check if User C is matched with A and B

**Expected Result**:
- User C sees "waiting for others" message
- User C is NOT added to Match 1 (A+B remain in their original match)
- No new match notification is sent to A and B
- Use `/cola` to verify: A and B should NOT show in queue (they're in a match), C should show as waiting

**Status**: [ ]

---

### TC3: Multiple Independent Groups Can Form
**Objective**: Verify multiple separate groups can exist simultaneously

**Steps**:
1. User A joins (Tank, 5-10) → waiting
2. User B joins (Healer, 5-10) → Match 1 formed (A+B)
3. User C joins (DPS, 5-10) → waiting
4. User D joins (DPS, 5-10) → Match 2 should form (C+D)
5. Check both match messages

**Expected Result**:
- Match 1 exists with User A and User B
- Match 2 exists with User C and User D
- Both matches are visible and independent
- Use `/cola` to verify: No users should appear (all are in matches)

**Status**: [ ]

---

### TC4: Match State Cleared When Dissolved
**Objective**: Verify players can re-match after their match is dissolved

**Steps**:
1. User A joins (Tank, 5-10) → waiting
2. User B joins (Healer, 5-10) → Match 1 formed (A+B)
3. User B clicks "Salir de Cola" on the match message
4. Match message should disappear (less than 2 players)
5. User C joins (Healer, 5-10)

**Expected Result**:
- After User B leaves, the match message is deleted
- User A can be matched with User C (new match forms)
- Match 2 notification appears with User A and User C

**Status**: [ ]

---

### TC5: Cannot Join Queue While In Active Match
**Objective**: Verify players cannot accidentally create duplicate entries

**Steps**:
1. User A joins (Tank, 5-10) → waiting
2. User B joins (Healer, 5-10) → Match 1 formed (A+B)
3. User A clicks "Join Queue" button again

**Expected Result**:
- Error message appears: "⚠️ Ya estás en un grupo activo"
- Message suggests using "Salir de Cola" or `/salir`
- User A remains in Match 1 (no duplicate entry created)

**Status**: [ ]

---

### TC6: Rejection With Multiple Players Remaining
**Objective**: Verify match continues when someone rejects but enough players remain

**Steps**:
1. User A joins (Tank, 5-10)
2. User B joins (Healer, 5-10)
3. User C joins (DPS, 5-10) → Match formed (A+B+C)
4. User A clicks "Grupo Completo"
5. User B clicks "Rechazar"

**Expected Result**:
- User B is removed from queue
- Match message is recreated with User A and User C
- User A and User C see updated match notification
- Use `/cola` to verify: Only A and C should appear (B is gone)

**Status**: [ ]

---

### TC7: Rejection With Not Enough Players
**Objective**: Verify match is dissolved when rejection leaves less than 2 players

**Steps**:
1. User A joins (Tank, 5-10)
2. User B joins (Healer, 5-10) → Match formed (A+B)
3. User A clicks "Grupo Completo"
4. User B clicks "Rechazar"

**Expected Result**:
- User B is removed from queue
- Match message is deleted (less than 2 players)
- User A receives DM about rejection
- User A's match_message_id is cleared (can be matched again)
- Use `/cola` to verify: User A should appear as waiting

**Status**: [ ]

---

### TC8: Leave Queue Via Command
**Objective**: Verify `/salir` command works with helpful messaging

**Steps**:
1. User A joins (Tank, 5-10)
2. User B joins (Healer, 5-10) → Match formed (A+B)
3. User A uses `/salir` command

**Expected Result**:
- User A receives confirmation message
- Message includes note about using the button for better UX
- User A is removed from queue
- Match message still exists (stale, but buttons will handle gracefully)

**Status**: [ ]

---

### TC9: Group Queue Still Works
**Objective**: Verify group queueing wasn't broken by the fixes

**Steps**:
1. User A clicks "Join Queue"
2. Select "Grupo" → 1 Tank, 1 Healer, 1 DPS → Keys 5-10
3. User B joins (Solo, DPS, 5-10)

**Expected Result**:
- Match formed with User A's group (3 players) + User B (1 player)
- Match notification shows composition correctly
- All functionality works as expected

**Status**: [ ]

---

### TC10: Overlapping Key Ranges
**Objective**: Verify range matching still works correctly

**Steps**:
1. User A joins (Tank, 5-10)
2. User B joins (Healer, 8-15)
3. User C joins (DPS, 2-6)

**Expected Result**:
- Match forms with User A and User B (overlap: 8-10)
- User C does NOT match with them (range 2-6 doesn't overlap enough)
- User C waits alone

**Status**: [ ]

---

## Regression Tests

### R1: Queue Viewing
- Use `/cola` at various points to ensure queue display is accurate
- Verify players in active matches don't show incorrect states

### R2: Stats Recording
- Complete a full match (all confirm)
- Verify stats are recorded correctly with `/mystats`

### R3: Match Notifications
- Verify all players in a match receive mentions
- Verify match embeds show correct information

### R4: Button Interactions
- Test all buttons (Confirmar, Rechazar, Grupo Completo, Salir de Cola)
- Verify they work when players are/aren't in queue

---

## Edge Cases

### E1: Bot Restart
**Note**: Queue is in-memory, so it will be empty after restart. This is expected behavior.

### E2: Message Manually Deleted
If an admin manually deletes a match message:
- Players still have match_message_id set
- They cannot be matched again until they leave queue
- Workaround: They can use `/salir` to reset their state

### E3: Rapid Joining
Multiple users joining within seconds:
- Each should form independent matches or wait
- No race conditions should occur

---

## Success Criteria

All test cases (TC1-TC10) must pass:
- [ ] TC1: Basic Match Formation
- [ ] TC2: Players Cannot Be In Multiple Matches
- [ ] TC3: Multiple Independent Groups Can Form
- [ ] TC4: Match State Cleared When Dissolved
- [ ] TC5: Cannot Join Queue While In Active Match
- [ ] TC6: Rejection With Multiple Players Remaining
- [ ] TC7: Rejection With Not Enough Players
- [ ] TC8: Leave Queue Via Command
- [ ] TC9: Group Queue Still Works
- [ ] TC10: Overlapping Key Ranges

All regression tests must pass:
- [ ] R1: Queue Viewing
- [ ] R2: Stats Recording
- [ ] R3: Match Notifications
- [ ] R4: Button Interactions

## Notes
- Mark each test case as [ ] (not tested), [x] (passed), or [!] (failed)
- Document any failures in detail
- For failed tests, attach screenshots if possible
