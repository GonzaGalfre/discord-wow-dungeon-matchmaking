"""
FastAPI app for the admin dashboard.
"""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from web.routes.auth import require_dashboard_auth
from web.routes.dashboard import router as dashboard_router

app = FastAPI(
    title="WoW Mythic+ LFG Dashboard",
    description="Admin dashboard for queues, groups, leaderboard, and testing actions.",
    version="1.0.0",
)

app.include_router(dashboard_router, tags=["dashboard"])
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


def _asset_version() -> str:
    """
    Build a cache-busting version from static asset mtimes.
    """
    static_dir = Path(__file__).parent / "static"
    assets = [
        static_dir / "js" / "dashboard.js",
        static_dir / "css" / "dashboard.css",
    ]
    existing = [asset for asset in assets if asset.exists()]
    if not existing:
        return "1"
    latest_mtime = max(int(asset.stat().st_mtime) for asset in existing)
    return str(latest_mtime)


def _resolve_base_path(request: Request) -> str:
    """
    Resolve deployment base path for static + API URLs.
    """
    raw = (
        request.scope.get("root_path")
        or request.headers.get("x-forwarded-prefix")
        or request.headers.get("x-script-name")
        or ""
    )
    normalized = str(raw).strip().rstrip("/")
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_dashboard_auth)])
def dashboard_index(request: Request) -> str:
    """
    Serve the dashboard page.
    """
    template_path = Path(__file__).parent / "templates" / "index.html"
    html = template_path.read_text(encoding="utf-8")
    version = _asset_version()
    base_path = _resolve_base_path(request)
    css_url = f"{base_path}/static/css/dashboard.css?v={version}"
    js_url = f"{base_path}/static/js/dashboard.js?v={version}"
    html = html.replace("__DASHBOARD_BASE_PATH__", base_path)
    html = html.replace("__DASHBOARD_CSS_URL__", css_url)
    html = html.replace("__DASHBOARD_JS_URL__", js_url)
    return html

