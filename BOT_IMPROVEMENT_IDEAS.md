# Discord Bot Improvement Ideas

This document proposes improvements for the WoW Mythic+ matchmaking bot, combining quick wins and larger strategic features.

## Most Impact, Least Complexity (Priority First)

### 1) Auto-expire stale queue entries
- **Impact:** Most
- **Complexity:** Least
- **Why:** Removes abandoned queue entries and improves matching quality.
- **Implementation hint:** Add `created_at`/`last_active_at` to queue entries and run periodic cleanup.

### 2) Track actual key level completed (instead of using queue minimum)
- **Impact:** Most
- **Complexity:** Least
- **Why:** Makes leaderboard and player stats more accurate and trustworthy.
- **Implementation hint:** Add a post-run select/modal in confirmation flow for final key level.

### 3) Queue position + wait duration in `/cola`
- **Impact:** Most
- **Complexity:** Least
- **Why:** Better transparency; users understand when to stay or requeue.
- **Implementation hint:** Show order, role, key range, and "waiting for Xm".

### 4) Duplicate queue entry guard per user
- **Impact:** Most
- **Complexity:** Least
- **Why:** Prevents accidental duplicate entries and queue pollution.
- **Implementation hint:** Reject joins if user already has an active waiting entry in the guild queue.

## Most Impact, Most Complexity (Strategic)

### 5) Persistent queue across bot restarts
- **Impact:** Most
- **Complexity:** Most
- **Why:** Greatly improves reliability in real-world operation.
- **Implementation hint:** Persist queue entries in SQLite and restore them at startup.

### 6) Persistent active match state + confirmation recovery
- **Impact:** Most
- **Complexity:** Most
- **Why:** Prevents broken confirmations after restart and avoids orphaned matches.
- **Implementation hint:** Store active match metadata and rebuild views/state on boot.

### 7) Smarter matchmaking scoring engine
- **Impact:** Most
- **Complexity:** Most
- **Why:** Improves group quality by balancing roles, range overlap quality, and wait time fairness.
- **Implementation hint:** Replace first-fit logic with weighted scoring + tie-breakers.

### 8) Admin dashboard with write actions
- **Impact:** Most
- **Complexity:** Most
- **Why:** Reduces admin friction by enabling operations without Discord slash commands.
- **Implementation hint:** Add authenticated actions: remove queue entry, dissolve match, trigger announcement.

## Least Impact, Least Complexity (Nice to Have)

### 9) Better cleanup tools for dev/testing messages
- **Impact:** Least
- **Complexity:** Least
- **Why:** Improves local testing hygiene and speeds iterative development.
- **Implementation hint:** Add `/dev_cleanup` to clear fake players and stale dev messages.

### 10) Guild-configurable weekly reset schedule
- **Impact:** Least
- **Complexity:** Least
- **Why:** More flexibility for communities in different regions/time zones.
- **Implementation hint:** Store timezone and reset time in guild settings.

### 11) Notification preferences (mention only, DM, or silent)
- **Impact:** Least
- **Complexity:** Least
- **Why:** Reduces spam and improves adoption for users with different notification tolerance.
- **Implementation hint:** Per-user preference table and conditional notify path.

## Least Impact, Most Complexity (Optional Later)

### 12) Queue analytics and trend reporting
- **Impact:** Least
- **Complexity:** Most
- **Why:** Useful for optimization, but not immediately required for core matchmaking quality.
- **Implementation hint:** Aggregate hourly/daily queue stats and expose simple dashboard charts.

### 13) Match history explorer
- **Impact:** Least
- **Complexity:** Most
- **Why:** Good for retrospective insights, lower priority than reliability features.
- **Implementation hint:** Store match snapshots and provide slash command/web filters.

### 14) Priority tiers in queueing
- **Impact:** Least
- **Complexity:** Most
- **Why:** Can support community perks, but risks fairness concerns and policy overhead.
- **Implementation hint:** Add priority weights and explicit governance rules.

## Suggested Execution Order

1. Auto-expiry, queue position, duplicate guard, real key-level capture.
2. Queue persistence and active match persistence.
3. Smarter matchmaking + dashboard write actions.
4. Optional analytics/history/priority systems.

