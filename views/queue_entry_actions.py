"""
Queue-entry action views shown after joining queue.
"""

import discord

from models.queue import queue_manager
from services.queue_exit import leave_queue_entry


class QueueEntryActionsView(discord.ui.View):
    """
    Actions available in the "you are in queue" ephemeral message.
    """

    def __init__(self, guild_id: int, owner_user_id: int):
        super().__init__(timeout=1800)  # 30 minutes
        self.guild_id = guild_id
        self.owner_user_id = owner_user_id

    def _build_active_queue_text(self) -> str:
        entry = queue_manager.get(self.guild_id, self.owner_user_id)
        if entry is None:
            return (
                "ℹ️ Ya no estás en la cola.\n\n"
                "*Este mensaje era efímero y puede quedar desactualizado.*"
            )
        queue_since_unix = int(entry["timestamp"].timestamp())
        return (
            "✅ Sigues en la cola.\n\n"
            f"⏱️ **En cola desde:** <t:{queue_since_unix}:R>\n\n"
            "Si no respondes al DM de confirmación de espera, puedes salir automáticamente."
        )

    @discord.ui.button(
        label="Verificar estado",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
    )
    async def refresh_status_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.owner_user_id:
            await interaction.response.send_message(
                "⚠️ Este botón no te pertenece.",
                ephemeral=True,
            )
            return

        if not queue_manager.contains(self.guild_id, self.owner_user_id):
            await interaction.response.edit_message(
                content=(
                    "ℹ️ Ya no estás en la cola.\n\n"
                    "*Este mensaje era efímero y quedó desactualizado.*"
                ),
                view=None,
            )
            return

        await interaction.response.edit_message(
            content=self._build_active_queue_text(),
            view=self,
        )

    @discord.ui.button(
        label="Salir de Cola",
        style=discord.ButtonStyle.danger,
        emoji="🚪",
    )
    async def leave_queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.owner_user_id:
            await interaction.response.send_message(
                "⚠️ Este botón no te pertenece.",
                ephemeral=True,
            )
            return

        result = await leave_queue_entry(
            interaction.client,
            self.guild_id,
            self.owner_user_id,
            fallback_channel=interaction.channel,
        )

        if not result.get("removed"):
            await interaction.response.edit_message(
                content=(
                    "ℹ️ Ya no estás en la cola.\n\n"
                    "*Este mensaje era efímero y quedó desactualizado.*"
                ),
                view=None,
            )
            return

        if result.get("was_group"):
            text = "✅ Tu grupo ha salido de la cola."
        else:
            text = "✅ Has salido de la cola."

        await interaction.response.edit_message(
            content=f"{text}\n\n*Puedes cerrar este mensaje.*",
            view=None,
        )
