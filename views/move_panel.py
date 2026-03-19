"""
Move Panel views for the WoW Mythic+ LFG Bot.

MovePanelView -- persistent message with two inline ChannelSelect dropdowns
(Origen / Destino) and a Move button. Everything lives in the panel message
itself -- no ephemeral popups required.

State (which channels each user has selected) is stored in a module-level
dict keyed by user_id. In-memory only; users re-select after a bot restart.
"""

from __future__ import annotations

import discord

from services.voice_move import move_all_members, build_move_embed, build_error_embed

# user_id -> {"from": int | None, "to": int | None}  (channel IDs)
_state: dict[int, dict] = {}


# =============================================================================
# Embed builder
# =============================================================================

def build_panel_embed() -> discord.Embed:
    """Embed displayed in the persistent move panel message."""
    return discord.Embed(
        title="Mover Miembros",
        description=(
            "1. Selecciona el canal de **Origen**.\n"
            "2. Selecciona el canal de **Destino**.\n"
            "3. Pulsa **Mover** para mover a todos los miembros."
        ),
        color=0x5865f2,
    )


# =============================================================================
# ChannelSelect components (subclass approach for compatibility)
# =============================================================================

class _OriginSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="1. Selecciona el canal de origen...",
            channel_types=[discord.ChannelType.voice],
            custom_id="move_panel:select:from",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        _state.setdefault(interaction.user.id, {})["from"] = self.values[0].id
        await interaction.response.defer()


class _DestinationSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="2. Selecciona el canal de destino...",
            channel_types=[discord.ChannelType.voice],
            custom_id="move_panel:select:to",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        _state.setdefault(interaction.user.id, {})["to"] = self.values[0].id
        await interaction.response.defer()


# =============================================================================
# Persistent panel view
# =============================================================================

class MovePanelView(discord.ui.View):
    """
    Persistent view attached to the move panel message.

    Contains two ChannelSelect dropdowns and a Move button,
    all inline in the message -- no ephemeral steps required.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(_OriginSelect())
        self.add_item(_DestinationSelect())

    @discord.ui.button(
        label="Mover",
        style=discord.ButtonStyle.primary,
        custom_id="move_panel:execute",
        emoji="🚀",
        row=2,
    )
    async def move_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.user.guild_permissions.move_members:
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Necesitas el permiso **Mover Miembros** para usar este panel."
                ),
                ephemeral=True,
            )
            return

        entry = _state.get(interaction.user.id, {})
        from_id: int | None = entry.get("from")
        to_id: int | None = entry.get("to")

        if not from_id or not to_id:
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Selecciona primero el canal de **Origen** y el de **Destino**."
                ),
                ephemeral=True,
            )
            return

        source = interaction.guild.get_channel(from_id)
        destination = interaction.guild.get_channel(to_id)

        if not isinstance(source, discord.VoiceChannel) or not isinstance(destination, discord.VoiceChannel):
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Uno de los canales seleccionados ya no existe. Vuelve a seleccionarlos."
                ),
                ephemeral=True,
            )
            _state.pop(interaction.user.id, None)
            return

        if len(source.members) == 0:
            await interaction.response.send_message(
                embed=build_error_embed(f"El canal {source.mention} está vacío."),
                ephemeral=True,
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        try:
            nb_moved = await move_all_members(source, destination)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=build_error_embed(
                    "El bot no tiene permiso para mover miembros.\n"
                    "Un administrador debe concederle el permiso **Mover Miembros**."
                ),
                ephemeral=True,
            )
            return
        finally:
            _state.pop(interaction.user.id, None)

        await interaction.followup.send(
            embed=build_move_embed(nb_moved, source, destination),
            ephemeral=True,
        )
