# WoW Mythic+ LFG Discord Bot

A Discord bot that acts as a "Soft Matchmaker" for World of Warcraft Mythic+ dungeons. Guild members can flag themselves as available for specific Keystone levels, and the bot notifies everyone when potential groups form.

## Features

- **Multi-Guild Support** - Works across multiple Discord servers simultaneously
- **Persistent Queue Button** - Survives bot restarts
- **Role Selection** - Tank, Healer, or DPS with themed buttons
- **Group Queue** - Queue as a pre-made group with any composition
- **Flexible Key Range** - Select min and max key levels (2-20)
- **Automatic Matching** - Notifies all players looking for compatible key ranges
- **Multiple Independent Groups** - Players can only be in one match at a time, allowing multiple groups to form simultaneously
- **Smart Match Prevention** - Players cannot join the queue while already in an active match
- **Stats & Leaderboards** - Track completed keys and see weekly/all-time rankings
- **Weekly Announcements** - Automatic weekly summaries on Tuesday reset
- **Easy Exit** - Leave the queue with a button click or `/salir` command
- **Queue Viewer** - Check who's looking with `/cola`
- **Admin Web Dashboard** - Monitor queue status, active groups, and leaderboard from a browser (polling every 10s)

## How It Works

```
User clicks "Join Queue" button
        ↓
Choose: Solo or Group queue
        ↓
Select Role (Solo) or Composition (Group)
        ↓
Select Min & Max Key Levels
        ↓
Added to queue → Check for matches
        ↓
Match found? → Notify all players!
        ↓
Everyone confirms → Group formed + Stats recorded
```

## Setup

### 1. Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section and click "Add Bot"
4. Copy the bot token (you'll need this later)

### 2. Configure Bot Permissions

In the Developer Portal:

1. Go to "OAuth2" → "URL Generator"
2. Select scopes: `bot`, `applications.commands`
3. Select bot permissions:
   - Send Messages
   - Embed Links
   - Use Slash Commands
   - Read Message History
   - Manage Messages (for deleting match notifications)
4. Copy the generated URL and use it to invite the bot to your server(s)

### 3. Set Up the Project

```bash
# Clone or download the project
cd discord-wow-dungeon-matchmaking

# Create a virtual environment (recommended)
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Configure Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your bot token:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   ```

   **Note:** Channel IDs are no longer needed in `.env` - they are now configured per-server using the `/setup` and `/config` commands.

3. Optional: Enable admin dashboard:
   ```env
   DASHBOARD_PASSWORD=your_admin_password
   DASHBOARD_HOST=127.0.0.1
   DASHBOARD_PORT=8080
   ```
   If `DASHBOARD_PASSWORD` is set, open `http://127.0.0.1:8080` and authenticate with Basic Auth.

### 5. Run the Bot

```bash
python main.py
```

You should see:
```
🚀 Starting WoW Mythic+ LFG Bot...
✅ ¡Comandos slash sincronizados!
🤖 Conectado como YourBot#1234 (ID: 123456789)
📡 Conectado a 2 servidor(es):
   • My Guild (ID: 123456789)
   • Test Server (ID: 987654321)
────────────────────────────────────────
⚙️ 1 servidor(es) configurado(s):
   • My Guild [match: ✓] [anuncios: ✗]
────────────────────────────────────────
```

### 6. Set Up Each Server

In each Discord server where you want to use the bot:

1. **Initial Setup**: Use `/setup` in your LFG channel. This:
   - Posts the persistent "Join Queue" button
   - Saves the channel as both LFG and match notification channel

2. **Optional Configuration**: Use `/config` to set different channels:
   - `/config tipo:match canal:#match-notifications` - Separate channel for matches
   - `/config tipo:announcement canal:#announcements` - Weekly announcement channel

3. **View Current Config**: Use `/verconfig` to see the server's configuration

## Commands

### User Commands
| Command | Description |
|---------|-------------|
| `/cola` | View who's currently in the queue |
| `/salir` | Leave the queue |
| `/leaderboard` | View weekly or all-time leaderboard |
| `/mystats` | View your personal stats |
| `/playerstats` | View another player's stats |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/setup` | Post the LFG button and configure the server |
| `/config` | Configure match or announcement channels |
| `/verconfig` | View current server configuration |
| `/anuncio` | Manually post weekly summary |

### Development Commands (Admin Only)
| Command | Description |
|---------|-------------|
| `/dev_add_player` | Add a fake solo player for testing |
| `/dev_add_group` | Add a fake group for testing |
| `/dev_simulate_scenario` | Create predefined test scenarios |
| `/dev_queue_state` | View internal queue state |
| `/dev_force_match` | Force matchmaking |
| `/dev_remove_player` | Remove player by ID |
| `/dev_clear_queue` | Clear entire queue |
| `/dev_info` | Show dev commands help |

See [DEV_MODE_GUIDE.md](DEV_MODE_GUIDE.md) for detailed testing workflows.

## Multi-Guild Support

The bot is designed to work with multiple Discord servers simultaneously:

- **Independent Queues**: Each server has its own separate queue
- **Per-Server Configuration**: Channel settings are stored per-server in SQLite
- **Guild-Specific Stats**: Leaderboards show stats for the current server
- **Automatic Announcements**: Weekly summaries are sent to all configured servers

### Adding the Bot to Multiple Servers

1. Use the OAuth2 URL to invite the bot to each server
2. Run `/setup` in each server to configure it
3. Optionally use `/config` to customize channels

## Project Structure

```
discord-wow-dungeon-matchmaking/
├── .cursorrules         # AI assistant guidelines for architecture
├── main.py              # Entry point (minimal)
├── bot.py               # LFGBot class definition
├── bot_data.db          # SQLite database (auto-created)
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .env                 # Your configuration (git-ignored)
├── .gitignore           # Git ignore rules
├── README.md            # This file
│
├── config/              # Configuration module
│   ├── __init__.py
│   └── settings.py      # Constants and environment variables
│
├── models/              # Data layer
│   ├── __init__.py
│   ├── database.py      # SQLite connection and schema
│   ├── queue.py         # QueueManager class (multi-guild)
│   ├── stats.py         # Stats database operations
│   └── guild_settings.py # Per-guild configuration storage
│
├── services/            # Business logic
│   ├── __init__.py
│   ├── matchmaking.py   # Matching algorithms
│   ├── embeds.py        # Discord embed builders
│   └── leaderboard.py   # Leaderboard embed builders
│
├── views/               # Discord UI components
│   ├── __init__.py
│   ├── join_queue.py    # Entry point views
│   ├── role_selection.py    # Solo queue views
│   ├── group_selection.py   # Group queue views
│   └── party.py         # Party formation views
│
└── cogs/                # Discord slash commands
    ├── __init__.py
    ├── lfg.py           # LFG commands (/setup, /config, /cola, /salir)
    └── stats.py         # Stats commands (/leaderboard, /mystats, etc.)
```

## Architecture Overview

The bot follows a modular architecture with clear separation of concerns:

| Module | Responsibility |
|--------|----------------|
| `config/` | Configuration and constants |
| `models/` | Data structures (QueueManager, GuildSettings, Stats) |
| `services/` | Business logic (matchmaking, embeds, leaderboards) |
| `views/` | Discord UI components |
| `cogs/` | Slash commands |

### Key Components

- **QueueManager** (`models/queue.py`) - Manages guild-specific in-memory queues
- **GuildSettings** (`models/guild_settings.py`) - Per-guild channel configuration
- **Stats** (`models/stats.py`) - Database operations for tracking completions
- **Matchmaking Service** (`services/matchmaking.py`) - Finding compatible groups
- **Embed Builders** (`services/embeds.py`, `services/leaderboard.py`) - Creating Discord embeds
- **Views** (`views/`) - Discord buttons, selects, and modals
- **LFG Cog** (`cogs/lfg.py`) - LFG-related slash commands
- **Stats Cog** (`cogs/stats.py`) - Stats/leaderboard commands + weekly task

### Database

The bot uses SQLite (`bot_data.db`) to store:
- Guild configurations (channel IDs per server)
- Completed key records (with guild_id for multi-guild tracking)
- Participant data for statistics

The queue itself remains in-memory for fast access but is now guild-aware.

## Adding New Features

Follow the `.cursorrules` file for architecture guidelines:

1. **New commands** → Add to `cogs/` as a Cog
2. **New UI components** → Add to `views/`
3. **New business logic** → Add to `services/`
4. **New constants** → Add to `config/settings.py`
5. **Queue operations** → Use `QueueManager` from `models/`

**Never add new code directly to `main.py`** - it should only contain the entry point.

## Customization

### Key Level Range

Edit in `config/settings.py`:

```python
MIN_KEY_LEVEL = 2
MAX_KEY_LEVEL = 20
```

### Roles

Edit the `ROLES` dictionary in `config/settings.py`:

```python
ROLES = {
    "tank": {"name": "Tanque", "emoji": "🛡️"},
    "healer": {"name": "Sanador", "emoji": "💚"},
    "dps": {"name": "DPS", "emoji": "⚔️"},
}
```

### Party Composition

Edit in `config/settings.py`:

```python
PARTY_COMPOSITION = {
    "tank": 1,
    "healer": 1,
    "dps": 3,
}
```

## Troubleshooting

### Bot doesn't respond to buttons after restart

Make sure the views are registered in `setup_hook()`:
```python
async def setup_hook(self):
    self.add_view(JoinQueueView())
```

### Slash commands not showing

Run the bot and wait a few minutes for Discord to sync. If still not working, try `/setup` directly - global command sync can take up to an hour.

### "DISCORD_TOKEN not found" error

Make sure your `.env` file exists and contains `DISCORD_TOKEN=your_actual_token`.

### Stats not showing for a server

Make sure you've run `/setup` in that server. Stats are tracked per-guild starting from when the server was configured.

### Testing multi-user scenarios

Use the dev commands to simulate multiple users without needing multiple Discord accounts:

```
/dev_simulate_scenario escenario:Múltiples Grupos Independientes
/dev_force_match
```

See [DEV_MODE_GUIDE.md](DEV_MODE_GUIDE.md) for complete testing workflows.

## Recent Improvements

- [x] **Fixed multiple group membership** - Players can no longer be in multiple matches simultaneously
- [x] **Multiple independent groups** - Different groups can form and exist at the same time
- [x] **Match state management** - Proper cleanup when matches are dissolved

## Future Improvements

- [ ] Batch matchmaking (form all possible groups at once)
- [ ] Queue persistence (save queue to database)
- [ ] Auto-expire queue entries after X hours
- [ ] Custom key range configuration per server
- [ ] Role-specific stats tracking
- [ ] Admin commands for queue management

## License

MIT License - Feel free to use and modify for your guild!

## Contributing

Pull requests welcome! Please keep the code well-commented for Discord bot beginners.
