"""
Voice Cog for the WoW Mythic+ LFG Bot.

Provides voice channel management commands.
Business logic lives in services/voice_move.py so the move panel UI
view can reuse it without importing from a cog.
"""

import discord
from discord import app_commands
from discord.ext import commands

from services.voice_move import move_all_members, build_move_embed, build_error_embed
from models.guild_settings import get_move_panel_ids, update_move_panel_ids


class VoiceCog(commands.Cog):
    """
    Cog containing voice channel management commands.

    Commands:
    - /move: Move all members from one voice channel to another.
    - /setup_move: Post the persistent move panel in this channel (admin only).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------------------
    # /move
    # -------------------------------------------------------------------------

    @app_commands.command(
        name="move",
        description="Move all members from one voice channel to another.",
    )
    @app_commands.default_permissions(move_members=True)
    @app_commands.describe(
        destination="The voice channel to move members to.",
        source="The channel to move members from (defaults to your current channel).",
    )
    async def move_command(
        self,
        interaction: discord.Interaction,
        destination: discord.VoiceChannel,
        source: discord.VoiceChannel | None = None,
    ) -> None:
        member = interaction.guild.get_member(interaction.user.id)

        if source is None:
            if member is None or member.voice is None or member.voice.channel is None:
                await interaction.response.send_message(
                    embed=build_error_embed(
                        "No especificaste un canal de origen y no estás conectado a ninguno."
                    ),
                    ephemeral=True,
                )
                return
            if not isinstance(member.voice.channel, discord.VoiceChannel):
                await interaction.response.send_message(
                    embed=build_error_embed(
                        "No especificaste un canal de origen y no estás en un canal de voz válido."
                    ),
                    ephemeral=True,
                )
                return
            source = member.voice.channel

        if len(source.members) == 0:
            await interaction.response.send_message(
                embed=build_error_embed(f"El canal {source.mention} está vacío."),
                ephemeral=True,
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return  # Stale/expired interaction token

        try:
            nb_moved = await move_all_members(source, destination)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=build_error_embed(
                    "El bot no tiene permiso para mover miembros en este servidor.\n"
                    "Un administrador debe concederle el permiso **Mover Miembros**."
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=build_move_embed(nb_moved, source, destination),
            ephemeral=True,
        )

    # -------------------------------------------------------------------------
    # /setup_move
    # -------------------------------------------------------------------------

    @app_commands.command(
        name="setup_move",
        description="Publica el panel de mover miembros en este canal.",
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_move_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id

        # Delete the previous panel message for this guild if it still exists
        existing = get_move_panel_ids(guild_id)
        if existing:
            old_channel_id, old_message_id = existing
            try:
                old_channel = interaction.guild.get_channel(old_channel_id)
                if old_channel:
                    old_msg = await old_channel.fetch_message(old_message_id)
                    await old_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass  # Already gone or no permission -- continue anyway

        # Import here to avoid a circular import at module load time
        from views.move_panel import MovePanelView, build_panel_embed

        panel_msg = await interaction.channel.send(
            embed=build_panel_embed(),
            view=MovePanelView(),
        )

        update_move_panel_ids(guild_id, interaction.channel.id, panel_msg.id)

        await interaction.followup.send(
            embed=discord.Embed(
                title="Panel publicado",
                description=f"El panel de mover miembros ha sido publicado en {interaction.channel.mention}.",
                color=0x55efc4,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceCog(bot))
