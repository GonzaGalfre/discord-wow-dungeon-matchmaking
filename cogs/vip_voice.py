"""VIP voice channel access controls."""

from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands, tasks

from models import vip_voice as vip_repo
from models.guild_settings import save_guild_settings
from services.hub_sync import push_hub_snapshot_for_client
from services import vip_voice as vip_service
from views.vip_voice import VipVoicePanelView


class VipVoiceCog(commands.Cog):
    """Manages temporary VIP voice access roles and request panel interactions."""

    vip = app_commands.Group(name="vip", description="VIP voice channel commands")
    ACCESS_GRACE_SECONDS = 30

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._remove_tasks: dict[tuple[int, int, int], asyncio.Task] = {}
        self._recovered_guilds: set[int] = set()
        self.expire_requests_loop.start()

    def cog_unload(self) -> None:
        self.expire_requests_loop.cancel()
        for task in self._remove_tasks.values():
            task.cancel()

    async def _sync_configured_channel(self, guild: discord.Guild, config: vip_repo.VipVoiceChannel) -> bool:
        channel = guild.get_channel(config.channel_id)
        role = guild.get_role(config.role_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) or role is None:
            return False
        for member in channel.members:
            await vip_service.grant_access(member, role)
        await vip_service.sync_channel_lock(channel, role)
        return True

    async def _recover_guild(self, guild: discord.Guild) -> None:
        for config in vip_repo.list_vip_channels(guild.id):
            try:
                await self._sync_configured_channel(guild, config)
            except discord.Forbidden:
                continue

    def _cancel_removal(self, guild_id: int, user_id: int, role_id: int) -> None:
        key = (guild_id, user_id, role_id)
        task = self._remove_tasks.pop(key, None)
        if task is not None:
            task.cancel()

    def schedule_access_removal(self, guild_id: int, user_id: int, channel_id: int, role_id: int) -> None:
        key = (guild_id, user_id, role_id)
        self._cancel_removal(guild_id, user_id, role_id)
        self._remove_tasks[key] = asyncio.create_task(self._remove_after_delay(key, channel_id))

    async def _remove_after_delay(self, key: tuple[int, int, int], channel_id: int) -> None:
        guild_id, user_id, role_id = key
        try:
            await asyncio.sleep(self.ACCESS_GRACE_SECONDS)
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except (discord.NotFound, discord.Forbidden):
                    member = None
            role = guild.get_role(role_id)
            if member is None or role is None:
                return
            if vip_service.member_is_in_channel(member, channel_id):
                return
            await vip_service.revoke_access(member, role)
        except asyncio.CancelledError:
            raise
        except discord.Forbidden:
            return
        finally:
            self._remove_tasks.pop(key, None)

    @tasks.loop(minutes=1)
    async def expire_requests_loop(self) -> None:
        vip_repo.expire_old_requests()

    @expire_requests_loop.before_loop
    async def before_expire_requests_loop(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            if guild.id in self._recovered_guilds:
                continue
            self._recovered_guilds.add(guild.id)
            await self._recover_guild(guild)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        before_id = before.channel.id if before.channel else None
        after_id = after.channel.id if after.channel else None
        if before_id == after_id:
            return

        guild = member.guild
        before_config = vip_repo.get_vip_channel(guild.id, before_id) if before_id else None
        after_config = vip_repo.get_vip_channel(guild.id, after_id) if after_id else None

        if after_config is not None and after.channel is not None:
            role = guild.get_role(after_config.role_id)
            if role is not None:
                self._cancel_removal(guild.id, member.id, role.id)
                try:
                    await vip_service.grant_access(member, role)
                    if isinstance(after.channel, (discord.VoiceChannel, discord.StageChannel)):
                        await vip_service.lock_channel(after.channel, role)
                except discord.Forbidden:
                    pass

        if before_config is not None and before.channel is not None:
            role = guild.get_role(before_config.role_id)
            if role is not None:
                self.schedule_access_removal(guild.id, member.id, before_config.channel_id, role.id)
                try:
                    if isinstance(before.channel, (discord.VoiceChannel, discord.StageChannel)):
                        await vip_service.sync_channel_lock(before.channel, role)
                except discord.Forbidden:
                    pass

    @vip.command(name="add_channel", description="Configure a VIP voice channel and its temporary role.")
    @app_commands.default_permissions(administrator=True)
    async def add_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        role: discord.Role,
    ) -> None:
        save_guild_settings(interaction.guild.id, interaction.guild.name)
        bot_member = interaction.guild.me
        if bot_member is not None and role >= bot_member.top_role:
            await interaction.response.send_message(
                "That role is not below the bot's highest role, so I cannot grant or remove it.",
                ephemeral=True,
            )
            return
        if role.is_default() or role.managed:
            await interaction.response.send_message(
                "Choose a dedicated, editable role for this VIP channel.",
                ephemeral=True,
            )
            return

        existing_role_config = vip_repo.get_vip_channel_by_role(interaction.guild.id, role.id)
        if existing_role_config is not None and existing_role_config.channel_id != channel.id:
            await interaction.response.send_message(
                f"{role.mention} is already assigned to <#{existing_role_config.channel_id}>. Each VIP channel needs its own role.",
                ephemeral=True,
            )
            return

        previous_config = vip_repo.get_vip_channel(interaction.guild.id, channel.id)
        vip_repo.upsert_vip_channel(interaction.guild.id, channel.id, role.id)
        await interaction.response.defer(ephemeral=True)
        try:
            if previous_config is not None and previous_config.role_id != role.id:
                previous_role = interaction.guild.get_role(previous_config.role_id)
                if previous_role is not None:
                    await vip_service.unlock_channel(channel, previous_role)
            await self._sync_configured_channel(interaction.guild, vip_repo.VipVoiceChannel(interaction.guild.id, channel.id, role.id))
        except discord.Forbidden:
            await interaction.followup.send(
                "VIP channel saved, but I could not update permissions. I need Manage Channels and Manage Roles.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"Configured {channel.mention} with temporary role {role.mention}.", ephemeral=True)

    @vip.command(name="remove_channel", description="Remove a configured VIP voice channel.")
    @app_commands.default_permissions(administrator=True)
    async def remove_channel(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> None:
        config = vip_repo.get_vip_channel(interaction.guild.id, channel.id)
        deleted = vip_repo.delete_vip_channel(interaction.guild.id, channel.id)
        if config is not None:
            role = interaction.guild.get_role(config.role_id)
            if role is not None:
                try:
                    await vip_service.unlock_channel(channel, role)
                except discord.Forbidden:
                    pass
        await interaction.response.send_message(
            f"Removed VIP config for {channel.mention}." if deleted else "That channel was not configured as VIP.",
            ephemeral=True,
        )

    @vip.command(name="setup_panel", description="Post the permanent VIP access request panel.")
    @app_commands.default_permissions(administrator=True)
    async def setup_panel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        save_guild_settings(interaction.guild.id, interaction.guild.name)
        target_channel = channel or interaction.channel
        await interaction.response.defer(ephemeral=True)
        old_panel = vip_repo.get_vip_panel(interaction.guild.id)
        if old_panel is not None:
            old_channel = interaction.guild.get_channel(old_panel.channel_id)
            if old_channel is not None:
                try:
                    old_message = await old_channel.fetch_message(old_panel.message_id)
                    await old_message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
        message = await target_channel.send(embed=vip_service.build_panel_embed(), view=VipVoicePanelView())
        vip_repo.set_vip_panel(interaction.guild.id, target_channel.id, message.id)
        await interaction.followup.send(f"VIP request panel posted in {target_channel.mention}.", ephemeral=True)

    @vip.command(name="status", description="Show VIP voice configuration.")
    @app_commands.default_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=vip_service.build_status_embed(interaction.guild.id), ephemeral=True)

    @vip.command(name="sync", description="Repair VIP permissions and refresh the dashboard status.")
    @app_commands.default_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        synced = 0
        for config in vip_repo.list_vip_channels(interaction.guild.id):
            try:
                if await self._sync_configured_channel(interaction.guild, config):
                    synced += 1
            except discord.Forbidden:
                pass
        await push_hub_snapshot_for_client(self.bot)
        await interaction.followup.send(
            f"Synced {synced} VIP channel(s) and refreshed the dashboard status.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VipVoiceCog(bot))
