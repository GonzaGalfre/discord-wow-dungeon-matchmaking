# WipyBot / Raid Report Hub Notes

## Repositories

- Bot repo: `D:\Proyectos\discord-wow-dungeon-matchmaking`
- Website repo: `D:\Proyectos\WIP-hub\raid-report-hub`

This repo is the Discord bot. The website repo is a separate Vite/React app used by raid leaders to manage signups and confirmed rosters.

## What This Bot Does

This project has been repurposed into `WipyBot`, a Discord raid signup bot.

Current core features:

- Discord raid signup messages with persistent dropdown/buttons.
- SQLite storage for raid events and signups.
- FastAPI dashboard still available locally.
- Voice move utility still available.
- Bidirectional sync with the website through `/api/raid-signups`.
- Website-created events are posted by the bot to Discord.
- Closed events update the Discord message and remove signup controls.
- Confirmed rosters from the website can be published by the bot as a generated PNG image.

Old Mythic+/LFG/matchmaking functionality has intentionally been removed.

## Local Services

Run the website/API from the website repo:

```powershell
npm run dev:api
```

This starts a custom local server at:

- Website: `http://localhost:3000`
- API: `http://localhost:3000/api/raid-signups`

Run the bot from this repo:

```powershell
python main.py
```

Bot dashboard:

- `http://127.0.0.1:8081`

## Environment

Bot `.env` needs:

```env
HUB_API_BASE_URL=http://localhost:3000
HUB_API_SECRET=local-dev-secret
HUB_SYNC_INTERVAL_SECONDS=5
DASHBOARD_PORT=8081
```

Website `.env.local` needs:

```env
APP_API_SECRET=local-dev-secret
VITE_APP_API_KEY=local-dev-secret
VITE_DATA_BACKEND=local
LIBSQL_URL=file:local.db
```

The shared secret must match between bot and website.

## Communication Model

The bot and website communicate via the website API endpoint:

```text
GET /api/raid-signups
PUT /api/raid-signups
```

The local API stores data in:

```text
D:\Proyectos\WIP-hub\raid-report-hub\local-raid-signups.json
```

The bot stores its local source data in SQLite:

```text
D:\Proyectos\discord-wow-dungeon-matchmaking\bot_data.db
```

Sync flow:

- Bot polls website snapshot every `HUB_SYNC_INTERVAL_SECONDS`.
- Bot imports website changes into SQLite.
- Bot posts missing website-created Discord signup messages.
- Bot updates Discord messages when website closes/opens events.
- Bot publishes confirmed roster images when the website requests publish.
- Bot pushes its latest snapshot back to the website.

Important: website API preserves important fields when bot pushes omit them, especially deleted event tombstones and roster fields. This prevents older bot snapshots from resurrecting deleted events or wiping website roster work.

## Snapshot Shape

The shared snapshot is roughly:

```ts
type RaidSignupSnapshot = {
  source?: string;
  synced_at?: string;
  events: RaidSignupEvent[];
  deleted_external_ids?: string[];
};
```

Each event includes:

```ts
type RaidSignupEvent = {
  external_id: string;
  guild_id: string;
  channel_id: string;
  message_id?: string | null;
  title: string;
  leader_name?: string | null;
  starts_at: string;
  created_by_user_id?: string;
  is_open: boolean;
  signups: RaidSignup[];
  confirmed_roster?: RaidSignup[];
  bench_roster?: RaidSignup[];
  roster_publish_channel_id?: string | null;
  roster_publish_requested_at?: string | null;
  roster_published_at?: string | null;
};
```

Each signup includes:

```ts
type RaidSignup = {
  user_id: string;
  display_name: string;
  status: string;
  class_key?: string | null;
  spec_key?: string | null;
  roster_role?: "tank" | "dps" | "healer" | null;
  note?: string | null;
  updated_at?: string | null;
};
```

`roster_role` is a website override used only for the confirmed roster. Example: someone signs as DPS but raid lead drags them to Final Tanks.

## Discord IDs

Current website constants:

- Guild ID: `1383121597833154680`
- `Inscripcion Core 1`: `1385248663324069908` thread
- `Testing`: `1383124998239162502` channel

These are in:

```text
D:\Proyectos\WIP-hub\raid-report-hub\src\components\tabs\RaidSignupsTab.tsx
```

## Key Bot Files

- `bot.py`: bot startup, command sync, hub sync loop.
- `config/settings.py`: environment config.
- `models/database.py`: SQLite schema/migrations.
- `models/raid_signup.py`: raid event/signups DAO and snapshot import/export.
- `services/hub_sync.py`: website sync logic.
- `services/raid_signup.py`: Discord signup embed/message refresh.
- `services/roster_publish.py`: confirmed roster image/text publishing.
- `services/raid_catalog.py`: class/spec/role metadata.
- `views/raid_signup.py`: Discord UI components.
- `cogs/raid.py`: raid slash commands.

## Key Website Files

- `scripts/local-dev-with-api.mjs`: local API + Vite server.
- `api/raid-signups.ts`: production/Vercel raid signup API endpoint.
- `src/lib/remote-sync.ts`: frontend API client and shared types.
- `src/hooks/use-raid-signups.ts`: React Query hook.
- `src/components/tabs/RaidSignupsTab.tsx`: signup/roster management UI.

## Roster Publishing

Website flow:

- Raid leader selects players into final roster columns.
- Players can be dragged between Final Tanks / Final DPS / Final Healers.
- Players can be dragged or clicked into Bench.
- Final role assignment is saved as `roster_role`.
- Pressing `Publish roster` sets `roster_publish_requested_at`.

Bot flow:

- Bot imports the snapshot.
- If `roster_publish_requested_at` differs from `roster_published_at`, bot publishes.
- Bot sends a generated PNG if Pillow works.
- Bot falls back to text if image generation fails.
- Bot marks `roster_published_at` to prevent repeat sends.

Pillow is required for image generation and is listed in `requirements.txt`.

## Deletions

Website deletions are tombstoned using:

```text
deleted_external_ids
```

This prevents the bot from re-pushing deleted events back into the website.

When bot sees a deleted external ID:

- It attempts to delete the Discord signup message.
- It deletes the local SQLite event.

## Verification Commands

Bot:

```powershell
python -m compileall .
```

Website:

```powershell
npm run build
```

## Restart Notes

On this Windows environment, detached long-running process startup can be flaky. A reliable fallback has been:

```powershell
Start-Process -FilePath "python" -ArgumentList "main.py" -WorkingDirectory "D:\Proyectos\discord-wow-dungeon-matchmaking" -RedirectStandardOutput "D:\Proyectos\discord-wow-dungeon-matchmaking\bot-local.log" -RedirectStandardError "D:\Proyectos\discord-wow-dungeon-matchmaking\bot-local.err.log" -WindowStyle Hidden
```

For the website API:

```powershell
cmd.exe /c start "" /min cmd.exe /c "cd /d D:\Proyectos\WIP-hub\raid-report-hub && npm run dev:api > local-dev-api.log 2> local-dev-api.err.log"
```

Stop both:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*local-dev-with-api.mjs*' -or $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## Current UX Notes

- Website event cards are full-width.
- Signed players are grouped into Tanks / DPS / Healers.
- Final selected players are grouped into Tanks / DPS / Healers.
- Bench is a separate row below final selections.
- Player cards use WoW class colors and show player + spec only.
- Bench/late signed players show small status badges.
- Final columns and bench row highlight during drag-over.
- Clicking final/bench cards sends players back to signed list.
- Dragging selected players between final columns changes only their roster role, not their signup spec.
