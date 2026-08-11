"""Synchronization with raid-report-hub."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import discord

from config.settings import HUB_API_BASE_URL, HUB_API_SECRET, HUB_SYNC_INTERVAL_SECONDS
from models.raid_signup import (
    attach_raid_message,
    delete_raid_event_by_external_id,
    export_raid_signup_snapshot,
    get_raid_event,
    get_raid_event_by_external_id,
    list_raid_signups,
    replace_raid_signups_from_snapshot,
    update_raid_event_from_snapshot,
)
from models.participation import (
    draw_current_period,
    export_raffle_action_receipts,
    export_raffle_state_snapshot,
    get_action_receipt,
    get_pending_raffle_publications,
    get_participation_settings,
    mark_raffle_published,
    replace_exclusive_winner_ids,
    reset_current_period,
    save_action_receipt,
    export_live_voice_snapshot,
    export_participation_leaderboards_snapshot,
    export_participation_settings_snapshot,
    update_participation_panel,
    upsert_participation_settings_from_snapshot,
    add_debug_tickets,
)
from models import vip_voice as vip_voice_repo
from services.participation_panel import build_panel_embed
from services.participation_panel import calculator_for_settings
from services.raid_signup import build_raid_signup_embed, refresh_raid_signup_message
from services.roster_publish import publish_confirmed_roster


_participation_member_names: dict[tuple[int, int], str] = {}


def is_hub_sync_enabled() -> bool:
    return bool(HUB_API_BASE_URL)


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if HUB_API_SECRET:
        headers["x-api-key"] = HUB_API_SECRET
    return headers


def _request_json(method: str, path: str, payload: Any | None = None) -> Any:
    url = f"{HUB_API_BASE_URL}{path}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=_headers(), method=method)
    with urlopen(request, timeout=12) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else None


async def fetch_hub_snapshot() -> dict | None:
    if not is_hub_sync_enabled():
        return None
    try:
        result = await asyncio.to_thread(_request_json, "GET", "/api/raid-signups")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"Hub sync fetch failed: {exc}")
        return None
    data = result.get("data") if isinstance(result, dict) else None
    return data if isinstance(data, dict) else None


async def push_hub_snapshot() -> None:
    if not is_hub_sync_enabled():
        return
    snapshot = export_raid_signup_snapshot()
    snapshot["participation_settings"] = export_participation_settings_snapshot()
    snapshot["participation_raffle"] = {"states": export_raffle_state_snapshot(), "action_receipts": export_raffle_action_receipts()}
    try:
        await asyncio.to_thread(_request_json, "PUT", "/api/raid-signups", {"data": snapshot})
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"Hub sync push failed: {exc}")


def _export_discord_guilds(client: discord.Client) -> list[dict]:
    guilds: list[dict] = []
    for guild in client.guilds:
        roles = [
            {"id": str(role.id), "name": role.name, "position": role.position, "color": str(role.color)}
            for role in sorted(guild.roles, key=lambda item: item.position, reverse=True)
            if not role.is_default()
        ]
        channels = []
        for channel in sorted(guild.channels, key=lambda item: (str(getattr(item, "category", "")), item.position, item.name)):
            if isinstance(channel, discord.TextChannel):
                kind = "text"
            elif isinstance(channel, discord.VoiceChannel):
                kind = "voice"
            elif isinstance(channel, discord.StageChannel):
                kind = "stage"
            elif isinstance(channel, discord.Thread):
                kind = "thread"
            else:
                continue
            channels.append(
                {
                    "id": str(channel.id),
                    "name": channel.name,
                    "kind": kind,
                    "category": getattr(getattr(channel, "category", None), "name", None),
                }
            )
        guilds.append({"id": str(guild.id), "name": guild.name, "roles": roles, "channels": channels})
    return guilds


async def _export_participation_leaderboards(client: discord.Client) -> list[dict]:
    leaderboards = export_participation_leaderboards_snapshot()
    for leaderboard in leaderboards:
        guild_id = leaderboard.get("guild_id")
        guild = client.get_guild(int(guild_id)) if isinstance(guild_id, str) and guild_id.isdigit() else None
        for entry in leaderboard["entries"]:
            user_id = entry.get("user_id")
            if not guild or not isinstance(user_id, str) or not user_id.isdigit():
                continue
            key = (guild.id, int(user_id))
            display_name = _participation_member_names.get(key)
            if display_name is None:
                member = guild.get_member(key[1])
                if member is None:
                    try:
                        member = await guild.fetch_member(key[1])
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        continue
                display_name = member.display_name
                _participation_member_names[key] = display_name
            entry["display_name"] = display_name
    return leaderboards


async def _export_live_voice(client: discord.Client) -> list[dict]:
    live_voice = export_live_voice_snapshot()
    for status in live_voice:
        guild_id = status.get("guild_id")
        guild = client.get_guild(int(guild_id)) if isinstance(guild_id, str) and guild_id.isdigit() else None
        for member_status in status["members"]:
            user_id = member_status.get("user_id")
            if not guild or not isinstance(user_id, str) or not user_id.isdigit():
                continue
            key = (guild.id, int(user_id))
            display_name = _participation_member_names.get(key)
            if display_name is None:
                member = guild.get_member(key[1])
                if member is None:
                    try:
                        member = await guild.fetch_member(key[1])
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        continue
                display_name = member.display_name
                _participation_member_names[key] = display_name
            member_status["display_name"] = display_name
    return live_voice


async def _export_vip_voice_status(client: discord.Client) -> list[dict]:
    statuses: list[dict] = []
    for guild in client.guilds:
        channels: list[dict] = []
        for config in vip_voice_repo.list_vip_channels(guild.id):
            channel = guild.get_channel(config.channel_id)
            role = guild.get_role(config.role_id)
            voice_channel = channel if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) else None
            role_members = {
                member.id: {"user_id": str(member.id), "display_name": member.display_name}
                for member in role.members
            } if role else {}
            occupants = []
            for cached_member in voice_channel.members if voice_channel else []:
                member = cached_member
                try:
                    member = await guild.fetch_member(cached_member.id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
                has_access_role = bool(role and any(member_role.id == role.id for member_role in member.roles))
                if has_access_role:
                    role_members[member.id] = {"user_id": str(member.id), "display_name": member.display_name}
                occupants.append(
                    {
                        "user_id": str(member.id),
                        "display_name": member.display_name,
                        "has_access_role": has_access_role,
                    }
                )
            pending_requests = []
            for request in vip_voice_repo.list_pending_requests(guild.id, config.channel_id):
                member = guild.get_member(request.requester_user_id)
                pending_requests.append(
                    {
                        "user_id": str(request.requester_user_id),
                        "display_name": member.display_name if member else None,
                        "created_at": request.created_at.isoformat(),
                        "expires_at": request.expires_at.isoformat(),
                    }
                )
            everyone_connect = voice_channel.overwrites_for(guild.default_role).connect if voice_channel else None
            role_connect = voice_channel.overwrites_for(role).connect if voice_channel and role else None
            channels.append(
                {
                    "channel_id": str(config.channel_id),
                    "channel_name": voice_channel.name if voice_channel else None,
                    "kind": "stage" if isinstance(voice_channel, discord.StageChannel) else "voice" if voice_channel else "missing",
                    "role_id": str(config.role_id),
                    "role_name": role.name if role else None,
                    "available": voice_channel is not None and role is not None,
                    "access_locked": everyone_connect is False,
                    "role_can_connect": role_connect is True,
                    "occupants": occupants,
                    "role_members": sorted(role_members.values(), key=lambda member: member["display_name"].casefold()),
                    "pending_requests": pending_requests,
                }
            )
        if not channels and vip_voice_repo.get_vip_panel(guild.id) is None:
            continue
        panel = vip_voice_repo.get_vip_panel(guild.id)
        statuses.append(
            {
                "guild_id": str(guild.id),
                "generated_at": discord.utils.utcnow().isoformat(),
                "panel": {"channel_id": str(panel.channel_id), "message_id": str(panel.message_id)} if panel else None,
                "channels": channels,
            }
        )
    return statuses


async def push_hub_snapshot_for_client(client: discord.Client) -> None:
    if not is_hub_sync_enabled():
        return
    snapshot = export_raid_signup_snapshot()
    snapshot["participation_settings"] = export_participation_settings_snapshot()
    snapshot["participation_raffle"] = {"states": export_raffle_state_snapshot(), "action_receipts": export_raffle_action_receipts()}
    snapshot["participation_leaderboards"] = await _export_participation_leaderboards(client)
    snapshot["participation_live_voice"] = await _export_live_voice(client)
    snapshot["vip_voice_status"] = await _export_vip_voice_status(client)
    snapshot["discord_guilds"] = _export_discord_guilds(client)
    try:
        await asyncio.to_thread(_request_json, "PUT", "/api/raid-signups", {"data": snapshot})
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"Hub sync push failed: {exc}")


def schedule_hub_push() -> None:
    """Fire-and-forget snapshot push from interaction handlers."""
    if not is_hub_sync_enabled():
        return
    try:
        asyncio.create_task(push_hub_snapshot())
    except RuntimeError:
        pass


async def _ensure_discord_message(client: discord.Client, event_id: int) -> None:
    event = get_raid_event(event_id)
    if not event or event.get("message_id"):
        return

    channel_id = event.get("channel_id")
    if not channel_id:
        return

    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except discord.NotFound:
            print(f"Hub sync could not post event {event_id}: channel {channel_id} not found")
            return
        except discord.Forbidden:
            print(f"Hub sync could not post event {event_id}: missing access to channel {channel_id}")
            return

    if not isinstance(channel, discord.abc.Messageable):
        print(f"Hub sync could not post event {event_id}: channel {channel_id} is not messageable")
        return

    from views.raid_signup import RaidSignupView

    try:
        message = await channel.send(
            embed=build_raid_signup_embed(event, guild=getattr(channel, "guild", None)),
            view=RaidSignupView(),
        )
    except discord.Forbidden:
        print(f"Hub sync could not post event {event_id}: cannot send to channel {channel_id}")
        return
    except discord.NotFound:
        print(f"Hub sync could not post event {event_id}: channel {channel_id} disappeared")
        return

    attach_raid_message(event_id, message.id)
    print(f"Hub sync posted event {event_id} to channel {channel_id} as message {message.id}")


async def _delete_discord_message(client: discord.Client, event: dict) -> None:
    """Delete the signup Discord message for a removed hub event when possible."""
    channel_id = event.get("channel_id")
    message_id = event.get("message_id")
    if not channel_id or not message_id:
        return
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            return

    if not isinstance(channel, discord.abc.Messageable):
        return

    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
    except (discord.NotFound, discord.Forbidden):
        return


async def _ensure_participation_panel(client: discord.Client, settings) -> None:
    if not settings or not settings.enabled or not settings.configured or not settings.panel_channel_id:
        return

    channel = client.get_channel(settings.panel_channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(settings.panel_channel_id)
        except discord.NotFound:
            print(f"Hub sync could not create participation panel: channel {settings.panel_channel_id} not found")
            return
        except discord.Forbidden:
            print(f"Hub sync could not create participation panel: missing access to channel {settings.panel_channel_id}")
            return

    if not isinstance(channel, discord.abc.Messageable):
        return

    from views.participation_panel import ParticipationPanelView

    if settings.panel_message_id:
        try:
            message = await channel.fetch_message(settings.panel_message_id)
            await message.edit(embed=build_panel_embed(settings), view=ParticipationPanelView())
            return
        except discord.NotFound:
            pass
        except discord.Forbidden:
            return

    try:
        message = await channel.send(embed=build_panel_embed(settings), view=ParticipationPanelView())
    except (discord.Forbidden, discord.NotFound):
        return
    update_participation_panel(settings.guild_id, settings.panel_channel_id, message.id)
    print(f"Hub sync posted participation panel to channel {settings.panel_channel_id} as message {message.id}")


async def _apply_participation_settings(client: discord.Client, snapshot: dict) -> None:
    settings_list = snapshot.get("participation_settings")
    if not isinstance(settings_list, list):
        return
    for payload in settings_list:
        if not isinstance(payload, dict):
            continue
        try:
            settings = upsert_participation_settings_from_snapshot(payload)
            if settings:
                await _ensure_participation_panel(client, settings)
        except Exception as exc:
            print(f"Hub sync participation settings apply failed: {exc}")


async def _publish_pending_raffle_draws(client: discord.Client) -> None:
    for period in get_pending_raffle_publications():
        settings = get_participation_settings(period.guild_id)
        if not settings or not settings.raffle_publish_channel_id:
            continue
        channel = client.get_channel(settings.raffle_publish_channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(settings.raffle_publish_channel_id)
            except (discord.NotFound, discord.Forbidden):
                continue
        if not isinstance(channel, discord.abc.Messageable):
            continue
        try:
            from views.raffle_details import RaffleDetailsView
            message = await channel.send(
                f"Raffle winner: <@{period.winner_user_id}>\n"
                f"Tickets: {period.total_tickets_at_draw} | Winning number: {period.winning_number}",
                view=RaffleDetailsView(period.id),
            )
        except (discord.NotFound, discord.Forbidden):
            continue
        mark_raffle_published(period.id, channel.id, message.id)


async def _apply_raffle_actions(client: discord.Client, snapshot: dict) -> None:
    raffle = snapshot.get("participation_raffle")
    actions = raffle.get("actions") if isinstance(raffle, dict) else snapshot.get("participation_raffle_actions")
    if not isinstance(actions, list):
        return
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_id = action.get("action_id") or action.get("id")
        action_type = action.get("type")
        guild_id = action.get("guild_id")
        if not isinstance(action_id, str) or action_type not in {"RESET", "DRAW", "REPLACE_EXCLUSIVE_WINNERS", "ADD_DEBUG_TICKETS"}:
            continue
        try:
            guild_id = int(guild_id)
        except (TypeError, ValueError):
            continue
        if get_action_receipt(action_id) is not None:
            continue
        try:
            if action_type == "RESET":
                result = {"reset": bool(reset_current_period(guild_id, discord.utils.utcnow()))}
            elif action_type == "ADD_DEBUG_TICKETS":
                user_id = int(action.get("user_id"))
                tickets = int(action.get("tickets"))
                period, total = add_debug_tickets(guild_id, user_id, tickets, discord.utils.utcnow())
                result = {"period_id": str(period.id), "user_id": str(user_id), "tickets": total}
            elif action_type == "REPLACE_EXCLUSIVE_WINNERS":
                values = action.get("user_ids")
                if not isinstance(values, list):
                    raise ValueError("user_ids must be a list")
                result = {"exclusive_winner_user_ids": [str(value) for value in replace_exclusive_winner_ids(guild_id, (int(value) for value in values))]}
            else:
                settings = get_participation_settings(guild_id)
                if not settings or not settings.configured or not settings.raffle_publish_channel_id:
                    raise ValueError("participation or raffle announcement channel is not configured")
                result = draw_current_period(guild_id, discord.utils.utcnow(), calculator_for_settings(settings))
                result["winner_user_id"] = str(result["winner_user_id"])
            save_action_receipt(action_id, guild_id, action_type, result)
        except Exception as exc:
            save_action_receipt(action_id, guild_id, action_type, {"error": str(exc)})


def _event_needs_import(event: dict) -> bool:
    """Return True only when the hub event differs from local state."""
    existing = get_raid_event_by_external_id(str(event.get("external_id") or ""))
    if not existing:
        return True

    comparable_event_fields = (
        "guild_id",
        "channel_id",
        "message_id",
        "title",
        "leader_name",
        "starts_at",
        "created_by_user_id",
        "is_open",
        "confirmed_roster",
        "bench_roster",
        "roster_publish_channel_id",
        "roster_publish_requested_at",
        "roster_published_at",
    )
    for field in comparable_event_fields:
        incoming = event.get(field)
        current = existing.get(field)
        if field == "confirmed_roster":
            import json

            incoming = incoming if isinstance(incoming, list) else []
            try:
                current = json.loads(existing.get("confirmed_roster_json") or "[]")
            except json.JSONDecodeError:
                current = []
        if field == "bench_roster":
            import json

            incoming = incoming if isinstance(incoming, list) else []
            try:
                current = json.loads(existing.get("bench_roster_json") or "[]")
            except json.JSONDecodeError:
                current = []
        if field in {"guild_id", "channel_id", "message_id", "created_by_user_id"}:
            incoming = str(incoming) if incoming is not None else None
            current = str(current) if current is not None else None
        if field == "is_open":
            incoming = bool(incoming)
            current = bool(current)
        if incoming != current:
            return True

    incoming_signups = event.get("signups") if isinstance(event.get("signups"), list) else []
    current_signups = list_raid_signups(existing["id"])

    def normalize_signup(signup: dict) -> tuple:
        return (
            str(signup.get("user_id")),
            signup.get("display_name"),
            signup.get("status"),
            signup.get("class_key"),
            signup.get("spec_key"),
            signup.get("note"),
        )

    return sorted(normalize_signup(signup) for signup in incoming_signups) != sorted(
        normalize_signup(signup) for signup in current_signups
    )


async def apply_hub_snapshot(client: discord.Client, snapshot: dict | None) -> None:
    if not snapshot:
        return
    if snapshot.get("source") == "wipybot":
        return

    await _apply_participation_settings(client, snapshot)
    await _apply_raffle_actions(client, snapshot)
    await _publish_pending_raffle_draws(client)

    deleted_external_ids = snapshot.get("deleted_external_ids")
    if isinstance(deleted_external_ids, list):
        for external_id in deleted_external_ids:
            if isinstance(external_id, str):
                event = get_raid_event_by_external_id(external_id)
                if event:
                    await _delete_discord_message(client, event)
                delete_raid_event_by_external_id(external_id)

    events = snapshot.get("events")
    if not isinstance(events, list):
        return

    touched_event_ids: list[int] = []
    for event in events:
        if not isinstance(event, dict) or not event.get("external_id"):
            continue
        if not _event_needs_import(event):
            continue
        try:
            event_id = update_raid_event_from_snapshot(event)
            signups = event.get("signups") if isinstance(event.get("signups"), list) else []
            replace_raid_signups_from_snapshot(event_id, signups)
            await _ensure_discord_message(client, event_id)
            refreshed_event = get_raid_event(event_id)
            if refreshed_event:
                refreshed_event["confirmed_roster"] = event.get("confirmed_roster") if isinstance(event.get("confirmed_roster"), list) else []
                refreshed_event["bench_roster"] = event.get("bench_roster") if isinstance(event.get("bench_roster"), list) else []
                if await publish_confirmed_roster(client, refreshed_event):
                    refreshed_event = get_raid_event(event_id)
            if refreshed_event and refreshed_event.get("message_id"):
                touched_event_ids.append(event_id)
        except Exception as exc:
            print(f"Hub sync apply failed for event {event.get('external_id')}: {exc}")

    for event_id in touched_event_ids:
        await refresh_raid_signup_message(client, event_id)


async def sync_once(client: discord.Client) -> None:
    if not is_hub_sync_enabled():
        return
    snapshot = await fetch_hub_snapshot()
    await apply_hub_snapshot(client, snapshot)
    await push_hub_snapshot_for_client(client)


async def hub_sync_loop(client: discord.Client) -> None:
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            await sync_once(client)
        except Exception as exc:
            print(f"Hub sync loop failed: {exc}")
        await asyncio.sleep(max(5, HUB_SYNC_INTERVAL_SECONDS))
