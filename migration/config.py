"""Migration config: SQLite source + PostgreSQL target connections."""

import os
import sqlite3
import sys

import psycopg2

# ── SQLite source ────────────────────────────────────────────────────
# Try multiple known locations for the Keka SQLite database
_SQLITE_CANDIDATES = [
    os.environ.get("KEKA_SQLITE_PATH", ""),
    "/Users/allfred/scripts/keka/keka_hr.db",
    "/Users/donna/.openclaw/workspace/scripts/keka/data/keka.db",
    "/Users/allfred/scripts/keka/data/keka.db",
]

SQLITE_PATH: str = ""
for _p in _SQLITE_CANDIDATES:
    if _p and os.path.isfile(_p):
        SQLITE_PATH = _p
        break

if not SQLITE_PATH:
    print("⚠  No SQLite database found. Searched:", _SQLITE_CANDIDATES)

# ── PostgreSQL target ────────────────────────────────────────────────
# Import from the project config if available, else fall back to env/default
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from backend.config import settings
    DATABASE_URL_SYNC = settings.DATABASE_URL_SYNC
except Exception:
    DATABASE_URL_SYNC = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://hr_app:password@localhost:5432/hr_intelligence",
    )


def get_sqlite_conn() -> sqlite3.Connection:
    """Return a sqlite3 connection with row factory enabled."""
    if not SQLITE_PATH:
        raise FileNotFoundError("Keka SQLite database not found")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_conn():
    """Return a psycopg2 connection to the PostgreSQL database."""
    return psycopg2.connect(DATABASE_URL_SYNC)
