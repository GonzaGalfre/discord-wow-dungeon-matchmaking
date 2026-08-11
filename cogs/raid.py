"""Raid signup commands for WipyBot."""

from __future__ import annotations

import zlib
import random

import discord
from discord import app_commands
from discord.ext import commands

from models.guild_settings import save_guild_settings, update_signup_message_id
from models.raid_signup import (
    attach_raid_message,
    create_raid_event,
    delete_dummy_raid_signups,
    get_raid_event,
    set_raid_event_open,
    upsert_raid_signup,
)
from services.hub_sync import schedule_hub_push
from services.raid_catalog import CLASSES, get_class, get_spec
from services.raid_signup import (
    STATUS_ABSENCE,
    STATUS_ATTENDING,
    STATUS_BENCH,
    STATUS_LATE,
    STATUS_TENTATIVE,
    build_raid_signup_embed,
    refresh_raid_signup_message,
)
from views.raid_signup import RaidSignupView


DUMMY_USER_ID_START = 900000000000000000
SEED_NAMES = [
    "Jhin",
    "Nano",
    "Plop",
    "Neflit",
    "Nanaue",
    "Myrin",
    "Amari",
    "Larien",
    "Trinley",
    "Adnes",
    "Tronquito",
    "Malverion",
    "Rhangu",
    "Shaula",
    "Syranee",
    "Infinity",
    "Noshog",
    "Navi",
    "Frellian",
    "Perfectx",
    "Pando",
    "Algodon",
    "Wazapen",
    "Natjoe",
    "Lanathel",
    "Bolker",
    "Maicilidan",
    "Aldor",
    "Kyra",
    "Velkan",
    "Runa",
    "Thalor",
]
STATUS_CHOICES = [
    app_commands.Choice(name="Going", value=STATUS_ATTENDING),
    app_commands.Choice(name="Bench", value=STATUS_BENCH),
    app_commands.Choice(name="Late", value=STATUS_LATE),
    app_commands.Choice(name="Tentative", value=STATUS_TENTATIVE),
    app_commands.Choice(name="Absence", value=STATUS_ABSENCE),
]


def _dummy_user_id(event_id: int, name: str) -> int:
    seed = f"{event_id}:{name.strip().lower()}".encode("utf-8")
    return DUMMY_USER_ID_START + zlib.crc32(seed)


def _normalize_class_key(value: str) -> str | None:
    normalized = value.strip().lower().replace(" ", "_")
    if normalized in CLASSES:
        return normalized
    for class_key, class_data in CLASSES.items():
        if class_data["name"].lower() == value.strip().lower():
            return class_key
    return None


def _normalize_spec_key(class_key: str, value: str) -> str | None:
    class_data = get_class(class_key)
    if not class_data:
        return None
    normalized = value.strip().lower().replace(" ", "_")
    if normalized in class_data["specs"]:
        return normalized
    for spec_key, spec_data in class_data["specs"].items():
        if spec_data["name"].lower() == value.strip().lower():
            return spec_key
    return None


def _spec_pool_for_role(role: str) -> list[tuple[str, str]]:
    pool = []
    for class_key, class_data in CLASSES.items():
        for spec_key, spec_data in class_data["specs"].items():
            if spec_data["role"] == role:
                pool.append((class_key, spec_key))
    return pool


def _random_spec_from_roles(roles: list[str]) -> tuple[str, str]:
    pool = []
    for role in roles:
        pool.extend(_spec_pool_for_role(role))
    return random.choice(pool)


class RaidCog(commands.Cog):
    """Commands for creating and managing raid signup messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def class_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        needle = current.strip().lower()
        choices = []
        for class_key, class_data in CLASSES.items():
            label = class_data["name"]
            if not needle or needle in label.lower() or needle in class_key:
                choices.append(app_commands.Choice(name=label, value=class_key))
        return choices[:25]

    async def spec_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        class_value = getattr(interaction.namespace, "class_name", "") or ""
        class_key = _normalize_class_key(class_value)
        if not class_key:
            return []

        class_data = get_class(class_key)
        needle = current.strip().lower()
        choices = []
        for spec_key, spec_data in class_data["specs"].items():
            label = spec_data["name"]
            if not needle or needle in label.lower() or needle in spec_key:
                choices.append(app_commands.Choice(name=label, value=spec_key))
        return choices[:25]

    @app_commands.command(
        name="raid_create",
        description="Create a raid signup message in this channel.",
    )
    @app_commands.describe(
        title="Raid title shown in the signup message.",
        raid_date="Raid date text, e.g. 30 de junio de 2026.",
        raid_time="Raid time text, e.g. 21:45.",
        leader="Optional raid leader name.",
    )
    @app_commands.default_permissions(administrator=True)
    async def raid_create_command(
        self,
        interaction: discord.Interaction,
        title: str,
        raid_date: str,
        raid_time: str,
        leader: str | None = None,
    ) -> None:
        """Create and publish a new raid signup event."""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        starts_at = f"{raid_date.strip()} {raid_time.strip()}"
        leader_name = leader.strip() if leader else interaction.user.display_name

        save_guild_settings(
            guild_id=guild_id,
            guild_name=interaction.guild.name,
            signup_channel_id=channel_id,
        )

        event_id = create_raid_event(
            guild_id=guild_id,
            channel_id=channel_id,
            title=title.strip(),
            starts_at=starts_at,
            leader_name=leader_name,
            created_by_user_id=interaction.user.id,
        )
        event = {
            "id": event_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": None,
            "title": title.strip(),
            "leader_name": leader_name,
            "starts_at": starts_at,
            "created_by_user_id": interaction.user.id,
            "is_open": 1,
        }

        message = await interaction.channel.send(
            embed=build_raid_signup_embed(event, [], guild=interaction.guild),
            view=RaidSignupView(),
        )
        attach_raid_message(event_id, message.id)
        update_signup_message_id(guild_id, message.id)
        schedule_hub_push()

        await interaction.followup.send(
            f"Raid signup created: {message.jump_url}\nEvent ID: `{event_id}`",
            ephemeral=True,
        )

    @app_commands.command(
        name="raid_close",
        description="Close a raid signup by event ID.",
    )
    @app_commands.describe(event_id="Database event ID to close.")
    @app_commands.default_permissions(administrator=True)
    async def raid_close_command(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        """Close an event to prevent further signup changes."""
        updated = set_raid_event_open(event_id, False)
        if not updated:
            await interaction.response.send_message("Raid event not found.", ephemeral=True)
            return

        await refresh_raid_signup_message(self.bot, event_id)
        schedule_hub_push()
        await interaction.response.send_message("Raid signup closed.", ephemeral=True)

    @app_commands.command(
        name="raid_open",
        description="Re-open a raid signup by event ID.",
    )
    @app_commands.describe(event_id="Database event ID to open.")
    @app_commands.default_permissions(administrator=True)
    async def raid_open_command(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        """Re-open an event to allow signup changes again."""
        updated = set_raid_event_open(event_id, True)
        if not updated:
            await interaction.response.send_message("Raid event not found.", ephemeral=True)
            return

        await refresh_raid_signup_message(self.bot, event_id)
        schedule_hub_push()
        await interaction.response.send_message("Raid signup opened.", ephemeral=True)

    @app_commands.command(
        name="raid_dummy_add",
        description="Add a dummy signup to a raid event for testing.",
    )
    @app_commands.describe(
        event_id="Raid event ID shown in the signup footer.",
        name="Dummy player display name.",
        class_name="Class to add.",
        spec="Spec to add.",
        status="Attendance status.",
    )
    @app_commands.choices(status=STATUS_CHOICES)
    @app_commands.autocomplete(class_name=class_autocomplete, spec=spec_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def raid_dummy_add_command(
        self,
        interaction: discord.Interaction,
        event_id: int,
        name: str,
        class_name: str,
        spec: str,
        status: str = STATUS_ATTENDING,
    ) -> None:
        """Add or update a fake signup for visual testing."""
        event = get_raid_event(event_id)
        if not event:
            await interaction.response.send_message("Raid event not found.", ephemeral=True)
            return

        class_key = _normalize_class_key(class_name)
        if not class_key:
            await interaction.response.send_message("Unknown class.", ephemeral=True)
            return

        spec_key = _normalize_spec_key(class_key, spec)
        if not spec_key or not get_spec(class_key, spec_key):
            await interaction.response.send_message("Unknown spec for that class.", ephemeral=True)
            return

        display_name = name.strip()
        if not display_name:
            await interaction.response.send_message("Name cannot be empty.", ephemeral=True)
            return

        upsert_raid_signup(
            event_id=event_id,
            user_id=_dummy_user_id(event_id, display_name),
            display_name=display_name,
            status=status,
            class_key=class_key,
            spec_key=spec_key,
        )
        await refresh_raid_signup_message(self.bot, event_id)
        schedule_hub_push()
        await interaction.response.send_message(
            f"Dummy signup added: **{display_name}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="raid_dummy_clear",
        description="Remove all dummy signups from a raid event.",
    )
    @app_commands.describe(event_id="Raid event ID shown in the signup footer.")
    @app_commands.default_permissions(administrator=True)
    async def raid_dummy_clear_command(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        """Remove fake signups created through /raid_dummy_add."""
        event = get_raid_event(event_id)
        if not event:
            await interaction.response.send_message("Raid event not found.", ephemeral=True)
            return

        removed = delete_dummy_raid_signups(event_id, DUMMY_USER_ID_START)
        await refresh_raid_signup_message(self.bot, event_id)
        schedule_hub_push()
        await interaction.response.send_message(
            f"Removed {removed} dummy signup(s).",
            ephemeral=True,
        )

    @app_commands.command(
        name="raid_dummy_seed",
        description="Add a full dummy raid roster for testing.",
    )
    @app_commands.describe(
        event_id="Raid event ID shown in the signup footer.",
        count="Total dummy players to create. Defaults to 25.",
        clear_existing="Remove previous dummy signups for this event first.",
    )
    @app_commands.default_permissions(administrator=True)
    async def raid_dummy_seed_command(
        self,
        interaction: discord.Interaction,
        event_id: int,
        count: app_commands.Range[int, 10, 40] = 25,
        clear_existing: bool = True,
    ) -> None:
        """Seed an event with a realistic test roster."""
        event = get_raid_event(event_id)
        if not event:
            await interaction.response.send_message("Raid event not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        removed = 0
        if clear_existing:
            removed = delete_dummy_raid_signups(event_id, DUMMY_USER_ID_START)

        status_plan = [STATUS_BENCH, STATUS_BENCH, STATUS_LATE, STATUS_LATE, STATUS_TENTATIVE, STATUS_TENTATIVE, STATUS_ABSENCE]
        attending_count = max(0, count - len(status_plan))
        role_plan = (
            ["tank"] * 2
            + ["healer"] * 4
            + ["melee"] * 7
            + ["ranged"] * max(0, attending_count - 13)
        )
        while len(role_plan) < attending_count:
            role_plan.append(random.choice(["melee", "ranged", "healer"]))
        random.shuffle(role_plan)

        names = SEED_NAMES.copy()
        random.shuffle(names)
        while len(names) < count:
            names.append(f"Dummy{len(names) + 1}")

        created = 0
        for index in range(count):
            display_name = names[index]
            if index < attending_count:
                status = STATUS_ATTENDING
                class_key, spec_key = _random_spec_from_roles([role_plan[index]])
            else:
                status = status_plan[index - attending_count]
                class_key, spec_key = _random_spec_from_roles(["tank", "healer", "melee", "ranged"])

            upsert_raid_signup(
                event_id=event_id,
                user_id=_dummy_user_id(event_id, display_name),
                display_name=display_name,
                status=status,
                class_key=class_key,
                spec_key=spec_key,
            )
            created += 1

        await refresh_raid_signup_message(self.bot, event_id)
        schedule_hub_push()
        await interaction.followup.send(
            f"Seeded {created} dummy signup(s). Removed {removed} previous dummy signup(s).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RaidCog(bot))
