# WipyBot

WipyBot is a Discord bot scaffold for guild tooling. The original Mythic+ matchmaking functionality has been removed so the project can be rebuilt around raid signups.

## Current Features

- Discord bot startup with global slash command sync.
- Multi-guild SQLite configuration storage.
- Optional admin dashboard with Basic Auth.
- Runtime event logging to `logs/events.jsonl`.
- Raid signup messages with class/spec and attendance controls.
- Voice move utility via `/move` and `/setup_move`.
- Per-server voice/text participation tracking with weighted raffles.

## Setup

1. Create a Discord application and bot in the Discord Developer Portal.
2. Invite the bot with `bot` and `applications.commands` scopes.
3. Enable Discord intents: Guilds, Voice States, and Messages. Message Content is not required.
4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Create `.env` from `.env.example` and set `DISCORD_TOKEN`.
6. Optionally set `DASHBOARD_PASSWORD` to enable the dashboard.
7. Run the bot:

```bash
python main.py
```

## Environment

```env
DISCORD_TOKEN=your_discord_bot_token_here
DASHBOARD_PASSWORD=change_me
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8080

# Optional raid-report-hub integration
HUB_API_BASE_URL=https://your-raid-report-hub.example.com
HUB_API_SECRET=shared_secret_with_raid_report_hub
HUB_SYNC_INTERVAL_SECONDS=15
```

If `DASHBOARD_PASSWORD` is empty, the dashboard does not start.

If `HUB_API_BASE_URL` is set, WipyBot syncs raid signup events with raid-report-hub through `/api/raid-signups`. `HUB_API_SECRET` must match the website `APP_API_SECRET` when that secret is configured.

## Commands

| Command | Description |
|---------|-------------|
| `/raid_create` | Create a dynamic raid signup message. |
| `/raid_close` | Close a raid signup by event ID. |
| `/raid_open` | Re-open a raid signup by event ID. |
| `/raid_dummy_add` | Add a fake signup to an event for testing. |
| `/raid_dummy_seed` | Add a full fake roster to an event for testing. |
| `/raid_dummy_clear` | Remove fake signups from an event. |
| `/move` | Move all members from one voice channel to another. |
| `/setup_move` | Publish the persistent voice move panel. |
| `/participation setup_roles` | Set the minimum eligible role and officer role for this server. |
| `/participation add_voice` | Add a tracked voice channel. |
| `/participation add_text` | Add a tracked text channel. |
| `/participation rules` | Configure voice ticket thresholds, cap, message cooldown, and raffle period length. |
| `/participation status` | Show participation configuration. |
| `/participation sync_voice` | Start tracking eligible members already connected to tracked voice channels. |
| `/participation panel_create` | Post a persistent participation overview panel. |
| `/participation panel_refresh` | Officer-only refresh of the panel message. |
| `/participation panel_interval` | Set the panel auto-refresh interval in minutes. |
| `/participation panel_delete` | Delete or clear the saved panel message. |
| `/participation me` | Show your current-period participation totals. |
| `/participation leaderboard` | Show the current-period leaderboard. |
| `/participation voice_status` | Officer-only open voice session diagnostics. |
| `/raffle preview` | Officer-only ticket preview. |
| `/raffle close` | Officer-only close current raffle period and open the next. |
| `/raffle draw` | Officer-only weighted draw for the latest closed undrawn period. |

## Participation And Raffles

Participation is configured per Discord server and stored in SQLite. A member only counts when they have the configured eligible role. Officer raffle commands require the configured officer role.

Voice time counts only in tracked voice channels. Moving between tracked voice channels keeps one continuous session; mute/deafen-only state changes are ignored. On startup, WipyBot closes stale open voice sessions and opens fresh sessions for eligible members already connected to tracked voice channels.

Messages count only in tracked text channels for stats. WipyBot stores message metadata only and does not require Message Content intent. Messages do not earn raffle tickets.

Raffle tickets are calculated from the active period:

```text
if total_voice_seconds < first_voice_minutes_per_ticket * 60:
    voice_tickets = 0
else:
    voice_tickets = 1 + floor((total_voice_seconds - first_voice_minutes_per_ticket * 60) / (voice_minutes_per_ticket * 60))
message_tickets = 0
```

By default, the first voice ticket is earned after 15 minutes, then additional voice tickets are earned every 60 minutes. Voice tickets are capped by the configured max. `/raffle draw` stores the winning number and per-user cumulative ticket snapshots for auditability.

### Participation Panel

Use `/participation panel_create` to post a persistent public panel in a channel. The panel shows the current period, top participants, time remaining, and refresh interval. It includes buttons:

- `My Progress`: private live stats for the user who clicks.
- `Rules`: private server rules and tracked channels.
- `Leaderboard`: private detailed leaderboard.

The bot refreshes the public panel every configured interval. Use `/participation panel_interval` to change it and `/participation panel_refresh` to force an update.

## Custom Icons

Custom class/spec/status icons can be configured in `config/emoji_overrides.py` using Discord custom emoji mentions such as `<:frost:123456789012345678>`.

When a spec icon is configured, signup rows use the icon instead of spelling out the full spec name.

## Project Structure

```text
discord-wow-dungeon-matchmaking/
├── main.py                  # Entry point
├── bot.py                   # WipyBot class
├── runtime.py               # Shared runtime bot reference
├── event_logger.py          # JSONL runtime logging
├── config/                  # Environment/config values
├── models/                  # SQLite connection and guild settings
├── cogs/                    # Discord slash command cogs
├── services/                # Reusable business logic
├── views/                   # Discord UI views
└── web/                     # Optional admin dashboard
```

## Next Feature Area

Raid signup will be built on top of the preserved infrastructure:

- Admin creates or configures raid signup messages.
- Members select attendance status.
- Members select class/spec.
- The bot updates a dynamic Discord message with the current signup state.
- Future web/admin tooling can edit signup state and reflect changes back in Discord.
