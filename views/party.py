"""
Party views for the WoW Mythic+ LFG Bot.

This module contains views for party formation and confirmation.
"""

import asyncio
from typing import Dict, List, Tuple

import discord

from models.queue import queue_manager
from models.stats import record_completed_key
from services.matchmaking import (
    is_group_entry,
    calculate_common_range,
    group_has_keystone,
    group_requires_keystone,
    resolve_role_assignments,
)
from services.embeds import build_match_embed, format_entry_composition
from event_logger import log_event
from services.queue_status import refresh_lfg_setup_message


ACTIVE_DM_CONFIRMATIONS: Dict[Tuple[int, Tuple[int, ...]], "GroupDMConfirmationSession"] = {}


class GroupDMConfirmationSession:
    """
    Tracks an active DM confirmation round for a potential group.

    Each matched player/leader receives a private message with Yes/No buttons.
    The group is formed only if everyone still in queue confirms.
    """

    def __init__(
        self,
        client: discord.Client,
        guild_id: int,
        channel_id: int,
        matched_user_ids: List[int],
    ):
        self.client = client
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.matched_user_ids = matched_user_ids
        self.confirmed_ids: set[int] = set()
        self.failed_dm_user_ids: set[int] = set()
        self.channel_fallback_user_ids: set[int] = set()
        self.cancelled = False
        self.completed = False
        self._lock = asyncio.Lock()

        # Auto-confirm fake players (for testing)
        for user_id in matched_user_ids:
            if user_id > 900000000000000000:  # Fake player
                self.confirmed_ids.add(user_id)
    
    @property
    def key(self) -> Tuple[int, Tuple[int, ...]]:
        return self.guild_id, tuple(sorted(self.matched_user_ids))

    def users_still_in_queue(self) -> List[int]:
        return [uid for uid in self.matched_user_ids if queue_manager.contains(self.guild_id, uid)]

    def all_confirmed(self) -> bool:
        users_still = self.users_still_in_queue()
        return len(users_still) >= 2 and all(uid in self.confirmed_ids for uid in users_still)

    async def notify_channel(self, content: str) -> None:
        channel = self.client.get_channel(self.channel_id)
        if channel is None:
            try:
                channel = await self.client.fetch_channel(self.channel_id)
            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                return
        try:
            await channel.send(content)
        except (discord.errors.Forbidden, discord.errors.HTTPException):
            pass

    async def finalize_group(self) -> None:
        users_still = self.users_still_in_queue()
        if len(users_still) < 2:
            log_event(
                "group_finalize_aborted_not_enough_players",
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                users_still_in_queue=users_still,
            )
            self.completed = True
            ACTIVE_DM_CONFIRMATIONS.pop(self.key, None)
            return

        participants = []
        removed_entries = []

        for uid in users_still:
            entry = queue_manager.get(self.guild_id, uid)
            if not entry:
                continue

            participants.append(
                {
                    "user_id": uid,
                    "username": entry["username"],
                    "role": entry.get("role"),
                    "roles": entry.get("roles", []),
                    "composition": entry.get("composition"),
                    "key_min": entry["key_min"],
                    "key_max": entry["key_max"],
                    "has_keystone": entry.get("has_keystone", False),
                    "keystone_level": entry.get("keystone_level"),
                }
            )

            if uid > 900000000000000000:
                removed_entries.append(f"`{entry['username']}`")
            elif is_group_entry(entry):
                removed_entries.append(f"<@{uid}> (grupo)")
            else:
                removed_entries.append(f"<@{uid}>")

            queue_manager.remove(self.guild_id, uid)

        channel = self.client.get_channel(self.channel_id)
        if channel is None:
            try:
                channel = await self.client.fetch_channel(self.channel_id)
            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                channel = None

        if channel is not None:
            await refresh_lfg_setup_message(self.client, self.guild_id, channel)

        if group_requires_keystone(participants) and not group_has_keystone(participants):
            await self.notify_channel(
                "⚠️ **No se pudo cerrar el grupo.**\n"
                "La combinación final requiere llave +2 o superior y nadie tiene piedra registrada."
            )
            self.completed = True
            ACTIVE_DM_CONFIRMATIONS.pop(self.key, None)
            return

        role_assignments = resolve_role_assignments(participants) or {}
        for participant in participants:
            participant["resolved_role"] = role_assignments.get(str(participant["user_id"]))

        common_range = calculate_common_range(participants)
        key_level = common_range[0]
        log_event(
            "group_finalized",
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            matched_user_ids=self.matched_user_ids,
            finalized_user_ids=users_still,
            key_level=key_level,
            participants=participants,
        )

        try:
            record_completed_key(key_level, participants, guild_id=self.guild_id)
        except Exception as e:
            print(f"⚠️ Error recording completed key: {e}")

        await self.notify_channel(
            f"🎉 **¡Grupo formado!**\n\n"
            f"El grupo se ha formado con {', '.join(removed_entries)} "
            f"y han sido eliminados de la cola.\n\n"
            f"📊 *Llave +{key_level} registrada en las estadísticas.*\n\n"
            f"¡Buena suerte en la mazmorra! 🗝️"
        )

        self.completed = True
        ACTIVE_DM_CONFIRMATIONS.pop(self.key, None)


class DMConfirmationView(discord.ui.View):
    """Private DM confirmation buttons for one matched user/leader."""

    def __init__(self, session: GroupDMConfirmationSession, allowed_user_id: int):
        super().__init__(timeout=1800)  # 30 minutes
        self.session = session
        self.allowed_user_id = allowed_user_id

    @discord.ui.button(label="Sí, confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_dm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = interaction.user.id

        if user_id != self.allowed_user_id:
            await interaction.response.send_message(
                "⚠️ Este mensaje privado no te pertenece.",
                ephemeral=True,
            )
            return

        async with self.session._lock:
            if self.session.cancelled:
                await interaction.response.send_message(
                    "ℹ️ Esta confirmación ya fue cancelada.",
                    ephemeral=True,
                )
                return

            if self.session.completed:
                await interaction.response.send_message(
                    "ℹ️ El grupo ya fue confirmado y cerrado.",
                    ephemeral=True,
                )
                return

            if not queue_manager.contains(self.session.guild_id, user_id):
                await interaction.response.send_message(
                    "⚠️ Ya no estás en la cola.",
                    ephemeral=True,
                )
                return

            if user_id in self.session.confirmed_ids:
                await interaction.response.send_message(
                    "ℹ️ Ya habías confirmado. Esperando a los demás...",
                    ephemeral=True,
                )
                return

            self.session.confirmed_ids.add(user_id)
            everyone_confirmed = self.session.all_confirmed()
            log_event(
                "group_confirmation_yes_dm",
                guild_id=self.session.guild_id,
                user_id=user_id,
                confirmed_count=len(self.session.confirmed_ids),
                pending_user_ids=[
                    uid
                    for uid in self.session.users_still_in_queue()
                    if uid not in self.session.confirmed_ids
                ],
            )

        await interaction.response.send_message(
            "✅ Confirmación recibida. Te avisaremos cuando todos confirmen.",
            ephemeral=True,
        )

        if everyone_confirmed:
            await self.session.finalize_group()

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_dm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = interaction.user.id

        if user_id != self.allowed_user_id:
            await interaction.response.send_message(
                "⚠️ Este mensaje privado no te pertenece.",
                ephemeral=True,
            )
            return

        async with self.session._lock:
            if self.session.cancelled:
                await interaction.response.send_message(
                    "ℹ️ Esta confirmación ya fue cancelada.",
                    ephemeral=True,
                )
                return

            if self.session.completed:
                await interaction.response.send_message(
                    "ℹ️ El grupo ya fue confirmado y cerrado.",
                    ephemeral=True,
                )
                return

            self.session.cancelled = True
            ACTIVE_DM_CONFIRMATIONS.pop(self.session.key, None)
            log_event(
                "group_confirmation_cancelled_dm_no",
                guild_id=self.session.guild_id,
                user_id=user_id,
                matched_user_ids=self.session.matched_user_ids,
            )

        await interaction.response.send_message(
            "✅ Confirmación cancelada. Sigues en cola.",
            ephemeral=True,
        )
        await self.session.notify_channel(
            "❌ **Se canceló la confirmación del grupo en privado.**\n"
            "Al menos un jugador pulsó *No*. El grupo sigue en cola."
        )


class ChannelFallbackConfirmationView(discord.ui.View):
    """Channel fallback confirmation for users who cannot receive DMs."""

    def __init__(self, session: GroupDMConfirmationSession):
        super().__init__(timeout=1800)  # 30 minutes
        self.session = session

    def _is_fallback_user(self, user_id: int) -> bool:
        return user_id in self.session.channel_fallback_user_ids

    @discord.ui.button(label="Confirmar aquí", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = interaction.user.id

        if not self._is_fallback_user(user_id):
            await interaction.response.send_message(
                "⚠️ Este botón es solo para quienes no pudieron recibir DM.",
                ephemeral=True,
            )
            return

        async with self.session._lock:
            if self.session.cancelled:
                await interaction.response.send_message(
                    "ℹ️ Esta confirmación ya fue cancelada.",
                    ephemeral=True,
                )
                return

            if self.session.completed:
                await interaction.response.send_message(
                    "ℹ️ El grupo ya fue confirmado y cerrado.",
                    ephemeral=True,
                )
                return

            if not queue_manager.contains(self.session.guild_id, user_id):
                await interaction.response.send_message(
                    "⚠️ Ya no estás en la cola.",
                    ephemeral=True,
                )
                return

            if user_id in self.session.confirmed_ids:
                await interaction.response.send_message(
                    "ℹ️ Ya habías confirmado. Esperando a los demás...",
                    ephemeral=True,
                )
                return

            self.session.confirmed_ids.add(user_id)
            everyone_confirmed = self.session.all_confirmed()
            log_event(
                "group_confirmation_yes_channel_fallback",
                guild_id=self.session.guild_id,
                user_id=user_id,
                confirmed_count=len(self.session.confirmed_ids),
                pending_user_ids=[
                    uid
                    for uid in self.session.users_still_in_queue()
                    if uid not in self.session.confirmed_ids
                ],
            )

        await interaction.response.send_message(
            "✅ Confirmación recibida desde el canal.",
            ephemeral=True,
        )

        if everyone_confirmed:
            await self.session.finalize_group()

    @discord.ui.button(label="No (cancelar)", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = interaction.user.id

        if not self._is_fallback_user(user_id):
            await interaction.response.send_message(
                "⚠️ Este botón es solo para quienes no pudieron recibir DM.",
                ephemeral=True,
            )
            return

        async with self.session._lock:
            if self.session.cancelled:
                await interaction.response.send_message(
                    "ℹ️ Esta confirmación ya fue cancelada.",
                    ephemeral=True,
                )
                return

            if self.session.completed:
                await interaction.response.send_message(
                    "ℹ️ El grupo ya fue confirmado y cerrado.",
                    ephemeral=True,
                )
                return

            self.session.cancelled = True
            ACTIVE_DM_CONFIRMATIONS.pop(self.session.key, None)
            log_event(
                "group_confirmation_cancelled_channel_fallback_no",
                guild_id=self.session.guild_id,
                user_id=user_id,
                matched_user_ids=self.session.matched_user_ids,
            )

        await interaction.response.send_message(
            "✅ Confirmación cancelada. Sigues en cola.",
            ephemeral=True,
        )
        await self.session.notify_channel(
            "❌ **Se canceló la confirmación del grupo.**\n"
            "Un jugador del fallback en canal pulsó *No*. El grupo sigue en cola."
        )


class PartyCompleteView(discord.ui.View):
    """
    View containing the 'Party Complete' button.
    
    Attached to match notification messages.
    - 'Party Complete': Starts the confirmation process
    
    For groups: only the leader can interact with the button.
    
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

        await interaction.response.defer(ephemeral=True, thinking=True)

        key = (self.guild_id, tuple(sorted(users_still_in_queue)))
        existing_session = ACTIVE_DM_CONFIRMATIONS.get(key)
        if existing_session and not existing_session.cancelled and not existing_session.completed:
            await interaction.followup.send(
                "ℹ️ Ya hay una confirmación privada en curso para este grupo.",
                ephemeral=True,
            )
            return

        if not interaction.channel_id:
            await interaction.followup.send(
                "⚠️ No pude encontrar el canal para publicar el resultado final.",
                ephemeral=True,
            )
            return

        session = GroupDMConfirmationSession(
            client=interaction.client,
            guild_id=self.guild_id,
            channel_id=interaction.channel_id,
            matched_user_ids=users_still_in_queue,
        )
        ACTIVE_DM_CONFIRMATIONS[key] = session
        log_event(
            "group_confirmation_session_started",
            guild_id=self.guild_id,
            channel_id=interaction.channel_id,
            initiator_user_id=user_id,
            matched_user_ids=users_still_in_queue,
            auto_confirmed_fake_user_ids=[
                uid for uid in session.confirmed_ids if uid > 900000000000000000
            ],
        )

        dm_targets = [uid for uid in users_still_in_queue if uid <= 900000000000000000]
        for uid in dm_targets:
            if not queue_manager.contains(self.guild_id, uid):
                continue

            try:
                user = await interaction.client.fetch_user(uid)
                entry = queue_manager.get(self.guild_id, uid)
                is_group = bool(entry and is_group_entry(entry))

                embed = discord.Embed(
                    title="Confirmación privada de grupo",
                    description=(
                        "¿Confirmas que tu entrada está lista para cerrar este grupo?\n\n"
                        "✅ Si todos confirman, se cerrará el grupo y saldrán de cola.\n"
                        "❌ Si alguien pulsa *No*, se cancela esta confirmación."
                    ),
                    color=discord.Color.blurple(),
                )
                if is_group:
                    embed.add_field(
                        name="Tu entrada",
                        value=f"Líder de grupo ({format_entry_composition(entry)})",
                        inline=False,
                    )
                else:
                    role_text = format_entry_composition(entry) if entry else "desconocido"
                    embed.add_field(name="Tu entrada", value=f"Jugador solo ({role_text})", inline=False)
                embed.set_footer(text="Solo tú puedes responder este DM.")

                await user.send(embed=embed, view=DMConfirmationView(session, uid))
            except (discord.errors.Forbidden, discord.errors.HTTPException):
                session.failed_dm_user_ids.add(uid)
                log_event(
                    "group_confirmation_dm_send_failed",
                    guild_id=self.guild_id,
                    channel_id=interaction.channel_id,
                    user_id=uid,
                )

        if session.failed_dm_user_ids:
            session.channel_fallback_user_ids = set(session.failed_dm_user_ids)
            log_event(
                "group_confirmation_channel_fallback_enabled",
                guild_id=self.guild_id,
                channel_id=interaction.channel_id,
                fallback_user_ids=sorted(session.failed_dm_user_ids),
            )
            failed_mentions = " ".join(f"<@{uid}>" for uid in sorted(session.failed_dm_user_ids))
            await interaction.followup.send(
                "⚠️ Algunos jugadores tienen DMs cerrados. Ellos deberán confirmar en el canal.",
                ephemeral=True,
            )
            if interaction.channel and failed_mentions:
                await interaction.channel.send(
                    content=(
                        f"📢 {failed_mentions}\n"
                        "No pude enviarles DM. Confirmen aquí para cerrar el grupo:"
                    ),
                    view=ChannelFallbackConfirmationView(session),
                )

        await interaction.followup.send(
            "✅ Envié la confirmación por DM a todos los jugadores/líderes del match.",
            ephemeral=True,
        )

        if session.all_confirmed():
            await session.finalize_group()
