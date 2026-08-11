"""Persistent views for VIP voice access requests."""

from __future__ import annotations

import discord

from models import vip_voice as vip_repo
from services import vip_voice as vip_service

_VOICE_OR_STAGE_TYPES = [discord.ChannelType.voice, discord.ChannelType.stage_voice]


class _VipChannelSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Select a VIP voice channel...",
            channel_types=_VOICE_OR_STAGE_TYPES,
            custom_id="vip_voice:select_channel",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return

        selected = self.values[0]
        configured = vip_repo.get_vip_channel(interaction.guild.id, selected.id)
        if configured is None:
            await interaction.response.send_message("That channel is not configured as a VIP voice channel.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(configured.channel_id)
        role = interaction.guild.get_role(configured.role_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) or role is None:
            await interaction.response.send_message("That VIP channel or role no longer exists.", ephemeral=True)
            return

        if vip_service.member_is_in_channel(interaction.user, channel.id):
            await interaction.response.send_message("You are already in that VIP channel.", ephemeral=True)
            return

        if not channel.members:
            await interaction.response.send_message("That VIP channel is empty, so you can join it directly.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.response.send_message("You already have access to that VIP channel.", ephemeral=True)
            return

        request = vip_repo.create_request(interaction.guild.id, channel.id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        sent = await vip_service.notify_channel_members(
            request,
            interaction.user,
            channel,
            VipVoiceDecisionView(),
        )
        if sent == 0:
            vip_repo.decide_request(request.id, vip_repo.REQUEST_EXPIRED, interaction.client.user.id if interaction.client.user else 0)
            await interaction.followup.send(
                "I could not DM anyone currently in that VIP channel. They may have DMs disabled.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Request sent to {sent} member(s) currently in {channel.mention}. It expires in 5 minutes.",
            ephemeral=True,
        )


class VipVoicePanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(_VipChannelSelect())


class VipVoiceDecisionView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _decide(self, interaction: discord.Interaction, accepted: bool) -> None:
        request = vip_repo.get_request_by_notification(interaction.message.id)
        if request is None:
            await interaction.response.send_message("This VIP request could not be found.", ephemeral=True)
            return
        if interaction.user.id == request.requester_user_id:
            await interaction.response.send_message("You cannot approve your own VIP request.", ephemeral=True)
            return

        guild = interaction.client.get_guild(request.guild_id)
        if guild is None:
            await interaction.response.send_message("I cannot access that server right now.", ephemeral=True)
            return

        configured = vip_repo.get_vip_channel(request.guild_id, request.channel_id)
        channel = guild.get_channel(request.channel_id)
        role = guild.get_role(configured.role_id) if configured else None
        approver = next((member for member in channel.members if member.id == interaction.user.id), None)
        requester = guild.get_member(request.requester_user_id)
        if requester is None:
            try:
                requester = await guild.fetch_member(request.requester_user_id)
            except (discord.NotFound, discord.Forbidden):
                requester = None
        if configured is None or not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) or role is None:
            await interaction.response.send_message("That VIP channel or role no longer exists.", ephemeral=True)
            return
        if approver is None or not vip_service.member_is_in_channel(approver, channel.id):
            await interaction.response.send_message("Only members currently inside that VIP channel can decide this request.", ephemeral=True)
            return
        if request.status != vip_repo.REQUEST_PENDING:
            await interaction.response.send_message(f"This request was already {request.status.lower()}.", ephemeral=True)
            return
        if request.expires_at <= vip_repo.utc_now():
            vip_repo.decide_request(request.id, vip_repo.REQUEST_EXPIRED, interaction.user.id)
            await interaction.response.send_message("This request has expired.", ephemeral=True)
            return
        if requester is None:
            vip_repo.decide_request(request.id, vip_repo.REQUEST_EXPIRED, interaction.user.id)
            await interaction.response.send_message("The requester is no longer available in the server.", ephemeral=True)
            return

        if accepted:
            decided = vip_repo.decide_request(request.id, vip_repo.REQUEST_ACCEPTED, interaction.user.id)
            if decided is None or decided.status != vip_repo.REQUEST_ACCEPTED:
                await interaction.response.send_message("This request was already handled.", ephemeral=True)
                return
            await vip_service.grant_access(requester, role)
            vip_cog = interaction.client.get_cog("VipVoiceCog")
            if vip_cog is not None:
                vip_cog.schedule_access_removal(request.guild_id, requester.id, channel.id, role.id)
            try:
                await requester.send(f"Your request to join **{channel.name}** was accepted. You can join now.")
            except discord.Forbidden:
                pass
            await interaction.response.edit_message(content="Accepted. Access was granted.", embed=None, view=None)
            return

        decided = vip_repo.decide_request(request.id, vip_repo.REQUEST_DENIED, interaction.user.id)
        if decided is None or decided.status != vip_repo.REQUEST_DENIED:
            await interaction.response.send_message("This request was already handled.", ephemeral=True)
            return
        try:
            await requester.send(f"Your request to join **{channel.name}** was denied.")
        except discord.Forbidden:
            pass
        await interaction.response.edit_message(content="Denied. No access was granted.", embed=None, view=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="vip_voice:decision:accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._decide(interaction, True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="vip_voice:decision:deny")
    async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._decide(interaction, False)
