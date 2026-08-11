from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models.database as database


@pytest.fixture(autouse=True)
def isolated_database(tmp_path):
    database.close_connection()
    database.DATABASE_PATH = tmp_path / "bot_data.db"
    database._schema_initialized = False
    yield
    database.close_connection()
    database._schema_initialized = False


@dataclass(frozen=True)
class Role:
    id: int


@dataclass(frozen=True)
class Member:
    id: int
    bot: bool
    roles: list[Role]
