"""
Group selection views for the WoW Mythic+ LFG Bot.
"""

import asyncio
from typing import Dict

import discord

from config.settings import KEY_BRACKETS, MAX_KEY_LEVEL, MIN_KEY_LEVEL
from models.queue import queue_manager
from services.match_flow import trigger_matchmaking_for_entry
from services.queue_preferences import bracket_to_range, requires_keystone_for_range
from services.queue_status import refresh_lfg_setup_message
from views.queue_entry_actions import QueueEntryActionsView


def _format_compact(composition: Dict[str, int]) -> str:
    parts = []
    if composition["tank"] > 0:
        parts.append(f"🛡️ {composition['tank']}")
    if composition["healer"] > 0:
        parts.append(f"💚 {composition['healer']}")
    if composition["dps"] > 0:
        parts.append(f"⚔️ {composition['dps']}")
    return " • ".join(parts)


def _format_detailed(composition: Dict[str, int]) -> str:
    parts = []
    if composition["tank"] > 0:
        parts.append(f"🛡️ {composition['tank']} Tanque(s)")
    if composition["healer"] > 0:
        parts.append(f"💚 {composition['healer']} Sanador(es)")
    if composition["dps"] > 0:
        parts.append(f"⚔️ {composition['dps']} DPS")
    return " • ".join(parts)


def _format_bracket_text(bracket: str, key_min: int, key_max: int) -> str:
    if bracket in KEY_BRACKETS:
        return KEY_BRACKETS[bracket]["label"]
    return f"{key_min}-{key_max}"


async def _finish_group_queue(
    interaction: discord.Interaction,
    composition: Dict[str, int],
    key_bracket: str,
    has_keystone: bool,
    keystone_level: int | None,
) -> None:
    guild_id = interaction.guild_id
    user_id = interaction.user.id
    username = interaction.user.display_name
    key_min, key_max = bracket_to_range(key_bracket)
    total_players = sum(composition.values())
    composition_text = _format_detailed(composition)

    queue_manager.add(
        guild_id,
        user_id,
        username,
        key_min,
        key_max,
        composition=composition,
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
        source="group_queue",
        triggered_by_user_id=user_id,
        fallback_channel=interaction.channel,
    )
    bracket_text = _format_bracket_text(key_bracket, key_min, key_max)

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
                "✅ **¡Tu grupo está en la cola!**\n\n"
                f"👥 **Composición:** {composition_text}\n"
                f"👤 **Jugadores:** {total_players}\n"
                f"🗝️ **Bracket:** {bracket_text}\n"
                f"🔑 **Piedra en el grupo:** {keystone_text}{keystone_level_text}\n\n"
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
        "¡Tu grupo se ha unido a un match existente!"
        if joining_existing
        else f"¡Nuevo match formado con {user_count} jugadores/grupos!"
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


class GroupKeystoneLevelSelectView(discord.ui.View):
    def __init__(self, composition: Dict[str, int], key_bracket: str):
        super().__init__(timeout=60)
        self.composition = composition
        self.key_bracket = key_bracket
        options = [
            discord.SelectOption(
                label=f"Nivel {i}",
                value=str(i),
                description=f"El grupo tiene una piedra +{i}",
                emoji="🔑",
            )
            for i in range(MIN_KEY_LEVEL, MAX_KEY_LEVEL + 1)
        ]
        self.key_select = discord.ui.Select(
            placeholder=f"¿Qué nivel de piedra tiene tu grupo? ({MIN_KEY_LEVEL}-{MAX_KEY_LEVEL})",
            options=options,
            custom_id="group_keystone_level_select",
        )
        self.key_select.callback = self.keystone_level_selected
        self.add_item(self.key_select)

    async def keystone_level_selected(self, interaction: discord.Interaction):
        level = int(self.key_select.values[0])
        await _finish_group_queue(
            interaction,
            composition=self.composition,
            key_bracket=self.key_bracket,
            has_keystone=True,
            keystone_level=level,
        )


class GroupKeystoneChoiceView(discord.ui.View):
    def __init__(self, composition: Dict[str, int], key_bracket: str):
        super().__init__(timeout=60)
        self.composition = composition
        self.key_bracket = key_bracket

    @discord.ui.button(label="Sí, alguien tiene piedra", style=discord.ButtonStyle.success, emoji="🔑")
    async def has_keystone_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="🔑 ¿Qué nivel de piedra tiene alguien en tu grupo?",
            view=GroupKeystoneLevelSelectView(self.composition, self.key_bracket),
        )

    @discord.ui.button(label="No, nadie tiene piedra", style=discord.ButtonStyle.secondary, emoji="➖")
    async def no_keystone_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await _finish_group_queue(
            interaction,
            composition=self.composition,
            key_bracket=self.key_bracket,
            has_keystone=False,
            keystone_level=None,
        )


class GroupKeyBracketSelectView(discord.ui.View):
    def __init__(self, composition: Dict[str, int]):
        super().__init__(timeout=60)
        self.composition = composition
        options = [
            discord.SelectOption(label="0", value="0", description="Mythic 0", emoji="🧭"),
            discord.SelectOption(label="2-5", value="2-5", description="Llaves bajas", emoji="🗝️"),
            discord.SelectOption(label="6-9", value="6-9", description="Llaves medias", emoji="🗝️"),
            discord.SelectOption(label="10+", value="10+", description="Llaves altas", emoji="🔥"),
            discord.SelectOption(label="Anything", value="anything", description="0 y cualquier +", emoji="🌐"),
        ]
        self.bracket_select = discord.ui.Select(
            placeholder="Selecciona el bracket de llaves del grupo...",
            options=options,
            custom_id="group_key_bracket_select",
        )
        self.bracket_select.callback = self.bracket_selected
        self.add_item(self.bracket_select)

    async def bracket_selected(self, interaction: discord.Interaction):
        bracket = self.bracket_select.values[0]
        key_min, key_max = bracket_to_range(bracket)
        bracket_text = _format_bracket_text(bracket, key_min, key_max)
        if requires_keystone_for_range(key_min, key_max):
            await interaction.response.edit_message(
                content=(
                    f"👥 **Composición:** {_format_compact(self.composition)}\n"
                    f"🗝️ **Bracket:** {bracket_text}\n\n"
                    "¿Al menos una persona del grupo tiene piedra?"
                ),
                view=GroupKeystoneChoiceView(self.composition, bracket),
            )
            return
        await _finish_group_queue(
            interaction,
            composition=self.composition,
            key_bracket=bracket,
            has_keystone=False,
            keystone_level=None,
        )


class GroupCompositionView(discord.ui.View):
    """
    View for the leader to select their group composition.
    
    Allows selecting:
    - Tanks: 0-1
    - Healers: 0-1
    - DPS: 0-3
    
    Total must be at least 1 and maximum 5.
    """
    
    def __init__(self):
        super().__init__(timeout=120)
        self.tank_count = 0
        self.healer_count = 0
        self.dps_count = 0
        
        # Select for Tanks (0-1)
        self.tank_select = discord.ui.Select(
            placeholder="🛡️ Tanques (0-1)...",
            options=[
                discord.SelectOption(label="0 Tanques", value="0", emoji="🛡️", default=True),
                discord.SelectOption(label="1 Tanque", value="1", emoji="🛡️"),
            ],
            custom_id="group_tank_select",
            row=0,
        )
        self.tank_select.callback = self.tank_selected
        self.add_item(self.tank_select)
        
        # Select for Healers (0-1)
        self.healer_select = discord.ui.Select(
            placeholder="💚 Sanadores (0-1)...",
            options=[
                discord.SelectOption(label="0 Sanadores", value="0", emoji="💚", default=True),
                discord.SelectOption(label="1 Sanador", value="1", emoji="💚"),
            ],
            custom_id="group_healer_select",
            row=1,
        )
        self.healer_select.callback = self.healer_selected
        self.add_item(self.healer_select)
        
        # Select for DPS (0-3)
        self.dps_select = discord.ui.Select(
            placeholder="⚔️ DPS (0-3)...",
            options=[
                discord.SelectOption(label="0 DPS", value="0", emoji="⚔️", default=True),
                discord.SelectOption(label="1 DPS", value="1", emoji="⚔️"),
                discord.SelectOption(label="2 DPS", value="2", emoji="⚔️"),
                discord.SelectOption(label="3 DPS", value="3", emoji="⚔️"),
            ],
            custom_id="group_dps_select",
            row=2,
        )
        self.dps_select.callback = self.dps_selected
        self.add_item(self.dps_select)
    
    async def tank_selected(self, interaction: discord.Interaction):
        """Update tank count."""
        self.tank_count = int(self.tank_select.values[0])
        await interaction.response.defer()
    
    async def healer_selected(self, interaction: discord.Interaction):
        """Update healer count."""
        self.healer_count = int(self.healer_select.values[0])
        await interaction.response.defer()
    
    async def dps_selected(self, interaction: discord.Interaction):
        """Update DPS count."""
        self.dps_count = int(self.dps_select.values[0])
        await interaction.response.defer()
    
    @discord.ui.button(
        label="Confirmar Composición",
        style=discord.ButtonStyle.success,
        emoji="✅",
        row=3,
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Confirm composition and proceed to bracket selection."""
        total = self.tank_count + self.healer_count + self.dps_count
        
        if total == 0:
            await interaction.response.send_message(
                "⚠️ Debes seleccionar al menos 1 jugador en tu grupo.",
                ephemeral=True,
            )
            return
        
        if total > 5:
            await interaction.response.send_message(
                "⚠️ Un grupo de M+ puede tener máximo 5 jugadores.",
                ephemeral=True,
            )
            return
        
        composition = {
            "tank": self.tank_count,
            "healer": self.healer_count,
            "dps": self.dps_count,
        }
        
        # Format for display
        parts = []
        if self.tank_count > 0:
            parts.append(f"🛡️ {self.tank_count} Tanque(s)")
        if self.healer_count > 0:
            parts.append(f"💚 {self.healer_count} Sanador(es)")
        if self.dps_count > 0:
            parts.append(f"⚔️ {self.dps_count} DPS")
        
        composition_text = " • ".join(parts)
        
        await interaction.response.edit_message(
            content=f"👥 **Composición del Grupo:** {composition_text}\n"
                    f"👤 **Total:** {total} jugadores\n\n"
                    f"Ahora, selecciona el **bracket** de llaves:",
            view=GroupKeyBracketSelectView(composition),
        )
