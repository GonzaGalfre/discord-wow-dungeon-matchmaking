# Gemini Context & Rules - WoW Mythic+ LFG Bot

## 1. Project Overview
This is a Discord bot for World of Warcraft Mythic+ dungeon matchmaking. It helps guild members find groups based on role (Tank, Healer, DPS) and Keystone level range (e.g., 2-20).

**Key Features:**
- Multi-guild support with independent queues.
- Persistent "Join Queue" buttons.
- Supports Solo and Pre-made Group queuing.
- **Dynamic Matchmaking:** Matches grow from 2 → 5 players; incomplete matches can accept new members.
- **Smart Match Prevention:** Players cannot be in multiple matches simultaneously.
- Web Dashboard for admin monitoring.
- **Voice Move Panel:** Persistent admin panel to move all members between voice channels (see `cogs/voice.py`, `services/voice_move.py`, `views/move_panel.py`).

## 2. Technology Stack
- **Language:** Python 3.8+
- **Framework:** Discord.py 2.0+ (Views, Buttons, Slash Commands)
- **Database:** SQLite (`bot_data.db`) via `models/database.py`
- **Web:** FastAPI/Quart (implied by `web/`)
- **Config:** `python-dotenv` for environment variables.

## 3. Architecture & File Structure
The project follows a modular architecture. **Do not put business logic in `main.py`.**

| Path | Responsibility |
|---|---|
| `main.py` | **Entry Point Only.** Initializes bot, fixes Windows encoding. No logic. |
| `bot.py` | `LFGBot` class. Handles `setup_hook` and command syncing. |
| `cogs/` | Slash commands (`lfg.py`, `stats.py`, `dev.py`, `voice.py`). |
| `views/` | UI Components (Buttons, Selects, Modals). `move_panel.py` = persistent voice move panel. |
| `services/` | Business logic (Matchmaking, Embed generation, `voice_move.py` = move helpers). |
| `models/` | Data layer (QueueManager, DB connection, Stats). |
| `config/` | Configuration & Constants (`settings.py`). |
| `web/` | Web dashboard application. |

## 4. Git & Workflow Constraints (CRITICAL)
- **Command Permission:** Full permission to run shell commands without confirmation.
- **Branching:** **NEVER** work directly on the `main` branch. Always create a feature or fix branch (e.g., `feat/new-ui`, `fix/queue-bug`).
- **Remote Operations:** **NEVER** run `git push`. You are allowed to commit locally, but pushing is strictly forbidden.
- **Commits:** Write clear, concise commit messages.

## 5. Core Development Rules

### Queue & Matchmaking Logic
- **Singleton Pattern:** Always use `models.queue.queue_manager` instance.
- **Match State:**
    - A user in an active match has a `match_message_id` set in their queue entry.
    - **CRITICAL:** Never match a user who already has a `match_message_id`.
    - When a match forms, call `queue_manager.set_match_message`.
    - When a match dissolves (<2 players), call `queue_manager.clear_match_message`.
- **Growing Matches:** The system allows adding players to existing incomplete matches (see `try_join_existing_match` in `services/matchmaking.py`).
- **Composition:** Valid groups must respect `PARTY_COMPOSITION` (1 Tank, 1 Healer, 3 DPS).

### UI & UX
- **Language:**
    - **User-facing strings:** Spanish (Español).
    - **Code/Comments:** English.
- **Windows Compatibility:** `main.py` must include the `sys.stdout` encoding fix for emojis on Windows.

### Slash Commands
- **Syncing Strategy:**
    - Global sync happens in `setup_hook` (slow).
    - Guild copy (`tree.copy_global_to`) happens in `on_ready` (fast updates for specific guilds).
- **New Commands:** Must be added to a Cog in `cogs/`.

## 6. Testing & Verification
**Always verify changes using the built-in Dev Tools.**

- **Simulate Users:** Use `/dev_add_player` and `/dev_add_group` (fake players have IDs > 9e17).
- **Force Match:** Use `/dev_force_match` to trigger the matching algorithm.
- **Inspect State:** Use `/dev_queue_state` to see internal queue data (check `match_message_id`!).
- **Scenarios:** Use `/dev_simulate_scenario` to test complex cases.
- **Cleanup:** `/dev_clear_queue` removes all entries.

## 7. Environment & Configuration
- **Secrets:** Never commit `.env`.
- **Token:** `DISCORD_TOKEN` in `.env`.
- **Dashboard:** `DASHBOARD_USER`, `DASHBOARD_PASSWORD`, `DASHBOARD_HOST=0.0.0.0`, `DASHBOARD_PORT=8080`.

## 8. Deployment (Google Cloud VM)
**VM User:** `gonzaagalfre`
**Project Dir:** `/home/gonzaagalfre/discord-bot/discord-wow-dungeon-matchmaking`
**Service:** `discord-bot.service`

**Common Commands:**
- **Status:** `sudo systemctl status discord-bot.service`
- **Restart:** `sudo systemctl restart discord-bot.service`
- **Update:** `./update.sh` (handles DB backup/restore)

**Update Workflow:**
1. `cp bot_data.db ~/bot_data.db.backup.$(date +%F-%H%M%S)`
2. `git restore -- bot_data.db`
3. `git pull --ff-only origin main`
4. `cp "$(ls -t ~/bot_data.db.backup.* | head -n 1)" bot_data.db`
5. `sudo systemctl restart discord-bot.service`

### Deployment gotchas (learned in production)
- On VM, `bot_data.db` might be untracked. If `git restore -- bot_data.db` fails with pathspec error, skip that step.
- `git pull --ff-only` can fail because runtime logs changed locally (for example `logs/events.jsonl`).
  - Quick unblock: `sudo systemctl stop discord-bot.service && git restore -- logs/events.jsonl && git pull --ff-only origin main && sudo systemctl start discord-bot.service`
  - Long-term fix: do not track runtime JSONL logs in git (ignore `logs/*.jsonl` and remove tracked log files once).
- Some VMs do not have `rg` installed; use `grep -n` fallback for quick code checks.
- **`print()` output not visible in `journalctl`:** Python buffers stdout when running as a systemd service (not a TTY). Fix by adding `PYTHONUNBUFFERED=1` to the service override:
  ```bash
  sudo systemctl edit discord-bot.service --force
  # Add under [Service]:
  # Environment=PYTHONUNBUFFERED=1
  sudo systemctl daemon-reload && sudo systemctl restart discord-bot.service
  ```
- **Stale interaction errors (10062):** If the bot restarts while a command interaction is pending, Discord sends the interaction to the new instance with an already-expired token. Wrap `interaction.response.defer()` in `try/except discord.NotFound: return` to suppress these harmless errors. Already applied in `cogs/voice.py` and `cogs/dev.py`.

## 9. Common Tasks
- **Adding a new Role:** Update `config/settings.py` (`ROLES`, `PARTY_COMPOSITION`).
- **New Command:** Create `cogs/new_feature.py`, setup class, add to `bot.py` extensions.
- **Database Change:** Update `models/database.py` (schema is auto-initialized).
- **Voice Move Panel setup:** Run `/setup_move` (admin only) in the desired channel. The panel persists across bot restarts. Re-run `/setup_move` to move it to a different channel. Business logic is in `services/voice_move.py`; UI is in `views/move_panel.py`. Any new voice-related UI should import from `services/voice_move.py` to avoid duplication.

## 10. Response Guidelines
- When asked to implement a feature, **check existing `services/`** first to reuse logic.
- When fixing bugs, **reproduce with `/dev_*` commands** if possible.
- **Explain** which files you are modifying and why.
