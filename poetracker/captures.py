"""Copied maps: parse the text PoE puts on the clipboard (Ctrl+C on an item)
and link each copied map to the run you open next.

Map text is split into sections by a line of 8 dashes. We keep every
"Name: +N%" property generically (Item Quantity, Monster Pack Size, More
Scarabs, ...) so new properties in future leagues work without changes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone

from . import db
from .config import Config

log = logging.getLogger(__name__)

SEP = "--------"
PROP_RE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z ']+): \+?(?P<value>-?\d+)%?(?: \((?:augmented|unmet)\))?$")
TIER_RE = re.compile(r"^Map Tier: (?P<tier>\d+)")
BASE_TIER_RE = re.compile(r"\(Tier (?P<tier>\d+)\)")          # 3.29+: base type "Map (Tier 16)"
RANGE_RE = re.compile(r"\((-?[\d.]+)--?(-?[\d.]+)\)")         # "23(22-25)%" from Ctrl+Alt+C copies
GENERIC_BASE_RE = re.compile(r"^Map \(Tier \d+\)$")
NOT_PROPS = {"Item Level", "Monster Level", "Area Level", "Map Tier", "Quality", "Level"}
SKIP_LINES = re.compile(
    r"^(Item Level|Monster Level|Map Tier|Atlas Region|Requirements|Level|Quality|Travel to |"
    r"Maps can only|Can be used in|Note:|Area Level|Wings Revealed|Escape routes)"
)


def is_map_text(text: str) -> bool:
    return text.startswith("Item Class: Maps") or ("\nMap Tier: " in text and text.startswith("Item Class:"))


def parse_map_text(text: str) -> dict | None:
    text = text.replace("\r\n", "\n").strip()
    if not is_map_text(text):
        return None
    sections = [[l.strip() for l in s.strip().split("\n") if l.strip()] for s in text.split(SEP)]
    header = sections[0]
    rarity = next((l.split(": ", 1)[1] for l in header if l.startswith("Rarity: ")), None)
    names = [l for l in header if not l.startswith(("Item Class:", "Rarity:"))]
    name = names[0] if names else None
    base = names[-1] if names else None
    props: dict[str, int] = {}
    tier = None
    mods: list[str] = []
    flags = set()
    group: list[str] | None = None   # lines of one modifier (Ctrl+Alt+C copies have "{ Prefix Modifier ... }" headers)

    def flush():
        nonlocal group
        if group:
            mods.append(" / ".join(group))
        group = None

    for sec in sections[1:]:
        flush()
        is_prop_section = any(TIER_RE.match(l) or PROP_RE.match(l) for l in sec) and not any(
            l.startswith("{") for l in sec
        )
        for l in sec:
            t = TIER_RE.match(l)
            if t:
                tier = int(t["tier"])
                continue
            if l in ("Corrupted", "Unidentified", "Mirrored", "Split"):
                flags.add(l)
                continue
            if is_prop_section:
                p = PROP_RE.match(l)
                if p and p["name"] not in NOT_PROPS:
                    props[p["name"]] = int(p["value"])
                continue
            if l.startswith("{"):
                flush()
                group = [] if "Modifier" in l else None
                continue
            if SKIP_LINES.match(l):
                continue
            if l.startswith("(") and l.endswith(")"):
                continue  # reminder text, e.g. "(Ignite deals Fire Damage over time...)"
            if len(sec) == 1 and l.endswith("."):
                continue  # flavour / help text
            l = re.sub(r" \((?:implicit|enchant|crafted|fractured)\)$", "", l)
            l = re.sub(r"\s+—\s+Unscalable Value$", "", l)
            l = RANGE_RE.sub("", l)
            if group is not None:
                group.append(l)
            else:
                mods.append(l)
    flush()
    if tier is None and base:
        bt = BASE_TIER_RE.search(base)
        if bt:
            tier = int(bt["tier"])
    return {
        "rarity": rarity, "name": name, "base": base, "tier": tier,
        "quantity": props.get("Item Quantity"), "item_rarity": props.get("Item Rarity"),
        "pack_size": props.get("Monster Pack Size"), "properties": props, "mods": mods,
        "corrupted": "Corrupted" in flags, "identified": "Unidentified" not in flags,
    }


def save_capture(con: sqlite3.Connection, text: str, when: datetime | None = None) -> int | None:
    parsed = parse_map_text(text)
    if parsed is None:
        return None
    when = when or datetime.now(timezone.utc)
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()
    # Copying the same map twice within a minute counts once.
    recent = con.execute(
        "SELECT id FROM map_capture WHERE raw_hash=? AND ts_utc>=?", (h, db.iso(when - timedelta(minutes=1)))
    ).fetchone()
    if recent:
        return recent[0]
    cur = con.execute(
        "INSERT INTO map_capture(ts_utc, raw_hash, raw_text, rarity, name, base, tier, quantity, item_rarity,"
        " pack_size, properties, mods, corrupted, identified) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (db.iso(when), h, text, parsed["rarity"], parsed["name"], parsed["base"], parsed["tier"],
         parsed["quantity"], parsed["item_rarity"], parsed["pack_size"], json.dumps(parsed["properties"]),
         json.dumps(parsed["mods"]), int(parsed["corrupted"]), int(parsed["identified"])),
    )
    con.commit()
    return cur.lastrowid


def _matches(run_name: str | None, run_tier: int | None, cap: sqlite3.Row) -> bool:
    """A copied map fits a run if its name/base mentions the map, or if it's a
    3.29-style generic map ("Map (Tier 16)") of the same or higher tier."""
    base = cap["base"] or ""
    if GENERIC_BASE_RE.match(base):
        return run_tier is None or cap["tier"] is None or run_tier <= cap["tier"]
    if not run_name:
        return True
    hay = f"{cap['name'] or ''} {base}"
    return run_name.lower() in hay.lower()


def link_pending(con: sqlite3.Connection, config: Config) -> int:
    """Give each map run the most recent unused copied map from the minutes before it.
    (You copy a map, then open it; with several copies, each opened map takes the
    latest one that fits.)"""
    minutes = int(config.settings.get("capture_link_minutes", 10))
    first = con.execute("SELECT MIN(ts_utc) FROM map_capture WHERE run_id IS NULL").fetchone()[0]
    if not first:
        con.commit()      # relink_all's UPDATE may have opened a write; never leave the database locked
        return 0
    linked = 0
    runs = con.execute(
        "SELECT id, area_name, tier, start_utc FROM run WHERE kind IN ('map','boss') AND start_utc>=? "
        "AND id NOT IN (SELECT run_id FROM map_capture WHERE run_id IS NOT NULL) ORDER BY start_utc", (first,)
    ).fetchall()
    for r in runs:
        t = datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00"))
        caps = con.execute(
            "SELECT * FROM map_capture WHERE run_id IS NULL AND ts_utc<=? AND ts_utc>=? ORDER BY ts_utc DESC",
            (db.iso(t + timedelta(seconds=5)), db.iso(t - timedelta(minutes=minutes))),
        ).fetchall()
        for cap in caps:
            if _matches(r["area_name"], r["tier"], cap):
                con.execute("UPDATE map_capture SET run_id=? WHERE id=?", (r["id"], cap["id"]))
                linked += 1
                break
    con.commit()
    return linked


def reparse_all(con: sqlite3.Connection) -> int:
    """Re-read every saved copy with the current parser (after parser fixes)."""
    n = 0
    for row in con.execute("SELECT id, raw_text FROM map_capture").fetchall():
        p = parse_map_text(row["raw_text"])
        if not p:
            continue
        con.execute(
            "UPDATE map_capture SET rarity=?, name=?, base=?, tier=?, quantity=?, item_rarity=?, pack_size=?,"
            " properties=?, mods=?, corrupted=?, identified=? WHERE id=?",
            (p["rarity"], p["name"], p["base"], p["tier"], p["quantity"], p["item_rarity"], p["pack_size"],
             json.dumps(p["properties"]), json.dumps(p["mods"]), int(p["corrupted"]), int(p["identified"]), row["id"]))
        n += 1
    con.commit()
    return n


def relink_all(con: sqlite3.Connection, config: Config) -> int:
    con.execute("UPDATE map_capture SET run_id=NULL")
    return link_pending(con, config)


# ---- clipboard watcher (Windows) ---------------------------------------

class ClipboardWatcher(threading.Thread):
    """Polls the Windows clipboard; saves any copied map."""

    CF_UNICODETEXT = 13

    def __init__(self, db_factory, config: Config, stop: threading.Event, interval: float = 0.4):
        super().__init__(daemon=True, name="clipboard")
        self.db_factory = db_factory
        self.config = config
        self.stop = stop
        self.interval = interval
        self.captured = 0

    def _read(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        if not user32.IsClipboardFormatAvailable(self.CF_UNICODETEXT):
            return None
        if not user32.OpenClipboard(None):
            return None
        try:
            h = user32.GetClipboardData(self.CF_UNICODETEXT)
            if not h:
                return None
            p = kernel32.GlobalLock(h)
            if not p:
                return None
            try:
                return ctypes.wstring_at(p)
            finally:
                kernel32.GlobalUnlock(h)
        finally:
            user32.CloseClipboard()

    def run(self) -> None:
        if sys.platform != "win32":
            log.info("clipboard capture only works on Windows")
            return
        import ctypes

        seq_fn = ctypes.windll.user32.GetClipboardSequenceNumber
        last = seq_fn()
        con = self.db_factory()
        while not self.stop.is_set():
            try:
                seq = seq_fn()
                if seq != last:
                    last = seq
                    text = self._read()
                    if text and is_map_text(text) and save_capture(con, text):
                        self.captured += 1
                        link_pending(con, self.config)
            except Exception:
                log.exception("clipboard read failed")
            self.stop.wait(self.interval)
