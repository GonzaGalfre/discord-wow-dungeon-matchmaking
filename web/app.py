"""
FastAPI app for the admin dashboard.
"""

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from web.routes.auth import require_dashboard_auth
from web.routes.dashboard import router as dashboard_router

app = FastAPI(
    title="WoW Mythic+ LFG Dashboard",
    description="Read-only admin dashboard for queues, groups, and leaderboard.",
    version="1.0.0",
)

app.include_router(dashboard_router, tags=["dashboard"])
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_dashboard_auth)])
def dashboard_index() -> str:
    """
    Serve the dashboard page.
    """
    template_path = Path(__file__).parent / "templates" / "index.html"
    return template_path.read_text(encoding="utf-8")

