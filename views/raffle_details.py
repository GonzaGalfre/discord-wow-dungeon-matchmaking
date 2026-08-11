"""Persistent raffle draw details button."""

from __future__ import annotations

import discord

from models import participation as participation_repo


class RaffleDetailsView(discord.ui.View):
    def __init__(self, period_id: int) -> None:
        super().__init__(timeout=None)
        self.period_id = period_id
        button = discord.ui.Button(
            label="Details",
            style=discord.ButtonStyle.secondary,
            custom_id=f"raffle_details:{period_id}",
        )
        button.callback = self.show_details
        self.add_item(button)

    async def show_details(self, interaction: discord.Interaction) -> None:
        period = participation_repo.get_period(self.period_id)
        if period is None or period.status != participation_repo.RAFFLE_DRAWN:
            await interaction.response.send_message("Raffle details are unavailable.", ephemeral=True)
            return
        lines = [
            f"Winning number: {period.winning_number}",
            f"Total tickets: {period.total_tickets_at_draw}",
            "Participants:",
        ]
        lines.extend(
            f"<@{entry['user_id']}>: {entry['total_tickets']} tickets"
            for entry in participation_repo.list_raffle_entry_snapshots(self.period_id)
        )
        chunks: list[str] = []
        current = ""
        for line in lines:
            if current and len(current) + len(line) + 1 > 2000:
                chunks.append(current)
                current = ""
            current = f"{current}\n{line}" if current else line
        if current:
            chunks.append(current)
        await interaction.response.send_message(chunks[0], ephemeral=True)
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)
