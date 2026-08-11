"""Discord UI components for raid signups."""

from __future__ import annotations

import discord

from models.raid_signup import (
    delete_raid_signup,
    get_raid_event_by_message,
    get_raid_signup,
    update_raid_signup_status,
    upsert_raid_signup,
)
from services.hub_sync import schedule_hub_push
from services.raid_catalog import CLASSES, class_emoji, get_class, spec_emoji
from services.raid_signup import (
    STATUS_ABSENCE,
    STATUS_ATTENDING,
    STATUS_BENCH,
    STATUS_LATE,
    STATUS_TENTATIVE,
    build_raid_signup_embed,
    refresh_raid_signup_message,
)


def _member_display_name(interaction: discord.Interaction) -> str:
    if isinstance(interaction.user, discord.Member):
        return interaction.user.display_name
    return interaction.user.name


async def _event_from_interaction(interaction: discord.Interaction) -> dict | None:
    if interaction.message is None:
        return None
    return get_raid_event_by_message(interaction.message.id)


async def _reject_if_closed(interaction: discord.Interaction, event: dict | None) -> bool:
    if event is None:
        await interaction.response.send_message(
            "This signup message is not linked to a raid event anymore.",
            ephemeral=True,
        )
        return True
    if not event.get("is_open", 1):
        await interaction.response.send_message(
            "This raid signup is closed.",
            ephemeral=True,
        )
        return True
    return False


class RaidClassSelect(discord.ui.Select):
    """Class dropdown attached to each raid signup message."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label=class_data["name"],
                value=class_key,
                emoji=discord.PartialEmoji.from_str(class_emoji(class_key)),
            )
            for class_key, class_data in CLASSES.items()
        ]
        super().__init__(
            placeholder="Select your class.",
            custom_id="raid_signup:class",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        event = await _event_from_interaction(interaction)
        if await _reject_if_closed(interaction, event):
            return

        class_key = self.values[0]
        class_data = get_class(class_key)
        if not class_data:
            await interaction.response.send_message("Unknown class selected.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Select your **{class_data['name']}** spec.",
            view=RaidSpecSelectView(event["id"], class_key, interaction.guild),
            ephemeral=True,
        )


class RaidSpecSelect(discord.ui.Select):
    """Ephemeral spec dropdown after a class is selected."""

    def __init__(self, event_id: int, class_key: str, guild: discord.Guild | None = None) -> None:
        self.event_id = event_id
        self.class_key = class_key
        class_data = get_class(class_key)
        options = []
        for spec_key, spec_data in class_data["specs"].items():
            icon = spec_emoji(class_key, spec_key, guild)
            options.append(
                discord.SelectOption(
                    label=spec_data["name"],
                    value=spec_key,
                    emoji=discord.PartialEmoji.from_str(icon) if icon else None,
                )
            )
        super().__init__(
            placeholder="Select your spec.",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id
        existing = get_raid_signup(self.event_id, user_id)
        status = existing.get("status") if existing else STATUS_ATTENDING

        upsert_raid_signup(
            event_id=self.event_id,
            user_id=user_id,
            display_name=_member_display_name(interaction),
            status=status if status != STATUS_ABSENCE else STATUS_ATTENDING,
            class_key=self.class_key,
            spec_key=self.values[0],
            note=existing.get("note") if existing else None,
        )
        await refresh_raid_signup_message(interaction.client, self.event_id)
        schedule_hub_push()
        await interaction.response.edit_message(
            content="You have been signed up to the event.",
            view=None,
        )


class RaidSpecSelectView(discord.ui.View):
    """Short-lived ephemeral spec picker."""

    def __init__(self, event_id: int, class_key: str, guild: discord.Guild | None = None) -> None:
        super().__init__(timeout=180)
        self.add_item(RaidSpecSelect(event_id, class_key, guild))


class RaidSignupView(discord.ui.View):
    """Persistent view for raid signup messages."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(RaidClassSelect())

    async def _set_status(self, interaction: discord.Interaction, status: str) -> None:
        event = await _event_from_interaction(interaction)
        if await _reject_if_closed(interaction, event):
            return

        update_raid_signup_status(
            event_id=event["id"],
            user_id=interaction.user.id,
            display_name=_member_display_name(interaction),
            status=status,
        )
        embed = build_raid_signup_embed(event, guild=interaction.guild)
        await interaction.response.edit_message(embed=embed, view=RaidSignupView())
        schedule_hub_push()
        await interaction.followup.send(
            f"Your raid signup status is now **{status}**.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Bench",
        style=discord.ButtonStyle.secondary,
        custom_id="raid_signup:bench",
        emoji="🪑",
        row=1,
    )
    async def bench_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._set_status(interaction, STATUS_BENCH)

    @discord.ui.button(
        label="Late",
        style=discord.ButtonStyle.secondary,
        custom_id="raid_signup:late",
        emoji="🕘",
        row=1,
    )
    async def late_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._set_status(interaction, STATUS_LATE)

    @discord.ui.button(
        label="Tentative",
        style=discord.ButtonStyle.secondary,
        custom_id="raid_signup:tentative",
        emoji="⚖️",
        row=1,
    )
    async def tentative_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._set_status(interaction, STATUS_TENTATIVE)

    @discord.ui.button(
        label="Absence",
        style=discord.ButtonStyle.secondary,
        custom_id="raid_signup:absence",
        emoji="🚫",
        row=1,
    )
    async def absence_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._set_status(interaction, STATUS_ABSENCE)

    @discord.ui.button(
        label="Remove",
        style=discord.ButtonStyle.danger,
        custom_id="raid_signup:remove",
        emoji="✖️",
        row=2,
    )
    async def remove_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        event = await _event_from_interaction(interaction)
        if await _reject_if_closed(interaction, event):
            return

        removed = delete_raid_signup(event["id"], interaction.user.id)
        embed = build_raid_signup_embed(event, guild=interaction.guild)
        await interaction.response.edit_message(embed=embed, view=RaidSignupView())
        schedule_hub_push()
        message = "Your signup was removed." if removed else "You were not signed up."
        await interaction.followup.send(message, ephemeral=True)
