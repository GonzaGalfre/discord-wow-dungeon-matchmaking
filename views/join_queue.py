"""
Join queue views for the WoW Mythic+ LFG Bot.

This module contains the entry point views for joining the LFG queue.
"""

import discord

from views.role_selection import RoleSelectView
from views.group_selection import GroupCompositionView


class QueueTypeSelectView(discord.ui.View):
    """
    View for selecting queue type: Solo or Group.
    
    This is the first step after clicking "Join Queue".
    """
    
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.button(
        label="Solo",
        style=discord.ButtonStyle.primary,
        emoji="👤",
    )
    async def solo_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Start the individual queue flow."""
        await interaction.response.edit_message(
            content="**👤 Cola Individual**\n\n"
                    "Selecciona tu rol:",
            view=RoleSelectView(),
        )
    
    @discord.ui.button(
        label="Grupo",
        style=discord.ButtonStyle.success,
        emoji="👥",
    )
    async def group_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Start the group queue flow."""
        await interaction.response.edit_message(
            content="**👥 Cola de Grupo**\n\n"
                    "Como líder, selecciona la composición de tu grupo.\n"
                    "Elige cuántos jugadores de cada rol hay en tu grupo:",
            view=GroupCompositionView(),
        )


class JoinQueueView(discord.ui.View):
    """
    The main persistent view with the "Join Queue" button.
    
    This is the entry point for the entire LFG system.
    It stays in the LFG channel and survives bot restarts.
    """
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Unirse a Cola",
        style=discord.ButtonStyle.success,
        emoji="🎮",
        custom_id="lfg:join_queue",
    )
    async def join_queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Handle the Join Queue button click.
        
        Starts the flow by asking if it's solo or group.
        The response is ephemeral (only the clicking user sees it).
        """
        # Import here to avoid circular dependency
        from models.queue import queue_manager
        
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        
        # Check if user is already in an active match
        entry = queue_manager.get(guild_id, user_id)
        if entry and entry.get("match_message_id") is not None:
            await interaction.response.send_message(
                "⚠️ **Ya estás en un grupo activo.**\n\n"
                "Si quieres salir y unirte con diferentes preferencias:\n"
                "• Haz clic en **'Salir de Cola'** en tu mensaje de emparejamiento, o\n"
                "• Usa el comando `/salir`",
                ephemeral=True,
            )
            return
        
        await interaction.response.send_message(
            "**🎮 ¿Buscando grupo para Mythic+?**\n\n"
            "¿Cómo quieres unirte a la cola?",
            view=QueueTypeSelectView(),
            ephemeral=True,
        )

