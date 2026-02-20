"""
Stats Cog for the WoW Mythic+ LFG Bot.

This module contains commands for viewing leaderboards and stats,
plus the weekly announcement background task.

Multi-guild support: Announcements are sent to all configured guilds.
"""

from datetime import datetime, time, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from models.guild_settings import get_all_configured_guilds, get_announcement_channel_id
from services.leaderboard import (
    build_weekly_leaderboard_embed,
    build_alltime_leaderboard_embed,
    build_player_stats_embed,
    build_weekly_announcement_embed,
)


# UTC-3 timezone
UTC_MINUS_3 = timezone(timedelta(hours=-3))

# Reset time: Tuesday 12:00 PM UTC-3
RESET_TIME = time(hour=12, minute=0, tzinfo=UTC_MINUS_3)


class StatsCog(commands.Cog):
    """
    Cog containing stats and leaderboard commands.
    
    Commands:
    - /leaderboard: View weekly or all-time leaderboard
    - /mystats: View your personal stats
    
    Background Tasks:
    - Weekly announcement on Tuesday reset (sent to all configured guilds)
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_announcement.start()
    
    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.weekly_announcement.cancel()
    
    @app_commands.command(
        name="leaderboard",
        description="Ver la tabla de posiciones"
    )
    @app_commands.describe(
        periodo="Período de tiempo para mostrar"
    )
    @app_commands.choices(periodo=[
        app_commands.Choice(name="Esta Semana", value="weekly"),
        app_commands.Choice(name="Histórico", value="alltime"),
    ])
    async def leaderboard_command(
        self,
        interaction: discord.Interaction,
        periodo: str = "weekly"
    ):
        """
        Show the leaderboard.
        
        Usage:
        - /leaderboard - Shows weekly leaderboard
        - /leaderboard periodo:Histórico - Shows all-time leaderboard
        """
        guild_id = interaction.guild_id
        
        if periodo == "alltime":
            embed = build_alltime_leaderboard_embed(guild_id=guild_id)
        else:
            embed = build_weekly_leaderboard_embed(guild_id=guild_id)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(
        name="mystats",
        description="Ver tus estadísticas personales"
    )
    async def mystats_command(self, interaction: discord.Interaction):
        """
        Show the user's personal stats.
        
        Usage: /mystats
        """
        guild_id = interaction.guild_id
        embed = build_player_stats_embed(
            interaction.user.id,
            interaction.user.display_name,
            guild_id=guild_id
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(
        name="playerstats",
        description="Ver las estadísticas de un jugador"
    )
    @app_commands.describe(jugador="El jugador a consultar")
    async def playerstats_command(
        self,
        interaction: discord.Interaction,
        jugador: discord.Member
    ):
        """
        Show another player's stats.
        
        Usage: /playerstats @player
        """
        guild_id = interaction.guild_id
        embed = build_player_stats_embed(
            jugador.id,
            jugador.display_name,
            guild_id=guild_id
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(
        name="anuncio",
        description="Publica el resumen semanal ahora mismo"
    )
    @app_commands.describe(
        semana="¿Qué semana mostrar? (Por defecto: anterior, como el anuncio del martes)"
    )
    @app_commands.choices(semana=[
        app_commands.Choice(name="Semana anterior (estilo reset del martes)", value="previous"),
        app_commands.Choice(name="Semana actual (para probar)", value="current"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def announce_command(
        self,
        interaction: discord.Interaction,
        semana: str = "previous"
    ):
        """
        Manually trigger the weekly announcement.
        
        Admin only. Posts to the current channel.
        Por defecto muestra la semana anterior (como el anuncio automático del martes).
        Usa "Semana actual" para ver las llaves de esta semana (útil para probar).
        
        Usage: /anuncio
        Usage: /anuncio semana:Semana actual
        """
        guild_id = interaction.guild_id
        embed = build_weekly_announcement_embed(
            guild_id=guild_id,
            use_current_week=(semana == "current")
        )
        
        await interaction.response.send_message(
            content="📢 ¡Resumen semanal de Mythic+!",
            embed=embed
        )
    
    @tasks.loop(time=RESET_TIME)
    async def weekly_announcement(self):
        """
        Background task that runs every Tuesday at 12:00 PM UTC-3.
        
        Posts the weekly summary to all configured guild announcement channels.
        """
        # Check if it's Tuesday
        now = datetime.now(UTC_MINUS_3)
        if now.weekday() != 1:  # 1 = Tuesday
            return
        
        # Get all configured guilds
        guilds = get_all_configured_guilds()
        
        if not guilds:
            print("⚠️ No guilds configured, skipping weekly announcement")
            return
        
        sent_count = 0
        
        for guild_data in guilds:
            guild_id = guild_data["guild_id"]
            announcement_channel_id = guild_data.get("announcement_channel_id")
            
            if not announcement_channel_id:
                continue
            
            channel = self.bot.get_channel(announcement_channel_id)
            if not channel:
                print(f"⚠️ Could not find announcement channel {announcement_channel_id} for guild {guild_id}")
                continue
            
            # Build guild-specific announcement
            embed = build_weekly_announcement_embed(guild_id=guild_id)
            
            try:
                await channel.send(
                    content="@here 📢 ¡Resumen semanal de Mythic+!",
                    embed=embed
                )
                sent_count += 1
                print(f"✅ Weekly announcement sent to guild {guild_id}")
            except discord.errors.Forbidden:
                print(f"❌ No permission to send to channel {announcement_channel_id} in guild {guild_id}")
            except Exception as e:
                print(f"❌ Error sending weekly announcement to guild {guild_id}: {e}")
        
        print(f"📢 Weekly announcements sent to {sent_count} guild(s)")
    
    @weekly_announcement.before_loop
    async def before_weekly_announcement(self):
        """Wait for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    """
    Setup function for loading the cog.
    
    Called by bot.load_extension().
    """
    await bot.add_cog(StatsCog(bot))
