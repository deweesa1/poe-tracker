"""The pipeline: raw lines in, silver rows out.

    Client.txt --tailer--> raw line --LineParser--> Event --detectors--> SQLite

Detectors are small functions registered with @on("<event kind>") in the
poetracker.detectors package. They share one Context, which holds the
database connection and the "where are we now" state (current session,
login, character, area visit and run). That state is saved together with
the file offset in the same transaction, so stopping the app at any moment
and starting it again carries on exactly where it left off.
"""
from __future__ import annotations

import hashlib
import importlib
import pkgutil
import sqlite3
from collections import defaultdict
from typing import Callable

from . import db
from .areas import AreaClassifier
from .config import Config
from .logline import Event, LineParser

Handler = Callable[["Context", Event], None]
_HANDLERS: dict[str, list[Handler]] = defaultdict(list)


def on(*kinds: str):
    """Register a detector for one or more event kinds."""
    def deco(fn: Handler) -> Handler:
        for k in kinds:
            _HANDLERS[k].append(fn)
        return fn
    return deco


def load_detectors() -> None:
    from . import detectors
    for mod in sorted(pkgutil.iter_modules(detectors.__path__), key=lambda m: m.name):
        importlib.import_module(f"{detectors.__name__}.{mod.name}")


def fresh_state() -> dict:
    return {
        "session_id": None, "pid": None, "last_ts": None,
        "login_id": None, "char_id": None, "char_source": None, "login_names": {}, "login_prev_char": None,
        "last_known_char": None, "login_visits": 0, "char_acts": {},
        "visit_id": None, "visit_run": None, "visit_kind": None,
        "run_id": None, "run_area": None, "run_seed": None, "run_last_end": None,
        "afk_id": None,
        "atlas": {},          # league -> sorted list of allocated atlas node ids
    }


class Context:
    def __init__(self, con: sqlite3.Connection, config: Config, source: str):
        self.con = con
        self.config = config
        self.source = source
        self.classifier = AreaClassifier(config.area_rules, config.side_mechanics)
        self.state: dict = fresh_state()
        self._char_cache: dict[int, dict] = {}

    # ---- small helpers used by detectors -------------------------------
    def insert(self, table: str, row: dict, ev: Event | None = None) -> int | None:
        if ev is not None:
            row = {"source": self.source, "source_offset": ev.offset, **row}
        cols = ", ".join(row)
        qs = ", ".join("?" for _ in row)
        cur = self.con.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({qs})", tuple(row.values()))
        if cur.rowcount == 0 and ev is not None:
            r = self.con.execute(
                f"SELECT id FROM {table} WHERE source=? AND source_offset=?", (self.source, ev.offset)
            ).fetchone()
            return r[0] if r else None
        return cur.lastrowid

    def update(self, table: str, row_id: int | None, **values) -> None:
        if row_id is None or not values:
            return
        sets = ", ".join(f"{k}=?" for k in values)
        self.con.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*values.values(), row_id))

    def league_id(self, name: str) -> int:
        row = self.con.execute("SELECT id FROM league WHERE name=?", (name,)).fetchone()
        if row:
            return row[0]
        lg = next((l for l in self.config.leagues if l.name == name), None)
        return self.con.execute(
            "INSERT INTO league(name, start_utc, end_utc) VALUES (?,?,?)",
            (name, db.iso(lg.start) if lg else None, db.iso(lg.end) if lg and lg.end else None),
        ).lastrowid

    def character(self, char_id: int | None) -> dict | None:
        if char_id is None:
            return None
        if char_id not in self._char_cache:
            r = self.con.execute(
                "SELECT c.*, l.name AS league FROM character c LEFT JOIN league l ON l.id=c.league_id WHERE c.id=?",
                (char_id,),
            ).fetchone()
            if r is None:
                return None
            self._char_cache[char_id] = dict(r)
        return self._char_cache[char_id]

    def find_or_create_character(self, name: str, ev: Event, cls: str | None = None,
                                 level: int | None = None) -> int:
        rows = self.con.execute(
            "SELECT id, level, league_id FROM character WHERE name=? ORDER BY first_seen DESC", (name,)
        ).fetchall()
        league = self.config.league_for(ev.ts, name)
        lid = self.league_id(league)
        for r in rows:
            # A level 1-2 character in a newer league with the same name is a
            # new character (old one deleted or left in Standard).
            if level is not None and level <= 2 and r["league_id"] != lid:
                continue
            return r["id"]
        cid = self.con.execute(
            "INSERT OR IGNORE INTO character(name, class, league_id, first_seen, last_seen, level) VALUES (?,?,?,?,?,?)",
            (name, cls, lid, db.iso(ev.ts), db.iso(ev.ts), level),
        ).lastrowid
        if not cid:
            cid = self.con.execute("SELECT id FROM character WHERE name=? AND league_id=?", (name, lid)).fetchone()[0]
        return cid

    def touch_character(self, char_id: int, ev: Event, cls: str | None = None, level: int | None = None) -> None:
        sets, vals = ["last_seen=?"], [db.iso(ev.ts)]
        if cls:
            sets.append("class=?"); vals.append(cls)
        if level is not None:
            sets.append("level=MAX(COALESCE(level,0), ?)"); vals.append(level)
        self.con.execute(f"UPDATE character SET {', '.join(sets)} WHERE id=?", (*vals, char_id))
        self._char_cache.pop(char_id, None)

    def current_league(self, ev: Event) -> str:
        ch = self.character(self.state["char_id"])
        if ch and ch.get("league"):
            return ch["league"]
        return self.config.league_for(ev.ts)

    def atlas_hash(self, league: str) -> str | None:
        nodes = self.state["atlas"].get(league)
        if not nodes:
            return None
        return hashlib.sha1(",".join(nodes).encode()).hexdigest()[:10]

    def dispatch(self, ev: Event) -> None:
        for fn in _HANDLERS.get(ev.kind, ()):
            fn(self, ev)
        self.state["last_ts"] = db.iso(ev.ts)

    def flush(self) -> None:
        """Keep the open session's end time current (called per batch)."""
        if self.state["session_id"] and self.state["last_ts"]:
            self.update("game_session", self.state["session_id"], end_utc=self.state["last_ts"])


def make_parser(config: Config) -> LineParser:
    return LineParser(config.patterns, config.npc_ignore, config.timezone)
