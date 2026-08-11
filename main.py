"""WipyBot entry point."""

from config.settings import DISCORD_TOKEN
from bot import WipyBot
from runtime import set_bot_client
from web.server import start_dashboard_server


def main():
    """Entry point for the bot."""
    import sys
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN no encontrado.")
        print("Asegurate de tener un archivo .env con DISCORD_TOKEN=tu_token_aqui")
        exit(1)
    
    print("Iniciando WipyBot...")

    # Start admin dashboard in parallel (if configured)
    start_dashboard_server()

    bot = WipyBot()
    set_bot_client(bot)
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
