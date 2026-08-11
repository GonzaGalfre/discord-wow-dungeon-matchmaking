"""Discord bot class for WipyBot."""

import discord
from discord.ext import commands

from config.settings import HUB_API_BASE_URL
from services.hub_sync import hub_sync_loop
from views.move_panel import MovePanelView
from views.participation_panel import ParticipationPanelView
from views.raid_signup import RaidSignupView
from views.vip_voice import VipVoiceDecisionView, VipVoicePanelView
from models.guild_settings import get_all_configured_guilds
from models.participation import list_published_raffle_periods
from views.raffle_details import RaffleDetailsView


class WipyBot(commands.Bot):
    """Custom Discord bot class for WipyBot."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.voice_states = True
        intents.messages = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
        )
        self._guild_commands_synced = False
        self._hub_sync_task = None
    
    async def setup_hook(self):
        """Register persistent infrastructure views and slash commands."""
        self.add_view(MovePanelView())
        self.add_view(RaidSignupView())
        self.add_view(ParticipationPanelView())
        self.add_view(VipVoicePanelView())
        self.add_view(VipVoiceDecisionView())
        for period in list_published_raffle_periods():
            self.add_view(RaffleDetailsView(period.id))
        if HUB_API_BASE_URL:
            self._hub_sync_task = self.loop.create_task(hub_sync_loop(self))
            print(f"Hub sync habilitado: {HUB_API_BASE_URL}")
        
        try:
            await self.load_extension("cogs.raid")
            print("Raid cog cargado")
        except Exception as e:
            print(f"Error cargando Raid cog: {e}")
        
        try:
            await self.load_extension("cogs.voice")
            print("Voice cog cargado")
        except Exception as e:
            print(f"Error cargando Voice cog: {e}")

        try:
            await self.load_extension("cogs.participation")
            print("Participation cog cargado")
        except Exception as e:
            print(f"Error cargando Participation cog: {e}")

        try:
            await self.load_extension("cogs.vip_voice")
            print("VIP voice cog cargado")
        except Exception as e:
            print(f"Error cargando VIP voice cog: {e}")

        commands_to_restore = list(self.tree.get_commands())
        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        for command in commands_to_restore:
            self.tree.add_command(command)
        print("Comandos globales remotos limpiados; se usaran comandos por servidor")
    
    async def on_ready(self):
        """Called when the bot has connected to Discord."""
        if not self._guild_commands_synced:
            self._guild_commands_synced = True
            for guild in self.guilds:
                guild_object = discord.Object(id=guild.id)
                self.tree.clear_commands(guild=guild_object)
                self.tree.copy_global_to(guild=guild_object)
                await self.tree.sync(guild=guild_object)
                print(f"Comandos sincronizados en guild: {guild.name} ({guild.id})")

        print(f"Conectado como {self.user} (ID: {self.user.id})")
        print(f"Conectado a {len(self.guilds)} servidor(es):")
        
        for guild in self.guilds:
            print(f"   - {guild.name} (ID: {guild.id})")
        
        print("─" * 40)
        print("Comandos sincronizados en los servidores conectados")
        print("─" * 40)
        
        configured_guilds = get_all_configured_guilds()
        if configured_guilds:
            print(f"{len(configured_guilds)} servidor(es) configurado(s):")
            for guild_data in configured_guilds:
                guild_name = guild_data.get("guild_name", "Unknown")
                has_signup = "yes" if guild_data.get("signup_channel_id") else "no"
                print(f"   - {guild_name} [signup: {has_signup}]")
        else:
            print("Ningun servidor configurado todavia.")
        
        print("─" * 40)
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="raid signups",
            )
        )
