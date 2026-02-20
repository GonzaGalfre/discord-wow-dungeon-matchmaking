# Dev Mode Implementation Summary

## What Was Created

A comprehensive development/testing system to help you test multi-user scenarios without needing multiple Discord accounts.

## New Files

### 1. `cogs/dev.py` (485 lines)
The main development cog with 9 admin-only commands for testing.

**Commands:**
- `/dev_add_player` - Add fake solo players
- `/dev_add_group` - Add fake groups
- `/dev_simulate_scenario` - Create predefined test scenarios
- `/dev_queue_state` - View internal queue state with match_message_id
- `/dev_force_match` - Trigger matchmaking manually
- `/dev_remove_player` - Remove by ID
- `/dev_clear_queue` - Clear entire queue
- `/dev_info` - Show help
- `/dev_simulate_scenario` - Quick scenario setup

### 2. `DEV_MODE_GUIDE.md`
Comprehensive 400+ line guide covering:
- All command details and parameters
- 5 complete testing workflows
- How to identify fake vs real players
- Safety tips and troubleshooting
- Examples for testing specific bugs

### 3. `QUICK_TEST.md`
Fast-track testing guide:
- 2-minute test for the main bug fix
- Quick verification tests
- Success criteria checklist
- Common issues and solutions

### 4. `TEST_PLAN.md` (Created Earlier)
Formal test plan with 10 test cases and regression tests.

## Modified Files

### `bot.py`
Added dev cog loading:
```python
await self.load_extension("cogs.dev")
```

### `cogs/__init__.py`
Added DevCog to exports.

### `README.md`
Added dev commands section and references to dev mode guides.

## How It Works

### Fake Player System
- Generates unique IDs starting at `900000000000000000`
- Fake players work exactly like real players in the queue
- Can be matched with real players
- Cannot click buttons (they're not real Discord users)

### Match Creation
- `/dev_force_match` simulates what happens when a new player joins
- Creates match notifications with proper embeds and views
- Marks fake players with backticks instead of mentions
- Prefixes match messages with `[DEV MATCH]`

### State Inspection
- `/dev_queue_state` shows ALL internal details:
  - User IDs (helps identify fake vs real)
  - Match message IDs (verify players aren't in multiple matches)
  - Roles/compositions
  - Key ranges
- `/cola` shows what normal users see

## Quick Start

### Test the Main Bug Fix (2 minutes)

```bash
# 1. Clear and setup
/dev_clear_queue
/dev_simulate_scenario escenario:Escenario 2: Múltiples Grupos Independientes

# 2. Create matches
/dev_force_match

# 3. Verify
/dev_queue_state
```

**Expected:** Two separate matches, each player in exactly one match.

### Common Workflow

```bash
/dev_clear_queue          # Start fresh
/dev_simulate_scenario    # Add test players
/dev_queue_state          # Check initial state
/dev_force_match          # Create matches
/dev_queue_state          # Verify matches formed correctly
/dev_clear_queue          # Clean up
```

## Key Features

### Safety
- ✅ All commands are admin-only
- ✅ Only affects the current guild
- ✅ Clearly labeled as dev/test functionality
- ✅ Doesn't interfere with real user experience (except they'll see fake players)

### Flexibility
- Mix fake and real players
- Create complex scenarios quickly
- Inspect internal state at any time
- Force actions that normally require waiting

### Limitations
- Fake players can't click buttons
- For testing confirmation flow, still need real users/alts
- Match messages persist after clearing queue (delete manually)
- Primarily for testing matchmaking logic, not full user flows

## Testing the Bug Fixes

### Test: Players Can't Be in Multiple Groups

```bash
/dev_add_player nombre:A rol:tank key_min:5 key_max:10
/dev_add_player nombre:B rol:healer key_min:5 key_max:10
/dev_force_match  # Match 1

/dev_add_player nombre:C rol:dps key_min:5 key_max:10
/dev_force_match  # C should NOT join Match 1

/dev_queue_state  # Verify: A and B have match_message_id, C doesn't
```

### Test: Multiple Independent Groups

```bash
/dev_simulate_scenario escenario:Múltiples Grupos Independientes
/dev_force_match
/dev_queue_state  # Should see TWO different match_message_id values
```

## Documentation Hierarchy

1. **QUICK_TEST.md** - Start here! 2-minute tests
2. **DEV_MODE_GUIDE.md** - Complete reference with workflows
3. **TEST_PLAN.md** - Formal test cases
4. **BUGFIX_SUMMARY.md** - Technical details of the fixes

## Next Steps

1. **Restart your bot** to load the new dev cog
2. **Run `/dev_info`** in Discord to see command help
3. **Follow QUICK_TEST.md** to verify bug fixes
4. **Explore DEV_MODE_GUIDE.md** for advanced testing

## Example Session

```bash
# Start
/dev_info                                    # See available commands

# Create scenario
/dev_simulate_scenario escenario:Múltiples Grupos Independientes
# Output: 4 players added

# Inspect before matching
/dev_queue_state
# Output: Alice, Bob, Charlie, Diana - all without matches

# Create matches
/dev_force_match
# Output: 2 matches created

# Inspect after matching
/dev_queue_state
# Output: All 4 have match_message_id, but TWO different IDs

# View as user
/cola
# Output: Normal queue view (should be empty since all are in matches)

# Clean up
/dev_clear_queue
```

## Tips

- **Create a #dev-testing channel** for running these commands
- **Communicate with testers** so they're not confused by fake players
- **Clear fake players** before live demos or events
- **Mix real and fake** for more realistic testing
- **Take screenshots** of `/dev_queue_state` output when reporting issues

## Troubleshooting

### Commands not appearing?
- Restart the bot
- Wait a few minutes for Discord to sync
- Check you're an administrator
- Verify `cogs/dev.py` exists and `bot.py` loads it

### Fake players not matching?
- Check `/dev_queue_state` - do they have match_message_id already?
- Use `/dev_clear_queue` and start fresh
- Verify key ranges overlap

### Can't test button interactions?
- Fake players can't click buttons (limitation)
- Use real alt accounts for testing confirmation flows
- Or ask testers to help

## Support

See the detailed guides:
- **Quick tests:** QUICK_TEST.md
- **Complete reference:** DEV_MODE_GUIDE.md
- **Formal testing:** TEST_PLAN.md
- **Bug fix details:** BUGFIX_SUMMARY.md

---

**You're all set!** Run `/dev_info` in Discord to get started.
