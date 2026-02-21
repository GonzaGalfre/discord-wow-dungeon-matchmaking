"""
Group selection views for the WoW Mythic+ LFG Bot.

This module contains views for group queue composition and key range selection.
"""

import asyncio
from typing import Dict, TYPE_CHECKING

import discord

from config.settings import MIN_KEY_LEVEL, MAX_KEY_LEVEL
from models.queue import queue_manager
from models.guild_settings import get_match_channel_id
from services.matchmaking import get_users_with_overlap
from services.embeds import build_match_embed
from event_logger import log_event
from services.queue_status import refresh_lfg_setup_message
from views.role_selection import delete_old_match_messages

# Avoid circular imports
if TYPE_CHECKING:
    from views.party import PartyCompleteView


class GroupKeyRangeMaxSelectView(discord.ui.View):
    """
    View for selecting the MAXIMUM key level for a GROUP.
    
    Similar to KeyRangeMaxSelectView but uses composition instead of role.
    """
    
    def __init__(self, composition: Dict[str, int], key_min: int):
        super().__init__(timeout=60)
        self.composition = composition
        self.key_min = key_min
        
        options = [
            discord.SelectOption(
                label=f"Nivel {i}",
                value=str(i),
                description=f"Llaves hasta +{i}",
                emoji="🔼" if i == MAX_KEY_LEVEL else "🗝️",
            )
            for i in range(key_min, MAX_KEY_LEVEL + 1)
        ]
        
        self.key_select = discord.ui.Select(
            placeholder=f"Selecciona nivel máximo ({key_min}-{MAX_KEY_LEVEL})...",
            options=options,
            custom_id="group_key_max_select",
        )
        self.key_select.callback = self.key_max_selected
        self.add_item(self.key_select)
    
    def _format_composition(self) -> str:
        """Format the composition for display."""
        parts = []
        if self.composition["tank"] > 0:
            parts.append(f"🛡️ {self.composition['tank']} Tanque(s)")
        if self.composition["healer"] > 0:
            parts.append(f"💚 {self.composition['healer']} Sanador(es)")
        if self.composition["dps"] > 0:
            parts.append(f"⚔️ {self.composition['dps']} DPS")
        return " • ".join(parts)
    
    async def key_max_selected(self, interaction: discord.Interaction):
        """Handle maximum key level selection for groups."""
        # Import here to avoid circular import
        from views.party import PartyCompleteView
        
        key_max = int(self.key_select.values[0])
        user_id = interaction.user.id
        username = interaction.user.display_name
        guild_id = interaction.guild_id
        
        # Add the group to the queue
        queue_manager.add(guild_id, user_id, username, self.key_min, key_max, composition=self.composition)
        await refresh_lfg_setup_message(interaction.client, guild_id, interaction.channel)
        
        # Search for matches
        matches = get_users_with_overlap(guild_id, self.key_min, key_max, user_id)
        
        total_players = sum(self.composition.values())
        composition_text = self._format_composition()
        
        if len(matches) == 1:
            # Only this group - waiting
            await interaction.response.edit_message(
                content=f"✅ **¡Tu grupo está en la cola!**\n\n"
                f"👥 **Composición:** {composition_text}\n"
                f"👤 **Jugadores:** {total_players}\n"
                f"🗝️ **Rango de Llaves:** {self.key_min}-{key_max}\n\n"
                f"¡Serás notificado cuando otros busquen llaves compatibles!\n\n"
                f"*Este mensaje se cerrará en 5 segundos...*",
                view=None,
            )
            
            await asyncio.sleep(5)
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                pass
        else:
            # Match found! Could be a new match or joining existing match
            # Check if joining an existing match (any player already has a match_message_id)
            joining_existing = any(
                queue_manager.get(guild_id, u["user_id"]).get("match_message_id") is not None 
                for u in matches if u["user_id"] != user_id
            )
            
            if joining_existing:
                message_type = "¡Tu grupo se ha unido a un match existente!"
            else:
                message_type = f"¡Nuevo match formado con {len(matches)} jugadores/grupos!"
            
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
                log_event(
                    "match_message_created",
                    guild_id=guild_id,
                    channel_id=match_channel.id,
                    message_id=match_message.id,
                    matched_user_ids=matched_user_ids,
                    triggered_by_user_id=user_id,
                    source="group_queue",
                )
                
                # Store the message reference for ALL matched users (including new group)
                for uid in matched_user_ids:
                    queue_manager.set_match_message(guild_id, uid, match_message.id, match_channel.id)
            
            await asyncio.sleep(5)
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                pass


class GroupKeyRangeMinSelectView(discord.ui.View):
    """
    View for selecting the MINIMUM key level for a GROUP.
    
    This appears AFTER the leader selects the group composition.
    """
    
    def __init__(self, composition: Dict[str, int]):
        super().__init__(timeout=60)
        self.composition = composition
        
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
            custom_id="group_key_min_select",
        )
        self.key_select.callback = self.key_min_selected
        self.add_item(self.key_select)
    
    def _format_composition(self) -> str:
        """Format the composition for display."""
        parts = []
        if self.composition["tank"] > 0:
            parts.append(f"🛡️ {self.composition['tank']}")
        if self.composition["healer"] > 0:
            parts.append(f"💚 {self.composition['healer']}")
        if self.composition["dps"] > 0:
            parts.append(f"⚔️ {self.composition['dps']}")
        return " • ".join(parts)
    
    async def key_min_selected(self, interaction: discord.Interaction):
        """Handle minimum level selection for groups."""
        key_min = int(self.key_select.values[0])
        
        await interaction.response.edit_message(
            content=f"👥 **Composición:** {self._format_composition()}\n"
                    f"🔽 **Mínimo:** Nivel {key_min}\n\n"
                    f"Ahora, selecciona tu **nivel máximo** de llave:",
            view=GroupKeyRangeMaxSelectView(self.composition, key_min),
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
        """Confirm composition and proceed to key range selection."""
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
                    f"Ahora, selecciona el **nivel mínimo** de llave:",
            view=GroupKeyRangeMinSelectView(composition),
        )
