"""
Bot class for the WoW Mythic+ LFG Bot.

This module contains the LFGBot class which extends commands.Bot.

Multi-guild support: The bot can work with multiple Discord servers simultaneously.
Each guild has its own queue and channel configuration.
"""

import discord
from discord.ext import commands

from views.join_queue import JoinQueueView
from models.guild_settings import get_all_configured_guilds


class LFGBot(commands.Bot):
    """
    Custom Bot class for the LFG system.
    
    Inherits from commands.Bot to override setup_hook(),
    which is the best place to register persistent views.
    
    Supports multiple guilds with independent queues and configurations.
    """
    
    def __init__(self):
        intents = discord.Intents.default()
        
        super().__init__(
            command_prefix="!",
            intents=intents,
        )
    
    async def setup_hook(self):
        """
        Called before the bot connects to Discord.
        
        Here we:
        1. Register persistent views so they work after restarts
        2. Load the LFG cog with slash commands
        3. Sync the command tree
        
        Note: PartyCompleteView is not registered here because it needs
        the match user IDs, which are lost on restart.
        This is acceptable since the queue is also in memory.
        """
        # Register persistent views
        self.add_view(JoinQueueView())
        
        # Load cogs
        try:
            await self.load_extension("cogs.lfg")
            print("✓ LFG cog cargado")
        except Exception as e:
            print(f"✗ Error cargando LFG cog: {e}")
        
        try:
            await self.load_extension("cogs.stats")
            print("✓ Stats cog cargado")
        except Exception as e:
            print(f"✗ Error cargando Stats cog: {e}")
        
        try:
            await self.load_extension("cogs.dev")
            print("✓ Dev cog cargado")
        except Exception as e:
            print(f"✗ Error cargando Dev cog: {e}")
            import traceback
            traceback.print_exc()
        
        # Sync slash commands globally
        await self.tree.sync()
        print("✅ Comandos sincronizados globalmente")
    
    async def on_ready(self):
        """
        Called when the bot has connected to Discord.
        """
        print(f"🤖 Conectado como {self.user} (ID: {self.user.id})")
        print(f"📡 Conectado a {len(self.guilds)} servidor(es):")
        
        # List all connected guilds
        for guild in self.guilds:
            print(f"   • {guild.name} (ID: {guild.id})")
        
        print("─" * 40)
        print("💡 Comandos disponibles globalmente (pueden tardar 1 minuto en aparecer)")
        print("   Si necesitas comandos inmediatos, usa: /dev_sync")
        print("─" * 40)
        
        # Show configured guilds
        configured_guilds = get_all_configured_guilds()
        if configured_guilds:
            print(f"⚙️ {len(configured_guilds)} servidor(es) configurado(s):")
            for guild_data in configured_guilds:
                guild_name = guild_data.get("guild_name", "Unknown")
                has_match = "✓" if guild_data.get("match_channel_id") else "✗"
                has_announce = "✓" if guild_data.get("announcement_channel_id") else "✗"
                print(f"   • {guild_name} [match: {has_match}] [anuncios: {has_announce}]")
        else:
            print("⚠️ Ningún servidor configurado. Usa /setup en cada servidor.")
        
        print("─" * 40)
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="grupos de M+ 🗝️",
            )
        )
