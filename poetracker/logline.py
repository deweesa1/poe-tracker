"""Turning one Client.txt line into an event.

A line looks like:
    2026/07/28 16:57:00 283083656 1186a8a3 [DEBUG Client 51652] Generating level 1 area "1_1_1" with seed 258499789
    date       time     ms-tick   hash     [level  Client pid ] message

The time is the PC's local time; we convert it to UTC with the configured
time zone so that daylight-saving changes don't break durations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LINE_RE = re.compile(
    r"^(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) \d+ \w+ \[(?P<lvl>\w+) Client (?P<pid>\d+)\] (?P<msg>.*)$"
)
OPENING_RE = re.compile(r"^(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) \*+ LOG FILE OPENING \*+")


@dataclass(slots=True)
class Event:
    kind: str
    ts: datetime          # UTC, timezone-aware
    local: str            # "YYYY-MM-DD HH:MM:SS" as written in the log
    pid: int
    offset: int           # byte offset of the line in its source
    data: dict = field(default_factory=dict)

    @property
    def day(self) -> str:
        return self.local[:10]


class LineParser:
    def __init__(self, patterns: dict, npc_ignore: set[str], tz_name: str):
        self.tz = ZoneInfo(tz_name)
        self.compiled = [
            (name, p.get("contains") or "", re.compile(p["regex"]))
            for name, p in patterns.items()
        ]
        self.npc_ignore = npc_ignore
        self._ts_cache: tuple[str, datetime] | None = None

    def _to_utc(self, date: str, time: str) -> tuple[datetime, str]:
        key = f"{date} {time}"
        if self._ts_cache and self._ts_cache[0] == key:
            return self._ts_cache[1], key.replace("/", "-")
        local = datetime.strptime(key, "%Y/%m/%d %H:%M:%S").replace(tzinfo=self.tz)
        utc = local.astimezone(timezone.utc)
        self._ts_cache = (key, utc)
        return utc, key.replace("/", "-")

    def quick_relevant(self, text: str) -> bool:
        """Cheap test used before the full parse (most lines are noise)."""
        if "LOG FILE OPENING" in text:
            return True
        return any(c in text for _, c, _ in self.compiled if c) and "] " in text

    def parse(self, text: str, offset: int) -> Event | None:
        text = text.rstrip("\r\n")
        m = LINE_RE.match(text)
        if not m:
            o = OPENING_RE.match(text)
            if o:
                ts, local = self._to_utc(o["date"], o["time"])
                return Event("log_opening", ts, local, 0, offset)
            return None
        msg = m["msg"]
        for name, contains, rx in self.compiled:
            if contains and contains not in msg:
                continue
            mm = rx.match(msg)
            if not mm:
                continue
            data = {k: v for k, v in mm.groupdict().items() if v is not None}
            if name == "npc":
                if m["lvl"] != "INFO" or data["speaker"] in self.npc_ignore:
                    return None
            ts, local = self._to_utc(m["date"], m["time"])
            return Event(name, ts, local, int(m["pid"]), offset, data)
        return None
