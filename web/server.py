"""
Dashboard server startup helpers.
"""

from threading import Thread

import uvicorn

from config.settings import DASHBOARD_HOST, DASHBOARD_PASSWORD, DASHBOARD_PORT


def start_dashboard_server() -> None:
    """
    Start the dashboard server in a daemon thread.

    Dashboard only starts if DASHBOARD_PASSWORD is configured.
    """
    if not DASHBOARD_PASSWORD:
        print("ℹ️ Dashboard deshabilitado (DASHBOARD_PASSWORD no configurado).")
        return

    print(f"🌐 Dashboard admin disponible en http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")

    def _run() -> None:
        uvicorn.run(
            "web.app:app",
            host=DASHBOARD_HOST,
            port=DASHBOARD_PORT,
            log_level="warning",
        )

    thread = Thread(target=_run, daemon=True)
    thread.start()

