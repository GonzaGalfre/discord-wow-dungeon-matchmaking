"""
Role selection views for the WoW Mythic+ LFG Bot.

This module contains views for solo queue role and key range selection.
"""

import asyncio
from typing import List, TYPE_CHECKING

import discord

from config.settings import ROLES, MIN_KEY_LEVEL, MAX_KEY_LEVEL
from models.queue import queue_manager
from models.guild_settings import get_match_channel_id
from services.matchmaking import get_users_with_overlap
from services.embeds import build_match_embed

# Avoid circular imports
if TYPE_CHECKING:
    from views.party import PartyCompleteView


async def delete_old_match_messages(client: discord.Client, guild_id: int, user_ids: List[int]) -> None:
    """
    Delete existing match messages for the given users in a specific guild.
    
    When a new match forms that includes users from a previous match,
    we need to delete the old match message to avoid confusion.
    
    Args:
        client: Discord client to fetch channels
        guild_id: Discord guild ID
        user_ids: List of user IDs to check for existing match messages
    """
    # Collect unique messages to delete (avoid deleting same message multiple times)
    messages_to_delete = {}  # {(channel_id, message_id): True}
    
    for uid in user_ids:
        match_info = queue_manager.get_match_message(guild_id, uid)
        if match_info:
            message_id, channel_id = match_info
            messages_to_delete[(channel_id, message_id)] = True
            queue_manager.clear_match_message(guild_id, uid)
    
    # Delete the messages
    for (channel_id, message_id) in messages_to_delete.keys():
        try:
            channel = client.get_channel(channel_id)
            if channel:
                message = await channel.fetch_message(message_id)
                await message.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden):
            # Message already deleted or no permission
            pass
        except Exception as e:
            print(f"⚠️ Error deleting old match message: {e}")


class KeyRangeMaxSelectView(discord.ui.View):
    """
    View for selecting the MAXIMUM key level.
    
    This appears AFTER the user selects their minimum level.
    Only shows options >= the selected minimum.
    """
    
    def __init__(self, role: str, key_min: int):
        super().__init__(timeout=60)
        self.role = role
        self.key_min = key_min
        
        # Create select dynamically to show only valid options
        options = [
            discord.SelectOption(
                label=f"Nivel {i}",
                value=str(i),
                description=f"Llaves hasta +{i}",
                emoji="🔼" if i == MAX_KEY_LEVEL else "🗝️",
            )
            for i in range(key_min, MAX_KEY_LEVEL + 1)
        ]
        
        # Create and add the select
        self.key_select = discord.ui.Select(
            placeholder=f"Selecciona nivel máximo ({key_min}-{MAX_KEY_LEVEL})...",
            options=options,
            custom_id="key_max_select",
        )
        self.key_select.callback = self.key_max_selected
        self.add_item(self.key_select)
    
    async def key_max_selected(self, interaction: discord.Interaction):
        """
        Handle maximum key level selection.
        
        This is where the magic happens:
        1. Add user to queue
        2. Search for matches
        3. Confirm waiting OR send match notification
        """
        # Import here to avoid circular import
        from views.party import PartyCompleteView
        
        key_max = int(self.key_select.values[0])
        user_id = interaction.user.id
        username = interaction.user.display_name
        guild_id = interaction.guild_id
        
        # Add user to queue (or update if already there)
        queue_manager.add(guild_id, user_id, username, self.key_min, key_max, role=self.role)
        
        # Search for overlapping ranges AND compatible roles
        matches = get_users_with_overlap(guild_id, self.key_min, key_max, user_id)
        
        if len(matches) == 1:
            # Only this user has compatible range - waiting for others
            role_info = ROLES[self.role]
            await interaction.response.edit_message(
                content=f"✅ **¡Estás en la cola!**\n\n"
                f"{role_info['emoji']} **Rol:** {role_info['name']}\n"
                f"🗝️ **Rango de Llaves:** {self.key_min}-{key_max}\n\n"
                f"¡Serás notificado cuando otros busquen llaves compatibles!\n\n"
                f"*Este mensaje se cerrará en 5 segundos...*",
                view=None,  # Remove buttons/selects
            )
            
            # Wait and delete the ephemeral message
            await asyncio.sleep(5)
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                pass  # Message already deleted
        else:
            # Multiple people found! Could be a new match or joining existing match
            # Check if joining an existing match (any player already has a match_message_id)
            joining_existing = any(
                queue_manager.get(guild_id, u["user_id"]).get("match_message_id") is not None 
                for u in matches if u["user_id"] != user_id
            )
            
            if joining_existing:
                message_type = "¡Te has unido a un grupo existente!"
            else:
                message_type = f"¡Nuevo grupo formado con {len(matches)} jugadores!"
            
            await interaction.response.edit_message(
                content=f"🎉 **{message_type}**\n"
                f"Se ha enviado una notificación al canal de emparejamientos.\n\n"
                f"*Este mensaje se cerrará en 5 segundos...*",
                view=None,
            )
            
            # Get the match channel from guild settings
            match_channel_id = get_match_channel_id(guild_id)
            match_channel = None
            
            if match_channel_id:
                match_channel = interaction.client.get_channel(match_channel_id)
            
            # If not configured or not found, use current channel as fallback
            if not match_channel:
                match_channel = interaction.channel
            
            if match_channel:
                # Extract user IDs for the view
                matched_user_ids = [u["user_id"] for u in matches]
                
                # Delete any existing match messages for these users
                # This handles both: updating existing matches and removing old separate matches
                await delete_old_match_messages(interaction.client, guild_id, matched_user_ids)
                
                embed = build_match_embed(matches)
                mentions = " ".join(f"<@{u['user_id']}>" for u in matches)
                
                # Send new/updated match message
                match_message = await match_channel.send(
                    content=mentions,
                    embed=embed,
                    view=PartyCompleteView(guild_id, matched_user_ids),
                )
                
                # Store the message reference for ALL matched users (including new one)
                for uid in matched_user_ids:
                    queue_manager.set_match_message(guild_id, uid, match_message.id, match_channel.id)
            
            # Wait and delete the ephemeral message
            await asyncio.sleep(5)
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                pass


class KeyRangeMinSelectView(discord.ui.View):
    """
    View for selecting the MINIMUM key level.
    
    This appears AFTER the user selects their role.
    """
    
    def __init__(self, role: str):
        super().__init__(timeout=60)
        self.role = role
        
        # Create options for all available levels
        options = [
            discord.SelectOption(
                label=f"Nivel {i}",
                value=str(i),
                description=f"Llaves desde +{i}",
                emoji="🔽" if i == MIN_KEY_LEVEL else "🗝️",
            )
            for i in range(MIN_KEY_LEVEL, MAX_KEY_LEVEL + 1)
        ]
        
        self.key_select = discord.ui.Select(
            placeholder=f"Selecciona nivel mínimo ({MIN_KEY_LEVEL}-{MAX_KEY_LEVEL})...",
            options=options,
            custom_id="key_min_select",
        )
        self.key_select.callback = self.key_min_selected
        self.add_item(self.key_select)
    
    async def key_min_selected(self, interaction: discord.Interaction):
        """
        Handle minimum level selection.
        
        Shows the maximum level selector after choosing minimum.
        """
        key_min = int(self.key_select.values[0])
        role_info = ROLES[self.role]
        
        await interaction.response.edit_message(
            content=f"{role_info['emoji']} **{role_info['name']}** seleccionado.\n"
                    f"🔽 **Mínimo:** Nivel {key_min}\n\n"
                    f"Ahora, selecciona tu **nivel máximo** de llave:",
            view=KeyRangeMaxSelectView(self.role, key_min),
        )


class RoleSelectView(discord.ui.View):
    """
    View for selecting user role (Tank/Healer/DPS).
    
    This is the first step after clicking "Join Queue" for solo.
    Uses buttons for quick and clear selection.
    """
    
    def __init__(self):
        super().__init__(timeout=60)
    
    async def handle_role_selection(
        self, interaction: discord.Interaction, role: str
    ):
        """
        Common handler for all role buttons.
        
        Shows the key range selection after choosing a role.
        """
        role_info = ROLES[role]
        
        await interaction.response.edit_message(
            content=f"{role_info['emoji']} **{role_info['name']}** seleccionado.\n\n"
                    f"Ahora, selecciona tu **nivel mínimo** de llave:",
            view=KeyRangeMinSelectView(role),
        )
    
    @discord.ui.button(
        label="Tanque",
        style=discord.ButtonStyle.primary,
        emoji="🛡️",
    )
    async def tank_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle Tank selection."""
        await self.handle_role_selection(interaction, "tank")
    
    @discord.ui.button(
        label="Sanador",
        style=discord.ButtonStyle.success,
        emoji="💚",
    )
    async def healer_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle Healer selection."""
        await self.handle_role_selection(interaction, "healer")
    
    @discord.ui.button(
        label="DPS",
        style=discord.ButtonStyle.danger,
        emoji="⚔️",
    )
    async def dps_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle DPS selection."""
        await self.handle_role_selection(interaction, "dps")
