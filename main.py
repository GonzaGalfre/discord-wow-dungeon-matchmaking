"""
WoW Mythic+ LFG Discord Bot - Entry Point

A Discord bot that acts as a "Soft Matchmaker" for World of Warcraft
Mythic+ dungeons. Guild members can flag themselves as available for
specific Keystone levels, and the bot notifies everyone when potential
groups form.

Author: Tu Guild
Version: 2.0.0 (Modular Architecture)
Discord.py Version: 2.0+
"""

from config.settings import DISCORD_TOKEN
from bot import LFGBot
from web.server import start_dashboard_server


def main():
    """Entry point for the bot."""
    if not DISCORD_TOKEN:
        print("❌ ERROR: ¡DISCORD_TOKEN no encontrado!")
        print("Asegúrate de tener un archivo .env con DISCORD_TOKEN=tu_token_aquí")
        exit(1)
    
    print("🚀 Iniciando Bot LFG de WoW Mythic+...")

    # Start admin dashboard in parallel (if configured)
    start_dashboard_server()

    bot = LFGBot()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
