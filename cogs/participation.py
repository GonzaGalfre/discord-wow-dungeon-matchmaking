"""Participation tracking and raffle commands for WipyBot."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks

from models import participation as participation_repo
from models.guild_settings import save_guild_settings
from services.attendance import AttendanceService, VoiceTransition, is_eligible, is_officer
from services.participation import (
    ParticipationCalculator,
    ParticipationRules,
    format_duration,
    format_period,
    participation_line,
)
from services.participation_panel import build_panel_embed, leaderboard_text, message_chunks, user_progress_text
from services.raffle import RaffleError, draw_raffle, winner_ticket_numbers
from views.participation_panel import ParticipationPanelView
from views.raffle_details import RaffleDetailsView


def _calculator(settings) -> ParticipationCalculator:
    return ParticipationCalculator(
        ParticipationRules(
            first_voice_minutes_per_ticket=settings.first_voice_minutes_per_ticket,
            voice_minutes_per_ticket=settings.voice_minutes_per_ticket,
            messages_per_ticket=10,
            max_voice_tickets=settings.max_voice_tickets,
            max_message_tickets=0,
        )
    )


def _settings_summary(settings) -> str:
    voice_channels = ", ".join(f"<#{item}>" for item in sorted(settings.tracked_voice_channel_ids)) or "none"
    eligible_roles = ", ".join(f"<@&{item}>" for item in sorted(settings.eligible_role_ids)) or "none"
    officer_roles = ", ".join(f"<@&{item}>" for item in sorted(settings.officer_role_ids)) or "none"
    return "\n".join(
        [
            f"Enabled: {'yes' if settings.enabled else 'no'}",
            f"Configured: {'yes' if settings.configured else 'no'}",
            f"Eligible roles: {eligible_roles}",
            f"Officer roles: {officer_roles}",
            f"Voice channels: {voice_channels}",
            f"Voice tickets: first at {settings.first_voice_minutes_per_ticket} minutes, then 1 per {settings.voice_minutes_per_ticket} minutes, max {settings.max_voice_tickets}",
            f"Raffle announcements: {f'<#{settings.raffle_publish_channel_id}>' if settings.raffle_publish_channel_id else 'not configured'}",
            f"Panel: {f'<#{settings.panel_channel_id}>' if settings.panel_channel_id else 'not posted'}",
            f"Panel refresh: every {settings.panel_update_minutes} min",
        ]
    )


async def _require_officer(interaction: discord.Interaction, settings) -> bool:
    member = interaction.user if isinstance(interaction.user, discord.Member) else None
    if is_officer(member, settings):
        return True
    await interaction.response.send_message("You need an officer role to use this command.", ephemeral=True)
    return False


class ParticipationCog(commands.Cog):
    """Tracks per-server participation and manages raffle commands."""

    participation = app_commands.Group(name="participation", description="Participation commands")
    raffle = app_commands.Group(name="raffle", description="Participation raffle commands")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._recovered_guilds: set[int] = set()
        self.panel_refresh_loop.start()

    def cog_unload(self) -> None:
        self.panel_refresh_loop.cancel()

    def _configured_settings(self, guild_id: int):
        settings = participation_repo.get_participation_settings(guild_id)
        if settings is None or not settings.enabled or not settings.configured:
            return None
        return settings

    def _ensure_period(self, settings):
        return participation_repo.ensure_open_period(settings.guild_id, participation_repo.utc_now())

    async def _recover_current_voice_sessions(self, guild: discord.Guild, settings, now) -> None:
        attendance = AttendanceService(settings)
        for channel in guild.voice_channels:
            if channel.id not in settings.tracked_voice_channel_ids:
                continue
            for member in channel.members:
                attendance.open_session(guild.id, member, channel.id, now)

    async def _recover_guild(self, guild: discord.Guild) -> None:
        settings = self._configured_settings(guild.id)
        if settings is None:
            return
        now = participation_repo.utc_now()
        participation_repo.ensure_open_period(guild.id, now)
        AttendanceService(settings).close_all_open(guild.id, now)
        await self._recover_current_voice_sessions(guild, settings, now)

    async def _refresh_panel(self, settings) -> bool:
        if not settings.panel_channel_id or not settings.panel_message_id:
            return False
        channel = self.bot.get_channel(settings.panel_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(settings.panel_channel_id)
            except (discord.NotFound, discord.Forbidden):
                participation_repo.clear_participation_panel(settings.guild_id)
                return False
        try:
            message = await channel.fetch_message(settings.panel_message_id)
            await message.edit(embed=build_panel_embed(settings), view=ParticipationPanelView())
        except discord.NotFound:
            participation_repo.clear_participation_panel(settings.guild_id)
            return False
        except discord.Forbidden:
            return False
        participation_repo.mark_participation_panel_refreshed(settings.guild_id)
        return True

    @tasks.loop(minutes=1)
    async def panel_refresh_loop(self) -> None:
        now = participation_repo.utc_now()
        for settings in participation_repo.list_configured_participation_panels():
            last_updated = settings.panel_last_updated_at
            elapsed_seconds = None if last_updated is None else (now - last_updated).total_seconds()
            if elapsed_seconds is not None and elapsed_seconds < settings.panel_update_minutes * 60:
                continue
            await self._refresh_panel(settings)

    @panel_refresh_loop.before_loop
    async def before_panel_refresh_loop(self) -> None:
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
        settings = self._configured_settings(member.guild.id)
        if settings is None:
            return
        before_id = before.channel.id if before.channel else None
        after_id = after.channel.id if after.channel else None
        if before_id == after_id:
            return
        self._ensure_period(settings)
        AttendanceService(settings).handle_transition(
            VoiceTransition(member.guild.id, member, before_id, after_id, participation_repo.utc_now())
        )

    @participation.command(name="setup_roles", description="Set minimum eligible and officer roles.")
    @app_commands.default_permissions(administrator=True)
    async def setup_roles(
        self,
        interaction: discord.Interaction,
        eligible_role: discord.Role,
        officer_role: discord.Role,
    ) -> None:
        save_guild_settings(interaction.guild.id, interaction.guild.name)
        participation_repo.update_participation_roles(interaction.guild.id, [eligible_role.id], [officer_role.id])
        settings = participation_repo.get_or_create_participation_settings(interaction.guild.id)
        if settings.configured:
            self._ensure_period(settings)
            await self._recover_current_voice_sessions(interaction.guild, settings, participation_repo.utc_now())
        await interaction.response.send_message(_settings_summary(settings), ephemeral=True)

    @participation.command(name="add_voice", description="Track a voice channel for participation.")
    @app_commands.default_permissions(administrator=True)
    async def add_voice(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> None:
        save_guild_settings(interaction.guild.id, interaction.guild.name)
        settings = participation_repo.add_tracked_voice_channel(interaction.guild.id, channel.id)
        if settings.configured:
            self._ensure_period(settings)
            await self._recover_current_voice_sessions(interaction.guild, settings, participation_repo.utc_now())
        await interaction.response.send_message(_settings_summary(settings), ephemeral=True)

    @participation.command(name="rules", description="Set participation ticket rules.")
    @app_commands.default_permissions(administrator=True)
    async def rules(
        self,
        interaction: discord.Interaction,
        first_voice_minutes_per_ticket: app_commands.Range[int, 1, 10080] = 15,
        voice_minutes_per_ticket: app_commands.Range[int, 1, 10080] = 60,
        max_voice_tickets: app_commands.Range[int, 0, 1000] = 10,
    ) -> None:
        save_guild_settings(interaction.guild.id, interaction.guild.name)
        participation_repo.update_participation_rules(
            interaction.guild.id,
            first_voice_minutes_per_ticket,
            voice_minutes_per_ticket,
            max_voice_tickets,
        )
        settings = participation_repo.get_or_create_participation_settings(interaction.guild.id)
        await interaction.response.send_message(_settings_summary(settings), ephemeral=True)

    @participation.command(name="status", description="Show participation setup status.")
    @app_commands.default_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction) -> None:
        settings = participation_repo.get_or_create_participation_settings(interaction.guild.id)
        await interaction.response.send_message(_settings_summary(settings), ephemeral=True)

    @participation.command(name="raffle_channel", description="Set the channel where raffle draws are announced.")
    @app_commands.default_permissions(administrator=True)
    async def raffle_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        settings = participation_repo.update_raffle_publish_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(_settings_summary(settings), ephemeral=True)

    @participation.command(name="sync_voice", description="Start tracking eligible members currently in tracked voice channels.")
    async def sync_voice(self, interaction: discord.Interaction) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        if not await _require_officer(interaction, settings):
            return
        await interaction.response.defer(ephemeral=True)
        self._ensure_period(settings)
        before = len(participation_repo.list_open_voice_sessions(interaction.guild.id))
        await self._recover_current_voice_sessions(interaction.guild, settings, participation_repo.utc_now())
        after = len(participation_repo.list_open_voice_sessions(interaction.guild.id))
        await interaction.followup.send(f"Voice tracking synced. Open sessions: {after} ({after - before} new).", ephemeral=True)

    @participation.command(name="panel_create", description="Post the persistent participation panel in a channel.")
    @app_commands.default_permissions(administrator=True)
    async def panel_create(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        target_channel = channel or interaction.channel
        message = await target_channel.send(embed=build_panel_embed(settings), view=ParticipationPanelView())
        settings = participation_repo.update_participation_panel(interaction.guild.id, target_channel.id, message.id)
        await interaction.followup.send(
            f"Participation panel posted in {target_channel.mention}. Refreshes every {settings.panel_update_minutes} minutes.",
            ephemeral=True,
        )

    @participation.command(name="panel_refresh", description="Refresh the participation panel now.")
    async def panel_refresh(self, interaction: discord.Interaction) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        if not await _require_officer(interaction, settings):
            return
        await interaction.response.defer(ephemeral=True)
        refreshed = await self._refresh_panel(settings)
        await interaction.followup.send("Panel refreshed." if refreshed else "Panel could not be refreshed.", ephemeral=True)

    @participation.command(name="panel_interval", description="Set how often the public panel refreshes.")
    @app_commands.default_permissions(administrator=True)
    async def panel_interval(self, interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 1440]) -> None:
        settings = participation_repo.update_participation_panel_interval(interaction.guild.id, minutes)
        await interaction.response.send_message(f"Panel refresh interval set to {settings.panel_update_minutes} minutes.", ephemeral=True)

    @participation.command(name="panel_delete", description="Delete the saved participation panel message.")
    @app_commands.default_permissions(administrator=True)
    async def panel_delete(self, interaction: discord.Interaction) -> None:
        settings = participation_repo.get_or_create_participation_settings(interaction.guild.id)
        if not settings.panel_channel_id or not settings.panel_message_id:
            await interaction.response.send_message("No participation panel is configured.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = False
        channel = self.bot.get_channel(settings.panel_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(settings.panel_channel_id)
            except (discord.NotFound, discord.Forbidden):
                channel = None
        if channel is not None:
            try:
                message = await channel.fetch_message(settings.panel_message_id)
                await message.delete()
                deleted = True
            except (discord.NotFound, discord.Forbidden):
                pass
        participation_repo.clear_participation_panel(interaction.guild.id)
        await interaction.followup.send("Panel deleted." if deleted else "Panel settings cleared.", ephemeral=True)

    @participation.command(name="me", description="Show your current participation.")
    async def me(self, interaction: discord.Interaction) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            user_progress_text(settings, interaction.user.id),
            ephemeral=True,
        )

    @participation.command(name="leaderboard", description="Show current participation leaderboard.")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        await interaction.response.defer()
        for chunk in message_chunks(leaderboard_text(settings)):
            await interaction.followup.send(chunk)

    @participation.command(name="voice_status", description="Show open voice participation sessions.")
    async def voice_status(self, interaction: discord.Interaction) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        if not await _require_officer(interaction, settings):
            return
        await interaction.response.defer(ephemeral=True)
        now = participation_repo.utc_now()
        lines = []
        for item in participation_repo.list_open_voice_sessions(interaction.guild.id)[:25]:
            duration = int((now - item.started_at).total_seconds())
            lines.append(
                f"<@{item.user_id}> in <#{item.channel_id}> since {item.started_at:%Y-%m-%d %H:%M UTC} "
                f"({format_duration(duration)})"
            )
        await interaction.followup.send("\n".join(lines) or "No open voice sessions.", ephemeral=True)

    @raffle.command(name="preview", description="Preview raffle entries.")
    async def raffle_preview(self, interaction: discord.Interaction) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        if not await _require_officer(interaction, settings):
            return
        await interaction.response.defer(ephemeral=True)
        period = participation_repo.get_preview_period(interaction.guild.id) or self._ensure_period(settings)
        totals = participation_repo.totals_for_period(
            interaction.guild.id, period.starts_at, period.ends_at, participation_repo.utc_now(), _calculator(settings)
        )
        entries = [item for item in totals if item.total_tickets > 0]
        total_tickets = sum(item.total_tickets for item in entries)
        lines = [f"Period: {format_period(period.starts_at, period.ends_at)}", f"Total tickets: {total_tickets}"]
        lines.extend(participation_line(item) for item in entries[:25])
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @raffle.command(name="reset", description="Discard current raffle progress and open a fresh period.")
    async def raffle_reset(self, interaction: discord.Interaction) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        if not await _require_officer(interaction, settings):
            return
        await interaction.response.defer(ephemeral=True)
        now = participation_repo.utc_now()
        AttendanceService(settings).close_all_open(interaction.guild.id, now)
        result = participation_repo.reset_current_period(interaction.guild.id, now)
        if result is None:
            await interaction.followup.send("No open raffle period.", ephemeral=True)
            return
        await self._recover_current_voice_sessions(interaction.guild, settings, now)
        await interaction.followup.send("Raffle progress reset and a new period was opened.", ephemeral=True)

    @raffle.command(name="draw", description="Draw the current raffle and open a fresh period.")
    async def raffle_draw(self, interaction: discord.Interaction) -> None:
        settings = self._configured_settings(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message("Participation is not configured for this server.", ephemeral=True)
            return
        if not await _require_officer(interaction, settings):
            return
        if not settings.raffle_publish_channel_id:
            await interaction.response.send_message("Configure a raffle announcement channel first.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            result = draw_raffle(interaction.guild.id, participation_repo.utc_now(), _calculator(settings))
        except RaffleError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        if settings.raffle_publish_channel_id:
            channel = self.bot.get_channel(settings.raffle_publish_channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(settings.raffle_publish_channel_id)
                except (discord.NotFound, discord.Forbidden):
                    channel = None
            if isinstance(channel, discord.abc.Messageable):
                try:
                    message = await channel.send(
                        f"Raffle winner: <@{result.winner_user_id}>\n"
                        f"Winning number: {result.winning_number}\n"
                        f"Winner's ticket numbers: {winner_ticket_numbers(result.period_id)}\n"
                        f"Total tickets: {result.total_tickets}",
                        view=RaffleDetailsView(result.period_id),
                    )
                    participation_repo.mark_raffle_published(result.period_id, channel.id, message.id)
                except (discord.NotFound, discord.Forbidden):
                    pass
        await interaction.followup.send(
            "\n".join(
                [
                    f"Winner: <@{result.winner_user_id}>",
                    f"Participants: {result.participant_count}",
                    f"Total tickets: {result.total_tickets}",
                    f"Winning number: {result.winning_number}",
                    f"Winner tickets: {result.winner_tickets}",
                ]
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ParticipationCog(bot))
