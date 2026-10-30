"""Reading Client.txt incrementally (bronze) and feeding the pipeline (silver).

Client.txt only ever grows while the game writes to it. We remember the
byte offset we stopped at; next time we read from there. If the file got
smaller, or its first bytes changed, it was deleted or reset: that starts a
new "generation" (source "log:2", "log:3"...) read from the beginning, so
offsets from the old file never clash with the new one.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path

from . import db
from .config import Config
from .pipeline import Context, fresh_state, load_detectors, make_parser

log = logging.getLogger(__name__)

BATCH_LINES = 20000
CHUNK = 8 * 1024 * 1024
HEAD_BYTES = 256

SILVER_TABLES = (
    "run_speaker", "boss_kill", "quest_point", "quest_report", "bandit_reward", "level_up", "death", "passive_change", "afk_period",
    "whisper", "trade_result", "area_visit", "run", "login", "game_session", "character", "league",
)


def _head_hash(path: Path, n: int = HEAD_BYTES) -> str:
    with open(path, "rb") as f:
        return hashlib.sha1(f.read(n)).hexdigest()


# state key -> table its id lives in
_STATE_REFS = {"session_id": "game_session", "login_id": "login", "char_id": "character",
               "last_known_char": "character", "login_prev_char": "character", "visit_id": "area_visit",
               "visit_run": "run", "run_id": "run", "afk_id": "afk_period"}


def _drop_dangling(con: sqlite3.Connection, state: dict) -> None:
    """Forget ids in the saved reading state that no longer exist (e.g. after
    the tables were rebuilt underneath it); inserting them would fail."""
    for key, table in _STATE_REFS.items():
        v = state.get(key)
        if v is not None and not con.execute(f"SELECT 1 FROM {table} WHERE id=?", (v,)).fetchone():
            state[key] = None


class Ingestor:
    def __init__(self, con: sqlite3.Connection, config: Config, log_path: Path):
        load_detectors()
        self.con = con
        self.config = config
        self.log_path = Path(log_path)
        self.parser = make_parser(config)
        self.lines_seen = 0
        self.events_seen = 0

    # -- file position -------------------------------------------------
    def _position(self) -> tuple[str, int]:
        gen = db.get_state(self.con, "log_generation", 1)
        offset = db.get_state(self.con, "log_offset", 0)
        head = db.get_state(self.con, "log_head", None)   # [length, sha1 of first bytes]
        size = os.path.getsize(self.log_path)
        changed = bool(head) and isinstance(head, list) and _head_hash(self.log_path, head[0]) != head[1]
        if offset and (size < offset or changed):
            log.warning("Client.txt was reset (size %s < offset %s or header changed); new generation", size, offset)
            gen, offset = gen + 1, 0
            db.set_state(self.con, "log_generation", gen)
            db.set_state(self.con, "log_offset", 0)
            self.con.commit()
        return f"log:{gen}", offset

    def _context(self, source: str) -> Context:
        ctx = Context(self.con, self.config, source)
        saved = db.get_state(self.con, "pipeline_state")
        if saved:
            ctx.state.update(saved)
            _drop_dangling(self.con, ctx.state)
        return ctx

    def _commit(self, ctx: Context, offset: int | None) -> None:
        ctx.flush()
        db.set_state(self.con, "pipeline_state", ctx.state)
        if offset is not None:
            db.set_state(self.con, "log_offset", offset)
        self.con.commit()

    # -- main loop -----------------------------------------------------
    def run_once(self, progress=None) -> int:
        """Read everything new in Client.txt. Returns number of events."""
        if not self.log_path.exists():
            return 0
        source, offset = self._position()
        head = db.get_state(self.con, "log_head", None)
        if offset == 0 or not head or head[0] < HEAD_BYTES:
            n = min(HEAD_BYTES, os.path.getsize(self.log_path))
            db.set_state(self.con, "log_head", [n, _head_hash(self.log_path, n)])
        ctx = self._context(source)
        events = 0
        pending = 0
        size = os.path.getsize(self.log_path)
        with open(self.log_path, "rb") as f:
            f.seek(offset)
            buf = b""
            pos = offset          # file position of buf[0]
            while True:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                buf += chunk
                start = 0
                while True:
                    nl = buf.find(b"\n", start)
                    if nl < 0:
                        break
                    line_off = pos + start
                    raw = buf[start:nl + 1]
                    start = nl + 1
                    self.lines_seen += 1
                    text = raw.decode("utf-8", errors="replace").replace("\x00", "")
                    ev = self.parser.parse(text, line_off)
                    if ev is None:
                        continue
                    self.con.execute(
                        "INSERT OR IGNORE INTO bronze_log_line(source, source_offset, text) VALUES (?,?,?)",
                        (source, line_off, text.rstrip("\r\n")),
                    )
                    ctx.dispatch(ev)
                    events += 1
                    pending += 1
                    if pending >= BATCH_LINES:
                        self._commit(ctx, pos + start)
                        pending = 0
                        if progress:
                            progress(pos + start, size)
                buf = buf[start:]
                pos += start
            # A partial last line (game mid-write) stays unread until next time.
            self._commit(ctx, pos)
        self.events_seen += events
        return events

    def follow(self, stop, interval: float = 2.0) -> None:
        while not stop.is_set():
            try:
                self.run_once()
            except Exception:  # keep the watcher alive; errors go to the app log
                log.exception("ingest failed")
            stop.wait(interval)


def rebuild(con: sqlite3.Connection, config: Config, log_path: Path | None, from_log: bool = False,
            progress=None) -> int:
    """Wipe the silver tables and rebuild them.

    from_log=False replays the bronze table (fast, keeps history even if
    Client.txt was deleted). from_log=True re-reads Client.txt from the
    start, which also picks up lines that new patterns now recognise.
    Map captures and currency snapshots are kept; captures are re-linked.
    """
    load_detectors()
    con.execute("UPDATE map_capture SET run_id=NULL")
    for t in SILVER_TABLES:
        try:
            con.execute(f"DELETE FROM {t}")
        except sqlite3.OperationalError:
            pass
    db.set_state(con, "pipeline_state", fresh_state())
    con.commit()
    if from_log:
        con.execute("DELETE FROM bronze_log_line")
        con.execute("DELETE FROM app_state WHERE key='log_head'")
        db.set_state(con, "log_generation", 1)
        db.set_state(con, "log_offset", 0)
        con.commit()
        n = Ingestor(con, config, log_path).run_once(progress)
    else:
        parser = make_parser(config)
        n = 0
        ctx = Context(con, config, "log:1")
        rows = con.execute("SELECT source, source_offset, text FROM bronze_log_line ORDER BY source, source_offset")
        for source, off, text in rows.fetchall():
            ctx.source = source
            ev = parser.parse(text, off)
            if ev is None:
                continue
            ctx.dispatch(ev)
            n += 1
        ctx.flush()
        db.set_state(con, "pipeline_state", ctx.state)
        con.commit()
    from .captures import relink_all
    relink_all(con, config)
    con.commit()
    return n


def wait_for_log(path: Path, stop, interval: float = 10.0) -> bool:
    while not stop.is_set():
        if path.exists():
            return True
        time.sleep(interval)
    return False
