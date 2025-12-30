# WoW Mythic+ LFG Discord Bot

A Discord bot that acts as a "Soft Matchmaker" for World of Warcraft Mythic+ dungeons. Guild members can flag themselves as available for specific Keystone levels, and the bot notifies everyone when potential groups form.

## Features

- **Persistent Queue Button** - Survives bot restarts
- **Role Selection** - Tank, Healer, or DPS with themed buttons
- **Key Range Filtering** - 2-5, 6-10, 11-15, or 16-20
- **Automatic Matching** - Notifies all players looking for the same key range
- **Easy Exit** - Leave the queue with a button click or `/leave` command
- **Queue Viewer** - Check who's looking with `/queue`

## How It Works

```
User clicks "Join Queue" button
        ↓
Select Role (Tank/Healer/DPS)
        ↓
Select Key Range (2-5, 6-10, etc.)
        ↓
Added to queue → Check for matches
        ↓
Match found? → Notify all players in that range!
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
4. Copy the generated URL and use it to invite the bot to your server

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

2. Edit `.env` with your values:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   LFG_CHANNEL_ID=123456789012345678
   ```

   To get a Channel ID:
   - Enable Developer Mode in Discord (Settings → Advanced → Developer Mode)
   - Right-click the channel and select "Copy ID"

### 5. Run the Bot

```bash
python main.py
```

You should see:
```
🚀 Starting WoW Mythic+ LFG Bot...
✅ Slash commands synced!
🤖 Logged in as YourBot#1234 (ID: 123456789)
📡 Connected to 1 guild(s)
────────────────────────────────────────
```

### 6. Set Up the LFG Channel

In Discord, go to your LFG channel and use the `/setup` command. This posts the persistent "Join Queue" button.

## Commands

| Command | Description |
|---------|-------------|
| `/setup` | Post the LFG button (Admin only) |
| `/queue` | View who's currently in the queue |
| `/leave` | Leave the queue |

## Project Structure

```
discord-wow-dungeon-matchmaking/
├── main.py              # Main bot file with all logic
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .env                 # Your configuration (git-ignored)
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## Code Overview

### Views (UI Components)

- **JoinQueueView** - Persistent button to start the flow
- **RoleSelectView** - Ephemeral buttons for Tank/Healer/DPS
- **KeyRangeSelectView** - Dropdown for key range selection
- **LeaveQueueView** - Persistent button on match notifications

### Key Functions

- `add_to_queue()` - Add or update a user in the queue
- `remove_from_queue()` - Remove a user from the queue
- `get_users_in_range()` - Find all users looking for a specific key range
- `build_match_embed()` - Create the match notification embed

### Persistence

The bot uses `custom_id` on buttons and registers views in `setup_hook()` so buttons continue working after restarts. The queue itself is in-memory, so it resets on restart (database support planned for Phase 2).

## Customization

### Key Ranges

Edit the `KEY_RANGES` list in `main.py`:

```python
KEY_RANGES = [
    ("2-5", "Keys 2-5", "Beginner keys"),
    ("6-10", "Keys 6-10", "Intermediate"),
    # Add more ranges as needed
]
```

### Roles

Edit the `ROLES` dictionary:

```python
ROLES = {
    "tank": {"name": "Tank", "emoji": "🛡️"},
    "healer": {"name": "Healer", "emoji": "💚"},
    "dps": {"name": "DPS", "emoji": "⚔️"},
}
```

## Troubleshooting

### Bot doesn't respond to buttons after restart

Make sure the views are registered in `setup_hook()`:
```python
async def setup_hook(self):
    self.add_view(JoinQueueView())
    self.add_view(LeaveQueueView())
```

### Slash commands not showing

Run the bot and wait a few minutes for Discord to sync. If still not working, try `/setup` directly - global command sync can take up to an hour.

### "DISCORD_TOKEN not found" error

Make sure your `.env` file exists and contains `DISCORD_TOKEN=your_actual_token`.

## Future Improvements (Phase 2)

- [ ] SQLite database for persistent queue storage
- [ ] Auto-expire queue entries after X hours
- [ ] Statistics and analytics
- [ ] Multiple guild support
- [ ] Custom key range configuration per server

## License

MIT License - Feel free to use and modify for your guild!

## Contributing

Pull requests welcome! Please keep the code well-commented for Discord bot beginners.
