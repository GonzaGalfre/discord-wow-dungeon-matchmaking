"""
LFG Cog for the WoW Mythic+ LFG Bot.

This module contains all slash commands for the LFG system.
"""

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from models.queue import queue_manager
from models.guild_settings import (
    save_guild_settings,
    get_guild_settings,
    update_guild_channel,
    update_lfg_message_id,
)
from services.embeds import (
    format_entry_composition,
    format_entry_key_preference,
    build_lfg_setup_embed,
)
from services.queue_exit import leave_queue_entry
from views.join_queue import JoinQueueView


class LFGCog(commands.Cog):
    """
    Cog containing all LFG-related slash commands.
    
    Commands:
    - /setup: Post the LFG button (admin only)
    - /config: Configure guild channels (admin only)
    - /cola: View current queue
    - /salir: Leave the queue
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="setup",
        description="Publica el botón de LFG en este canal"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_command(self, interaction: discord.Interaction):
        """
        Slash command to setup the LFG system in a channel.
        
        Posts the persistent "Join Queue" button and saves the guild configuration.
        Only needs to be run once per channel.
        
        Usage: /setup
        """
        guild_id = interaction.guild_id
        guild_name = interaction.guild.name
        channel_id = interaction.channel_id
        
        # Save guild settings (use current channel for both LFG and matches by default)
        save_guild_settings(
            guild_id=guild_id,
            guild_name=guild_name,
            lfg_channel_id=channel_id,
            match_channel_id=channel_id,  # Use same channel as default
        )
        
        setup_message = await interaction.channel.send(
            embed=build_lfg_setup_embed(guild_id),
            view=JoinQueueView(),
        )
        update_lfg_message_id(guild_id, setup_message.id)
        
        await interaction.response.send_message(
            "✅ ¡El sistema LFG ha sido configurado en este canal!\n\n"
            "💡 *Tip: Usa `/config` para configurar un canal diferente para las notificaciones de emparejamiento.*",
            ephemeral=True,
        )
    
    @app_commands.command(
        name="config",
        description="Configura los canales del sistema LFG"
    )
    @app_commands.describe(
        tipo="Tipo de canal a configurar",
        canal="El canal a usar"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Canal de Emparejamientos", value="match"),
        app_commands.Choice(name="Canal de Anuncios Semanales", value="announcement"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def config_command(
        self,
        interaction: discord.Interaction,
        tipo: str,
        canal: discord.TextChannel
    ):
        """
        Configure guild-specific channels.
        
        Usage:
        - /config tipo:match canal:#matches - Set match notifications channel
        - /config tipo:announcement canal:#announcements - Set weekly announcement channel
        """
        guild_id = interaction.guild_id
        guild_name = interaction.guild.name
        
        # Ensure guild exists in settings
        settings = get_guild_settings(guild_id)
        if not settings:
            save_guild_settings(guild_id, guild_name)
        
        # Update the specific channel
        update_guild_channel(guild_id, tipo, canal.id)
        
        tipo_names = {
            "match": "emparejamientos",
            "announcement": "anuncios semanales",
        }
        
        await interaction.response.send_message(
            f"✅ Canal de {tipo_names[tipo]} configurado a {canal.mention}",
            ephemeral=True,
        )
    
    @app_commands.command(
        name="verconfig",
        description="Ver la configuración actual del servidor"
    )
    @app_commands.default_permissions(administrator=True)
    async def view_config_command(self, interaction: discord.Interaction):
        """
        View the current guild configuration.
        
        Usage: /verconfig
        """
        guild_id = interaction.guild_id
        settings = get_guild_settings(guild_id)
        
        if not settings:
            await interaction.response.send_message(
                "⚠️ Este servidor aún no ha sido configurado.\n"
                "Usa `/setup` para configurar el sistema LFG.",
                ephemeral=True,
            )
            return
        
        embed = discord.Embed(
            title="⚙️ Configuración del Servidor",
            color=discord.Color.blue(),
        )
        
        lfg_channel = f"<#{settings['lfg_channel_id']}>" if settings.get('lfg_channel_id') else "No configurado"
        match_channel = f"<#{settings['match_channel_id']}>" if settings.get('match_channel_id') else "No configurado"
        announcement_channel = f"<#{settings['announcement_channel_id']}>" if settings.get('announcement_channel_id') else "No configurado"
        
        embed.add_field(name="📍 Canal LFG", value=lfg_channel, inline=True)
        embed.add_field(name="🔔 Canal de Emparejamientos", value=match_channel, inline=True)
        embed.add_field(name="📢 Canal de Anuncios", value=announcement_channel, inline=True)
        
        embed.set_footer(text="Usa /config para cambiar la configuración")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(
        name="cola",
        description="Ver quién está actualmente en la cola LFG"
    )
    async def queue_command(self, interaction: discord.Interaction):
        """
        Slash command to view the current queue.
        
        Useful to see who's looking for a group without joining.
        Shows both individual players and groups.
        
        Usage: /cola
        """
        guild_id = interaction.guild_id
        
        if queue_manager.is_empty(guild_id):
            await interaction.response.send_message(
                "📭 La cola está vacía. ¡Sé el primero en unirte!",
                ephemeral=True,
            )
            return
        
        embed = discord.Embed(
            title="📋 Cola LFG Actual",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )
        
        # List all users/groups with their ranges
        user_lines = []
        total_players = 0
        
        for user_id, data in queue_manager.items(guild_id):
            queue_since_unix = int(data["timestamp"].timestamp())
            composition = data.get("composition")
            if composition:
                # It's a group
                total = sum(composition.values())
                total_players += total
                comp_text = format_entry_composition(data)
                user_lines.append(
                    f"👥 <@{user_id}> (Grupo: {comp_text}, {total} jugadores) — "
                    f"Llaves {format_entry_key_preference(data)} — en cola <t:{queue_since_unix}:R>"
                )
            else:
                # It's solo
                total_players += 1
                roles_text = format_entry_composition(data)
                user_lines.append(
                    f"🎭 <@{user_id}> ({roles_text}) — "
                    f"Llaves {format_entry_key_preference(data)} — en cola <t:{queue_since_unix}:R>"
                )
        
        embed.add_field(
            name="🎮 Jugadores/Grupos Buscando",
            value="\n".join(user_lines) if user_lines else "Nadie en cola",
            inline=False,
        )
        
        embed.set_footer(text=f"Entradas en cola: {queue_manager.count(guild_id)} | Jugadores totales: {total_players}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(
        name="salir",
        description="Salir de la cola LFG"
    )
    async def leave_command(self, interaction: discord.Interaction):
        """
        Slash command to leave the queue.
        
        Alternative to clicking the Leave Queue button.
        If you're a group leader, your whole group leaves the queue.
        
        Usage: /salir
        """
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        
        result = await leave_queue_entry(
            interaction.client,
            guild_id,
            user_id,
            fallback_channel=interaction.channel,
        )

        if not result.get("removed"):
            await interaction.response.send_message(
                "ℹ️ No estabas en la cola.",
                ephemeral=True,
            )
            return

        if result.get("was_group"):
            await interaction.response.send_message(
                "✅ ¡Tu grupo ha sido eliminado de la cola!",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✅ ¡Has sido eliminado de la cola!",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    """
    Setup function for loading the cog.
    
    Called by bot.load_extension().
    """
    await bot.add_cog(LFGCog(bot))
