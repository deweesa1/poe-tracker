"""SQLite connection and numbered migrations.

Each file in migrations/ named NNNN_name.sql runs once, in order; the number
of the last one applied is kept in PRAGMA user_version.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import paths


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path | None = None, readonly: bool = False) -> sqlite3.Connection:
    path = path or paths.db_path()
    if readonly:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False, timeout=30)
    else:
        con = sqlite3.connect(path, check_same_thread=False, timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def migrate(con: sqlite3.Connection) -> int:
    current = con.execute("PRAGMA user_version").fetchone()[0]
    files = sorted(paths.MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    for f in files:
        n = int(f.name[:4])
        if n <= current:
            continue
        con.executescript("BEGIN;\n" + f.read_text(encoding="utf-8") + f"\nPRAGMA user_version={n};\nCOMMIT;")
        current = n
    return current


def open_db(path: Path | None = None) -> sqlite3.Connection:
    con = connect(path)
    migrate(con)
    return con


def get_state(con: sqlite3.Connection, key: str, default=None):
    row = con.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_state(con: sqlite3.Connection, key: str, value) -> None:
    con.execute(
        "INSERT INTO app_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )
