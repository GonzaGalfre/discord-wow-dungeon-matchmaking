"""
Role selection views for the WoW Mythic+ LFG Bot.
"""

import asyncio
from typing import List

import discord

from config.settings import KEY_BRACKETS, MAX_KEY_LEVEL, MIN_KEY_LEVEL, ROLES
from models.queue import queue_manager
from services.match_flow import trigger_matchmaking_for_entry
from services.queue_preferences import bracket_to_range, requires_keystone_for_range
from services.queue_status import refresh_lfg_setup_message
from views.queue_entry_actions import QueueEntryActionsView


def _format_roles(roles: List[str]) -> str:
    if not roles:
        return "—"
    return " > ".join(f"{ROLES[role]['emoji']} {ROLES[role]['name']}" for role in roles if role in ROLES)


def _format_key_preference(bracket: str, key_min: int, key_max: int) -> str:
    if bracket in KEY_BRACKETS:
        return KEY_BRACKETS[bracket]["label"]
    return f"{key_min}-{key_max}"


async def _finish_solo_queue(
    interaction: discord.Interaction,
    roles: List[str],
    key_bracket: str,
    has_keystone: bool,
    keystone_level: int | None,
) -> None:
    guild_id = interaction.guild_id
    user_id = interaction.user.id
    username = interaction.user.display_name
    key_min, key_max = bracket_to_range(key_bracket)

    queue_manager.add(
        guild_id,
        user_id,
        username,
        key_min,
        key_max,
        roles=roles,
        has_keystone=has_keystone,
        keystone_level=keystone_level,
        key_bracket=key_bracket,
    )
    queue_entry = queue_manager.get(guild_id, user_id)
    queue_since_unix = int(queue_entry["timestamp"].timestamp()) if queue_entry else None
    await refresh_lfg_setup_message(interaction.client, guild_id, interaction.channel)

    result = await trigger_matchmaking_for_entry(
        interaction.client,
        guild_id,
        user_id,
        key_min,
        key_max,
        source="solo_queue",
        triggered_by_user_id=user_id,
        fallback_channel=interaction.channel,
    )
    key_text = _format_key_preference(key_bracket, key_min, key_max)
    roles_text = _format_roles(roles)

    if not result.get("matched"):
        keystone_text = "Sí" if has_keystone else "No"
        keystone_level_text = f" (+{keystone_level})" if keystone_level is not None else ""
        queue_since_line = (
            f"⏱️ **En cola desde:** <t:{queue_since_unix}:R>\n"
            if queue_since_unix is not None
            else ""
        )
        await interaction.response.edit_message(
            content=(
                "✅ **¡Estás en la cola!**\n\n"
                f"🎭 **Roles:** {roles_text}\n"
                f"🗝️ **Preferencia de llaves:** {key_text}\n"
                f"🔑 **Tienes piedra:** {keystone_text}{keystone_level_text}\n\n"
                f"{queue_since_line}"
                "¡Te avisaremos cuando haya grupo compatible!\n\n"
                "Puedes salir de cola o verificar estado desde este mismo mensaje."
            ),
            view=QueueEntryActionsView(guild_id=guild_id, owner_user_id=user_id),
        )
        return

    user_count = int(result.get("user_count", 0))
    joining_existing = bool(result.get("joining_existing"))
    message_type = (
        "¡Te has unido a un grupo existente!"
        if joining_existing
        else f"¡Nuevo grupo formado con {user_count} jugadores!"
    )
    await interaction.response.edit_message(
        content=(
            f"🎉 **{message_type}**\n"
            "Se ha enviado una notificación al canal de emparejamientos.\n\n"
            "*Este mensaje se cerrará en 5 segundos...*"
        ),
        view=None,
    )
    await asyncio.sleep(5)
    try:
        await interaction.delete_original_response()
    except discord.errors.NotFound:
        pass


class KeystoneLevelSelectView(discord.ui.View):
    """
    Select keystone level when the user has one.
    """

    def __init__(self, roles: List[str], key_bracket: str):
        super().__init__(timeout=60)
        self.roles = roles
        self.key_bracket = key_bracket
        options = [
            discord.SelectOption(
                label=f"Nivel {i}",
                value=str(i),
                description=f"Tengo una piedra +{i}",
                emoji="🔑",
            )
            for i in range(MIN_KEY_LEVEL, MAX_KEY_LEVEL + 1)
        ]
        self.key_select = discord.ui.Select(
            placeholder=f"¿Qué nivel de piedra tienes? ({MIN_KEY_LEVEL}-{MAX_KEY_LEVEL})",
            options=options,
            custom_id="solo_keystone_level_select",
        )
        self.key_select.callback = self.keystone_level_selected
        self.add_item(self.key_select)

    async def keystone_level_selected(self, interaction: discord.Interaction):
        level = int(self.key_select.values[0])
        await _finish_solo_queue(
            interaction,
            roles=self.roles,
            key_bracket=self.key_bracket,
            has_keystone=True,
            keystone_level=level,
        )


class KeystoneChoiceView(discord.ui.View):
    """
    Ask if user has keystone (only for 2+ ranges).
    """

    def __init__(self, roles: List[str], key_bracket: str):
        super().__init__(timeout=60)
        self.roles = roles
        self.key_bracket = key_bracket

    @discord.ui.button(label="Sí, tengo piedra", style=discord.ButtonStyle.success, emoji="🔑")
    async def has_keystone_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="🔑 Perfecto. ¿Qué nivel de piedra tienes?",
            view=KeystoneLevelSelectView(self.roles, self.key_bracket),
        )

    @discord.ui.button(label="No tengo piedra", style=discord.ButtonStyle.secondary, emoji="➖")
    async def no_keystone_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await _finish_solo_queue(
            interaction,
            roles=self.roles,
            key_bracket=self.key_bracket,
            has_keystone=False,
            keystone_level=None,
        )


class KeyBracketSelectView(discord.ui.View):
    """
    One-step bracket selection replacing min/max flow.
    """

    def __init__(self, roles: List[str]):
        super().__init__(timeout=60)
        self.roles = roles
        options = [
            discord.SelectOption(
                label="0",
                value="0",
                description="Mythic 0 (sin piedra)",
                emoji="🧭",
            ),
            discord.SelectOption(
                label="2-5",
                value="2-5",
                description="Llaves bajas",
                emoji="🗝️",
            ),
            discord.SelectOption(
                label="6-9",
                value="6-9",
                description="Llaves medias",
                emoji="🗝️",
            ),
            discord.SelectOption(
                label="10+",
                value="10+",
                description="Llaves altas",
                emoji="🔥",
            ),
            discord.SelectOption(
                label="Anything",
                value="anything",
                description="0 y cualquier + desde 2",
                emoji="🌐",
            ),
        ]
        self.bracket_select = discord.ui.Select(
            placeholder="Selecciona tu bracket de llaves...",
            options=options,
            custom_id="solo_key_bracket_select",
        )
        self.bracket_select.callback = self.bracket_selected
        self.add_item(self.bracket_select)

    async def bracket_selected(self, interaction: discord.Interaction):
        bracket = self.bracket_select.values[0]
        key_min, key_max = bracket_to_range(bracket)
        roles_text = _format_roles(self.roles)
        bracket_text = _format_key_preference(bracket, key_min, key_max)

        if requires_keystone_for_range(key_min, key_max):
            await interaction.response.edit_message(
                content=(
                    f"🎭 **Roles:** {roles_text}\n"
                    f"🗝️ **Bracket:** {bracket_text}\n\n"
                    "¿Tienes piedra angular disponible?"
                ),
                view=KeystoneChoiceView(self.roles, bracket),
            )
            return

        await _finish_solo_queue(
            interaction,
            roles=self.roles,
            key_bracket=bracket,
            has_keystone=False,
            keystone_level=None,
        )


class MultiRoleSelectView(discord.ui.View):
    """
    Optional multi-role step preserving selected priority order.
    """

    def __init__(self):
        super().__init__(timeout=60)
        options = [
            discord.SelectOption(label="Tanque", value="tank", emoji="🛡️", description="Tanque"),
            discord.SelectOption(label="Sanador", value="healer", emoji="💚", description="Sanador"),
            discord.SelectOption(label="DPS", value="dps", emoji="⚔️", description="DPS"),
        ]
        self.role_select = discord.ui.Select(
            placeholder="Selecciona 1-3 roles (orden de prioridad)",
            options=options,
            custom_id="solo_multi_role_select",
            min_values=1,
            max_values=3,
        )
        self.role_select.callback = self.multi_role_selected
        self.add_item(self.role_select)

    async def multi_role_selected(self, interaction: discord.Interaction):
        roles = [value for value in self.role_select.values if value in ROLES]
        await interaction.response.edit_message(
            content=(
                f"🎭 **Roles seleccionados:** {_format_roles(roles)}\n\n"
                "Ahora selecciona tu bracket de llaves:"
            ),
            view=KeyBracketSelectView(roles),
        )


class RoleSelectView(discord.ui.View):
    """
    Fast solo role selector with optional multi-role path.
    """

    def __init__(self):
        super().__init__(timeout=60)

    async def _continue_with_roles(self, interaction: discord.Interaction, roles: List[str]):
        await interaction.response.edit_message(
            content=f"🎭 **Roles:** {_format_roles(roles)}\n\nSelecciona tu bracket de llaves:",
            view=KeyBracketSelectView(roles),
        )

    @discord.ui.button(label="Tanque", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def tank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._continue_with_roles(interaction, ["tank"])

    @discord.ui.button(label="Sanador", style=discord.ButtonStyle.success, emoji="💚")
    async def healer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._continue_with_roles(interaction, ["healer"])

    @discord.ui.button(label="DPS", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def dps_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._continue_with_roles(interaction, ["dps"])

    @discord.ui.button(label="+ Añadir más roles", style=discord.ButtonStyle.secondary, emoji="➕")
    async def multi_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=(
                "Selecciona tus roles en orden de prioridad.\n"
                "Tip: si quieres cola rápida, puedes elegir solo 1 rol."
            ),
            view=MultiRoleSelectView(),
        )
