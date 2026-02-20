"""
LFG Cog for the WoW Mythic+ LFG Bot.

This module contains all slash commands for the LFG system.
"""

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import ROLES
from models.queue import queue_manager
from models.guild_settings import save_guild_settings, get_guild_settings, update_guild_channel
from services.matchmaking import is_group_entry
from services.embeds import format_entry_composition
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
        
        embed = discord.Embed(
            title="🗝️ Buscador de Grupos Mythic+",
            description=(
                "¿Buscas gente para hacer mazmorras Mythic+?\n\n"
                "**Cómo funciona:**\n"
                "1️⃣ Haz clic en el botón de abajo\n"
                "2️⃣ Selecciona tu rol (Tanque, Sanador o DPS)\n"
                "3️⃣ Elige tu rango de llaves preferido\n"
                "4️⃣ ¡Serás notificado cuando otros busquen lo mismo!\n\n"
                "*Solo puedes estar en una cola a la vez.*"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="¡Feliz cacería de mazmorras! 🎮")
        
        await interaction.channel.send(embed=embed, view=JoinQueueView())
        
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
            composition = data.get("composition")
            if composition:
                # It's a group
                total = sum(composition.values())
                total_players += total
                comp_text = format_entry_composition(data)
                user_lines.append(
                    f"👥 <@{user_id}> (Grupo: {comp_text}, {total} jugadores) — Llaves {data['key_min']}-{data['key_max']}"
                )
            else:
                # It's solo
                total_players += 1
                role = data.get("role")
                role_info = ROLES.get(role, {"name": "?", "emoji": "❓"})
                user_lines.append(
                    f"{role_info['emoji']} <@{user_id}> — Llaves {data['key_min']}-{data['key_max']}"
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
        
        # Check if it was a group before removing
        entry = queue_manager.get(guild_id, user_id)
        was_group = entry and is_group_entry(entry)
        has_match = entry and entry.get("match_message_id") is not None
        
        if queue_manager.remove(guild_id, user_id):
            if was_group:
                if has_match:
                    await interaction.response.send_message(
                        "✅ ¡Tu grupo ha sido eliminado de la cola!\n\n"
                        "💡 *Nota: Si tenías un emparejamiento activo, usa el botón "
                        "'Salir de Cola' en el mensaje de emparejamiento para notificar "
                        "correctamente a los demás jugadores.*",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "✅ ¡Tu grupo ha sido eliminado de la cola!",
                        ephemeral=True,
                    )
            else:
                if has_match:
                    await interaction.response.send_message(
                        "✅ ¡Has sido eliminado de la cola!\n\n"
                        "💡 *Nota: Si tenías un emparejamiento activo, usa el botón "
                        "'Salir de Cola' en el mensaje de emparejamiento para notificar "
                        "correctamente a los demás jugadores.*",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "✅ ¡Has sido eliminado de la cola!",
                        ephemeral=True,
                    )
        else:
            await interaction.response.send_message(
                "ℹ️ No estabas en la cola.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    """
    Setup function for loading the cog.
    
    Called by bot.load_extension().
    """
    await bot.add_cog(LFGCog(bot))
