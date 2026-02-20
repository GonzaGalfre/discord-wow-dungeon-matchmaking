"""
Authentication helpers for dashboard routes.
"""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from config.settings import DASHBOARD_PASSWORD

security = HTTPBasic()


def require_dashboard_auth(
    credentials: HTTPBasicCredentials = Depends(security),
) -> None:
    """
    Enforce basic auth using the configured dashboard password.
    """
    if not DASHBOARD_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard password is not configured.",
        )

    provided = credentials.password.encode("utf-8")
    expected = DASHBOARD_PASSWORD.encode("utf-8")
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid dashboard credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )

