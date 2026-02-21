"""
Party views for the WoW Mythic+ LFG Bot.

This module contains views for party formation and confirmation.
"""

from typing import List

import discord

from models.queue import queue_manager
from models.stats import record_completed_key
from services.matchmaking import is_group_entry, calculate_common_range
from services.embeds import build_match_embed, build_confirmation_embed, format_entry_composition
from services.queue_status import refresh_lfg_setup_message


class ConfirmationView(discord.ui.View):
    """
    View for confirming group formation.
    
    Each player/leader must click 'Confirm' or 'Reject'.
    - For groups: only the leader can confirm/reject for the whole group
    - If everyone confirms: group formed, all removed from queue
    - If someone rejects: that entry (solo or group) is removed, others keep searching
    
    TESTING: Fake players (ID > 900000000000000000) auto-confirm immediately.
    """
    
    def __init__(self, guild_id: int, matched_user_ids: List[int], original_embed: discord.Embed):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.matched_user_ids = matched_user_ids
        self.original_embed = original_embed  # Keep original embed in case we need to revert
        self.confirmed_ids: set = set()  # IDs of users who confirmed
        
        # Auto-confirm fake players (for testing)
        for user_id in matched_user_ids:
            if user_id > 900000000000000000:  # Fake player
                self.confirmed_ids.add(user_id)
    
    @discord.ui.button(
        label="Confirmar",
        style=discord.ButtonStyle.success,
        emoji="✅",
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle Confirm button click."""
        user_id = interaction.user.id
        
        # Verify the clicker is part of the match (solo player or group leader)
        if user_id not in self.matched_user_ids:
            await interaction.response.send_message(
                "⚠️ Solo los jugadores o líderes de grupo pueden confirmar.",
                ephemeral=True,
            )
            return
        
        # Verify user is still in queue
        if not queue_manager.contains(self.guild_id, user_id):
            await interaction.response.send_message(
                "⚠️ Ya no estás en la cola.",
                ephemeral=True,
            )
            return
        
        # Check if already confirmed
        if user_id in self.confirmed_ids:
            entry = queue_manager.get(self.guild_id, user_id)
            if entry and is_group_entry(entry):
                await interaction.response.send_message(
                    "ℹ️ Ya has confirmado por tu grupo. Esperando a los demás...",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "ℹ️ Ya has confirmado. Esperando a los demás...",
                    ephemeral=True,
                )
            return
        
        # Add to confirmed
        self.confirmed_ids.add(user_id)
        
        # Check how many are still in queue and how many confirmed
        users_still_in_queue = [uid for uid in self.matched_user_ids if queue_manager.contains(self.guild_id, uid)]
        all_confirmed = all(uid in self.confirmed_ids for uid in users_still_in_queue)
        
        if all_confirmed and len(users_still_in_queue) >= 2:
            # Everyone confirmed! Group formed
            
            # Collect participant data before removing from queue
            participants = []
            removed_entries = []
            
            for uid in users_still_in_queue:
                entry = queue_manager.get(self.guild_id, uid)
                if entry:
                    participants.append({
                        "user_id": uid,
                        "username": entry["username"],
                        "role": entry.get("role"),
                        "composition": entry.get("composition"),
                        "key_min": entry["key_min"],
                        "key_max": entry["key_max"],
                    })
                    
                    if is_group_entry(entry):
                        removed_entries.append(f"<@{uid}> (grupo)")
                    else:
                        removed_entries.append(f"<@{uid}>")
                
                queue_manager.remove(self.guild_id, uid)

            await refresh_lfg_setup_message(interaction.client, self.guild_id, interaction.channel)
            
            # Calculate the key level (use the common range minimum)
            common_range = calculate_common_range(participants)
            key_level = common_range[0]  # Use minimum of common range
            
            # Record the completed key in the database (with guild_id)
            try:
                record_completed_key(key_level, participants, guild_id=self.guild_id)
            except Exception as e:
                print(f"⚠️ Error recording completed key: {e}")
            
            await interaction.response.send_message(
                f"🎉 **¡Grupo formado!**\n\n"
                f"El grupo se ha formado por {', '.join(removed_entries)} "
                f"y serán eliminados de la cola.\n\n"
                f"📊 *Llave +{key_level} registrada en las estadísticas.*\n\n"
                f"¡Buena suerte en la mazmorra! 🗝️",
                ephemeral=False,
            )
            
            # Delete confirmation message
            try:
                await interaction.message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
        else:
            # Update embed to show new status
            embed = build_confirmation_embed(self.guild_id, self.matched_user_ids, self.confirmed_ids)
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(
        label="Rechazar",
        style=discord.ButtonStyle.danger,
        emoji="❌",
    )
    async def reject_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle Reject button click."""
        user_id = interaction.user.id
        
        # Verify the clicker is part of the match (solo player or group leader)
        if user_id not in self.matched_user_ids:
            await interaction.response.send_message(
                "⚠️ Solo los jugadores o líderes de grupo pueden rechazar.",
                ephemeral=True,
            )
            return
        
        # Check if it was a group
        entry = queue_manager.get(self.guild_id, user_id)
        was_group = entry and is_group_entry(entry)
        
        # Remove user/group from queue
        was_in_queue = queue_manager.remove(self.guild_id, user_id)
        if was_in_queue:
            await refresh_lfg_setup_message(interaction.client, self.guild_id, interaction.channel)
        
        if was_in_queue:
            if was_group:
                await interaction.response.send_message(
                    "✅ Has rechazado y tu grupo ha salido de la cola. ¡Hasta la próxima!",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "✅ Has rechazado y salido de la cola. ¡Hasta la próxima!",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                "ℹ️ Ya no estabas en la cola.",
                ephemeral=True,
            )
        
        # Check if enough players remain
        users_still_in_queue = [uid for uid in self.matched_user_ids if queue_manager.contains(self.guild_id, uid)]
        
        # Notify via DM those who had confirmed (without revealing who rejected)
        for uid in self.confirmed_ids:
            if uid != user_id:  # Don't send to the one who rejected
                try:
                    user = await interaction.client.fetch_user(uid)
                    await user.send(
                        "😔 **Alguien ha rechazado la confirmación de grupo.**\n\n"
                        "Sigues en la cola esperando más jugadores. "
                        "¡No te preocupes, pronto encontrarás otro grupo!"
                    )
                except (discord.errors.Forbidden, discord.errors.HTTPException):
                    # User has DMs disabled or there was an error
                    pass
        
        if len(users_still_in_queue) < 2:
            # Not enough players remain, clear their match_message_id so they can find new matches
            for uid in users_still_in_queue:
                queue_manager.clear_match_message(self.guild_id, uid)
            
            # Delete message
            try:
                await interaction.message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
        else:
            # Delete current confirmation message
            try:
                await interaction.message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
            
            self.confirmed_ids.discard(user_id)
            
            # Rebuild original embed with remaining users
            users_data = [{"user_id": uid, **queue_manager.get(self.guild_id, uid)} for uid in users_still_in_queue]
            new_embed = build_match_embed(users_data)
            
            # Create new view
            new_view = PartyCompleteView(self.guild_id, users_still_in_queue)
            
            # Mention everyone remaining (new message = notification)
            mentions = " ".join(f"<@{uid}>" for uid in users_still_in_queue)
            
            channel = interaction.channel
            if channel:
                match_message = await channel.send(
                    content=mentions,  # Just ping, don't say who rejected
                    embed=new_embed,
                    view=new_view,
                )
                
                # Store the message reference for remaining users
                for uid in users_still_in_queue:
                    queue_manager.set_match_message(self.guild_id, uid, match_message.id, channel.id)


class PartyCompleteView(discord.ui.View):
    """
    View containing 'Party Complete' and 'Leave Queue' buttons.
    
    Attached to match notification messages.
    - 'Party Complete': Starts the confirmation process
    - 'Leave Queue': Removes the clicking user/leader (and their group if applicable)
    
    For groups: only the leader can interact with the buttons.
    
    Note: This view is not fully persistent after bot restart
    because it needs to know which users were in the match.
    Since the queue is also in memory, this is acceptable.
    """
    
    def __init__(self, guild_id: int, matched_user_ids: List[int]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.matched_user_ids = matched_user_ids
    
    @discord.ui.button(
        label="Grupo Completo",
        style=discord.ButtonStyle.success,
        emoji="✅",
    )
    async def party_complete_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Handle Party Complete button click.
        
        Starts the confirmation process where everyone (players/leaders) must accept.
        """
        user_id = interaction.user.id
        
        # Verify the clicker is part of the match (solo player or group leader)
        if user_id not in self.matched_user_ids:
            await interaction.response.send_message(
                "⚠️ Solo los jugadores o líderes de grupo pueden usar estos botones.",
                ephemeral=True,
            )
            return
        
        # Verify user is still in queue
        if not queue_manager.contains(self.guild_id, user_id):
            await interaction.response.send_message(
                "⚠️ Ya no estás en la cola.",
                ephemeral=True,
            )
            return
        
        # Check how many are still in queue
        users_still_in_queue = [uid for uid in self.matched_user_ids if queue_manager.contains(self.guild_id, uid)]
        
        if len(users_still_in_queue) < 2:
            await interaction.response.send_message(
                "⚠️ No hay suficientes jugadores en cola para formar grupo.",
                ephemeral=True,
            )
            return
        
        # Save current embed
        original_embed = interaction.message.embeds[0] if interaction.message.embeds else None
        
        # Create confirmation view
        confirmation_view = ConfirmationView(self.guild_id, users_still_in_queue, original_embed)
        
        # User who initiated is automatically confirming
        confirmation_view.confirmed_ids.add(user_id)
        
        # Check if all players are now confirmed (happens when only fake players remain)
        all_confirmed = all(uid in confirmation_view.confirmed_ids for uid in users_still_in_queue)
        
        if all_confirmed and len(users_still_in_queue) >= 2:
            # Everyone is confirmed (all fake players + clicking user)! Auto-complete group
            # Defer first
            await interaction.response.defer()
            
            # Collect participant data before removing from queue
            participants = []
            for uid in users_still_in_queue:
                entry = queue_manager.get(self.guild_id, uid)
                if entry:
                    participants.append({
                        "user_id": uid,
                        "username": entry["username"],
                        "role": entry.get("role"),
                        "composition": entry.get("composition"),
                        "key_min": entry["key_min"],
                        "key_max": entry["key_max"],
                    })
                queue_manager.remove(self.guild_id, uid)

            await refresh_lfg_setup_message(interaction.client, self.guild_id, interaction.channel)
            
            # Calculate the key level
            from services.matchmaking import calculate_common_range
            common_range = calculate_common_range(participants)
            key_level = common_range[0]
            
            # Record the completed key
            from models.stats import record_completed_key
            try:
                record_completed_key(key_level, participants, guild_id=self.guild_id)
            except Exception as e:
                print(f"⚠️ Error recording completed key: {e}")
            
            # Delete previous match message
            try:
                await interaction.message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
            
            # Send completion message
            channel = interaction.channel
            if channel:
                removed_entries = []
                for uid in users_still_in_queue:
                    if uid > 900000000000000000:  # Fake player
                        entry_data = next((p for p in participants if p["user_id"] == uid), None)
                        if entry_data:
                            removed_entries.append(f"`{entry_data['username']}`")
                    else:
                        removed_entries.append(f"<@{uid}>")
                
                await channel.send(
                    f"🎉 **¡Grupo formado automáticamente!**\n\n"
                    f"El grupo se ha formado con {', '.join(removed_entries)} "
                    f"y han sido eliminados de la cola.\n\n"
                    f"📊 *Llave +{key_level} registrada en las estadísticas.*\n\n"
                    f"💡 *Todos los jugadores falsos confirmaron automáticamente.*\n\n"
                    f"¡Buena suerte en la mazmorra! 🗝️",
                )
            return
        
        # Not all confirmed yet, create confirmation embed
        embed = build_confirmation_embed(self.guild_id, users_still_in_queue, confirmation_view.confirmed_ids)
        
        # Mention EVERYONE so they get notified (new message = notification)
        mentions = " ".join(f"<@{uid}>" for uid in users_still_in_queue)
        
        # Defer to avoid interaction timeout
        await interaction.response.defer()
        
        # Delete previous match message
        try:
            await interaction.message.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden):
            pass
        
        # Send NEW confirmation message (this DOES notify everyone)
        channel = interaction.channel
        if channel:
            await channel.send(
                content=f"🔔 {mentions} — ¡Confirmen para formar el grupo!",
                embed=embed,
                view=confirmation_view,
            )
    
    @discord.ui.button(
        label="Salir de Cola",
        style=discord.ButtonStyle.danger,
        emoji="🚪",
    )
    async def leave_queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Handle Leave Queue button click.
        
        Removes the clicking user/leader from queue (including their group).
        Useful when someone can't play anymore but others can.
        If no one from the match remains in queue, deletes the message.
        """
        user_id = interaction.user.id
        
        # Verify the clicker is part of the match (solo player or group leader)
        if user_id not in self.matched_user_ids:
            await interaction.response.send_message(
                "⚠️ Solo los jugadores o líderes de grupo pueden usar estos botones.",
                ephemeral=True,
            )
            return
        
        # Check if it was a group
        entry = queue_manager.get(self.guild_id, user_id)
        was_group = entry and is_group_entry(entry)
        
        was_in_queue = queue_manager.remove(self.guild_id, user_id)
        if was_in_queue:
            await refresh_lfg_setup_message(interaction.client, self.guild_id, interaction.channel)
        
        if was_in_queue:
            if was_group:
                await interaction.response.send_message(
                    "✅ Tu grupo ha salido de la cola. ¡Hasta la próxima!",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "✅ Has salido de la cola. ¡Hasta la próxima!",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                "ℹ️ Ya no estabas en la cola.",
                ephemeral=True,
            )
        
        # Check if anyone from original match is still in queue
        users_still_in_queue = [uid for uid in self.matched_user_ids if queue_manager.contains(self.guild_id, uid)]
        
        # If less than 2 remain, clear their match_message_id and delete the message
        if len(users_still_in_queue) < 2:
            # Clear match_message_id for remaining players so they can find new matches
            for uid in users_still_in_queue:
                queue_manager.clear_match_message(self.guild_id, uid)
            
            # Delete the notification message
            try:
                await interaction.message.delete()
            except discord.errors.NotFound:
                pass
            except discord.errors.Forbidden:
                pass
