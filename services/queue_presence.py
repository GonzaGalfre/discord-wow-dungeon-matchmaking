"""
Background queue presence checks ("still in queue?" DM prompt).
"""

import asyncio
from datetime import datetime
from typing import Dict, Tuple

import discord

from config.settings import (
    QUEUE_STAY_PROMPT_AFTER_SECONDS,
    QUEUE_STAY_RESPONSE_TIMEOUT_SECONDS,
)
from event_logger import log_event
from models.queue import queue_manager
from services.queue_exit import leave_queue_entry


PENDING_QUEUE_PROMPTS: Dict[Tuple[int, int], datetime] = {}
LAST_PROMPT_ATTEMPTS: Dict[Tuple[int, int], datetime] = {}


class QueueStayPromptView(discord.ui.View):
    """DM prompt asking if the queued user/leader wants to keep waiting."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=QUEUE_STAY_RESPONSE_TIMEOUT_SECONDS)
        self.guild_id = guild_id
        self.user_id = user_id

    def _key(self) -> Tuple[int, int]:
        return (self.guild_id, self.user_id)

    @discord.ui.button(label="Sí, seguir en cola", style=discord.ButtonStyle.success, emoji="✅")
    async def stay_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Este mensaje no te pertenece.")
            return

        if not queue_manager.contains(self.guild_id, self.user_id):
            PENDING_QUEUE_PROMPTS.pop(self._key(), None)
            await interaction.response.send_message("ℹ️ Ya no estás en la cola.")
            return

        queue_manager.touch_timestamp(self.guild_id, self.user_id)
        PENDING_QUEUE_PROMPTS.pop(self._key(), None)
        LAST_PROMPT_ATTEMPTS[self._key()] = datetime.now()
        log_event(
            "queue_stay_prompt_confirmed",
            guild_id=self.guild_id,
            user_id=self.user_id,
        )
        await interaction.response.edit_message(
            content="✅ Perfecto, sigues en la cola. Te avisaremos cuando haya grupo compatible.",
            view=None,
        )

    @discord.ui.button(label="No, salir de cola", style=discord.ButtonStyle.danger, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Este mensaje no te pertenece.")
            return

        PENDING_QUEUE_PROMPTS.pop(self._key(), None)
        LAST_PROMPT_ATTEMPTS.pop(self._key(), None)
        result = await leave_queue_entry(interaction.client, self.guild_id, self.user_id)
        log_event(
            "queue_stay_prompt_declined",
            guild_id=self.guild_id,
            user_id=self.user_id,
            removed=result.get("removed", False),
        )
        if result.get("removed"):
            await interaction.response.edit_message(
                content="✅ Has salido de la cola.",
                view=None,
            )
            return

        await interaction.response.edit_message(
            content="ℹ️ Ya no estabas en la cola.",
            view=None,
        )


async def _send_queue_stay_prompt(client: discord.Client, guild_id: int, user_id: int) -> None:
    key = (guild_id, user_id)
    if key in PENDING_QUEUE_PROMPTS:
        return

    last_attempt = LAST_PROMPT_ATTEMPTS.get(key)
    if last_attempt is not None:
        elapsed = (datetime.now() - last_attempt).total_seconds()
        if elapsed < QUEUE_STAY_PROMPT_AFTER_SECONDS:
            return

    try:
        user = await client.fetch_user(user_id)
        await user.send(
            "⏳ **Sigues en cola**\n\n"
            "Llevas un rato esperando y aún no hay match.\n"
            "¿Quieres seguir en cola?",
            view=QueueStayPromptView(guild_id, user_id),
        )
        PENDING_QUEUE_PROMPTS[key] = datetime.now()
        LAST_PROMPT_ATTEMPTS[key] = datetime.now()
        log_event(
            "queue_stay_prompt_sent",
            guild_id=guild_id,
            user_id=user_id,
        )
    except (discord.errors.Forbidden, discord.errors.NotFound, discord.errors.HTTPException):
        # Cannot DM this user; skip silently.
        LAST_PROMPT_ATTEMPTS[key] = datetime.now()
        return


async def _expire_stale_prompts(client: discord.Client) -> None:
    now = datetime.now()
    expired = []
    for key, sent_at in PENDING_QUEUE_PROMPTS.items():
        if (now - sent_at).total_seconds() >= QUEUE_STAY_RESPONSE_TIMEOUT_SECONDS:
            expired.append(key)

    for guild_id, user_id in expired:
        PENDING_QUEUE_PROMPTS.pop((guild_id, user_id), None)
        entry = queue_manager.get(guild_id, user_id)
        if entry is None:
            continue
        if entry.get("match_message_id") is not None:
            continue
        await leave_queue_entry(client, guild_id, user_id)
        log_event(
            "queue_stay_prompt_expired_auto_leave",
            guild_id=guild_id,
            user_id=user_id,
        )
        try:
            user = await client.fetch_user(user_id)
            await user.send(
                "⌛ No recibimos respuesta a tiempo y te sacamos de la cola.\n"
                "Cuando quieras, puedes volver a unirte."
            )
        except (discord.errors.Forbidden, discord.errors.NotFound, discord.errors.HTTPException):
            pass


async def queue_presence_watchdog(client: discord.Client) -> None:
    """
    Periodically DM users/leaders who have been waiting too long in queue.
    """
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            await _expire_stale_prompts(client)
            now = datetime.now()
            for guild_id in queue_manager.get_guild_ids():
                for user_id, entry in queue_manager.items(guild_id):
                    if entry.get("match_message_id") is not None:
                        continue
                    waited_seconds = (now - entry["timestamp"]).total_seconds()
                    if waited_seconds < QUEUE_STAY_PROMPT_AFTER_SECONDS:
                        continue
                    await _send_queue_stay_prompt(client, guild_id, user_id)
        except Exception as exc:
            print(f"⚠️ Error in queue presence watchdog: {exc}")
        await asyncio.sleep(30)
