"""Persistent participation panel buttons."""

from __future__ import annotations

import discord

from models import participation as participation_repo
from services.participation_panel import leaderboard_text, message_chunks, rules_text, user_progress_text


class ParticipationPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    def _settings(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return None
        settings = participation_repo.get_participation_settings(interaction.guild.id)
        if settings is None or not settings.enabled or not settings.configured:
            return None
        return settings

    @discord.ui.button(label="My Progress", style=discord.ButtonStyle.primary, custom_id="participation_panel:my_progress")
    async def my_progress(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        settings = self._settings(interaction)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        await interaction.response.send_message(user_progress_text(settings, interaction.user.id), ephemeral=True)

    @discord.ui.button(label="Rules", style=discord.ButtonStyle.secondary, custom_id="participation_panel:rules")
    async def rules(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        settings = self._settings(interaction)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        await interaction.response.send_message(rules_text(settings), ephemeral=True)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.secondary, custom_id="participation_panel:leaderboard")
    async def leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        settings = self._settings(interaction)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        chunks = message_chunks(leaderboard_text(settings))
        await interaction.response.send_message(chunks[0], ephemeral=True)
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)
