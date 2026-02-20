# Quick Test Guide

## 🚀 Quick Start - Test the Bug Fixes in 2 Minutes

### Test 1: Players Can't Be in Multiple Groups (THE MAIN BUG)

```bash
# 1. Start fresh
/dev_clear_queue

# 2. Create first match
/dev_simulate_scenario escenario:Escenario 1: Match Simple (2 jugadores)
/dev_force_match
# ✓ You should see Match 1 with Alice + Bob

# 3. Try to add a third player
/dev_add_player nombre:Charlie rol:dps key_min:5 key_max:10
/dev_force_match

# 4. Check the result
/dev_queue_state
```

**✅ EXPECTED (Bug Fixed):**
- Alice and Bob have `match_message_id` (in Match 1)
- Charlie has NO `match_message_id` (waiting alone)
- Only ONE match message exists

**❌ OLD BEHAVIOR (Bug Present):**
- All three would be in the same match
- OR a new match would be created with all three
- Players would appear in multiple matches

---

### Test 2: Multiple Independent Groups Can Form

```bash
# 1. Start fresh
/dev_clear_queue

# 2. Create scenario with 4 players
/dev_simulate_scenario escenario:Escenario 2: Múltiples Grupos Independientes

# 3. Force matching
/dev_force_match

# 4. Check results
/dev_queue_state
# Look for TWO different match_message_id values
```

**✅ EXPECTED (Bug Fixed):**
- Match 1: Alice (Tank 5-10) + Bob (Healer 5-10)
- Match 2: Charlie (DPS 8-15) + Diana (DPS 8-15)
- TWO separate match messages
- Each player in exactly ONE match

**❌ OLD BEHAVIOR (Bug Present):**
- Only one match with all 4 players
- OR matches would keep getting rebuilt

---

## 🎯 Verify Real User Behavior

### Test 3: Real User Can't Join While in Active Match

```bash
# 1. Setup
/dev_clear_queue
/dev_add_player nombre:FakeAlice rol:tank key_min:5 key_max:10

# 2. YOU join as a real user
Click "Join Queue" → Healer → 5-10
# A match should form with you and FakeAlice

# 3. Try to join again while in the match
Click "Join Queue" again
```

**✅ EXPECTED:**
- Error message: "Ya estás en un grupo activo"
- Suggests using "Salir de Cola" button

---

## 🧪 Full Scenario Test (5 minutes)

Complete walkthrough testing all features:

```bash
# === SETUP ===
/dev_clear_queue

# === PHASE 1: Simple Match ===
/dev_add_player nombre:Tank1 rol:tank key_min:5 key_max:10
/dev_add_player nombre:Healer1 rol:healer key_min:5 key_max:10
/dev_force_match
# → Should create Match 1

# === PHASE 2: Try to add to existing match ===
/dev_add_player nombre:DPS1 rol:dps key_min:5 key_max:10
/dev_force_match
# → DPS1 should NOT be added to Match 1
# → DPS1 should wait alone

/dev_queue_state
# → Tank1 and Healer1: have match_message_id
# → DPS1: no match_message_id

# === PHASE 3: Form second independent match ===
/dev_add_player nombre:DPS2 rol:dps key_min:5 key_max:10
/dev_force_match
# → Should create Match 2 with DPS1 + DPS2

/dev_queue_state
# → All 4 players should have match_message_id
# → But TWO different message IDs (two separate matches)

# === PHASE 4: Cleanup ===
/dev_clear_queue
```

---

## 🔍 Inspection Commands

During any test, use these to check state:

```bash
/dev_queue_state      # Internal state (IDs, match_message_id, etc.)
/cola                 # User view (what players see)
```

**Key things to look for in `/dev_queue_state`:**

```
Estado: ✓ Match: 123456789  ← Player is in an active match
Estado: ✗ No match          ← Player is waiting (can be matched)
```

---

## 🐛 Reproduce Specific Bugs

### Bug: Player appears in multiple match messages

**How it happened before:**
1. Alice + Bob form Match 1
2. Charlie joins
3. System creates Match 2 with Alice + Bob + Charlie
4. Now Alice and Bob are in BOTH Match 1 and Match 2 ❌

**Test it's fixed:**
```bash
/dev_clear_queue
/dev_add_player nombre:Alice rol:tank key_min:5 key_max:10
/dev_add_player nombre:Bob rol:healer key_min:5 key_max:10
/dev_force_match  # Match 1 created

# Now Alice and Bob should be "locked" (have match_message_id)
/dev_add_player nombre:Charlie rol:dps key_min:5 key_max:10
/dev_force_match  # Should NOT create a match including Alice/Bob

/dev_queue_state  # Alice and Bob should still only be in Match 1
```

---

### Bug: Match not clearing when someone leaves

**How it happened before:**
1. Alice + Bob form a match
2. Bob clicks "Salir de Cola"
3. Alice still has `match_message_id` set
4. Charlie joins
5. Alice can't be matched with Charlie ❌

**Test it's fixed:**
```bash
# This requires button interaction, so use real users or:
# 1. Create a match with 2 fake players
# 2. Click "Salir de Cola" on the match message
# 3. Use /dev_queue_state to verify remaining player's match_message_id is cleared
```

**Note:** Full testing of this bug requires clicking the "Salir de Cola" button, which fake players can't do. Use a real alt account or ask a tester to help.

---

## ✅ Success Criteria Checklist

After running tests, verify:

- [ ] Players with active matches are NOT included in new matches
- [ ] Multiple independent match messages can exist simultaneously
- [ ] Each player appears in at most ONE match message
- [ ] `/dev_queue_state` shows different `match_message_id` values for different matches
- [ ] Real users get an error when trying to join while in an active match
- [ ] When a match has <2 players, the match_message_id is cleared for remaining players

---

## 🆘 Something Wrong?

### If tests fail:

1. **Check bot version**: Make sure you've restarted the bot after pulling the latest code
2. **Check files**: Ensure all the bug fix files were updated:
   - `services/matchmaking.py`
   - `views/party.py`
   - `views/join_queue.py`
   - `cogs/lfg.py`

3. **Check logs**: Look for error messages in the console

4. **Clear everything**: Sometimes state gets weird
   ```bash
   /dev_clear_queue
   Restart bot
   Try again
   ```

### If dev commands don't appear:

- Make sure `cogs/dev.py` exists
- Check that `bot.py` has `await self.load_extension("cogs.dev")`
- Restart the bot
- Wait a few minutes for Discord to sync commands
- You must be an administrator

---

## 💡 Tips

- **Use a test server** if possible - easier to manage
- **Create a dedicated #testing channel** for dev commands
- **Mix fake and real users** - it's totally fine!
- **Check match messages visually** - easier to spot issues than just looking at IDs
- **Take screenshots** - useful for documenting bugs if you find any

---

## 📝 Report Issues

If you find bugs in the fix:

1. Note which test case failed
2. Run `/dev_queue_state` and screenshot it
3. Screenshot the match message(s)
4. Note what you expected vs what happened
5. Check `BUGFIX_SUMMARY.md` to see if it's a known limitation

---

## Next Steps

Once basic tests pass, try:
- Full flow testing with real users and the confirmation buttons
- Edge cases (what if someone leaves mid-confirmation?)
- Stress testing (10+ players)
- See `TEST_PLAN.md` for comprehensive test cases
