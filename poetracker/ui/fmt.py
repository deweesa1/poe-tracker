"""Formatting numbers, durations and times for display."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")


def set_tz(name: str) -> None:
    global TZ
    TZ = ZoneInfo(name)


def dur(s, short: bool = False) -> str:
    if s is None:
        return "–"
    s = int(round(s))
    if s < 60:
        return f"{s}s"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h >= 100:
        return f"{h}h"
    if h:
        return f"{h}h {m}m" if short else f"{h}h {m:02d}m"
    return f"{m}m" if short or m >= 10 else f"{m}m {sec:02d}s"


def clock(s) -> str:
    """Speedrun-style timer: 1:38:33."""
    if s is None:
        return "–"
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def hours(s) -> str:
    return "–" if s is None else f"{s / 3600:,.1f} h"


def num(v, d: int = 0) -> str:
    if v is None:
        return "–"
    return f"{v:,.{d}f}"


def pct(v, d: int = 0) -> str:
    return "–" if v is None else f"{v * 100:.{d}f}%"


def signed_pct(v) -> str:
    return "–" if v is None else f"{'+' if v >= 0 else '−'}{abs(v) * 100:.0f}%"


def _dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)


def when(iso: str | None, with_date: bool = True) -> str:
    d = _dt(iso)
    if not d:
        return "–"
    return d.strftime("%b %d, %H:%M") if with_date else d.strftime("%H:%M")


def date(iso: str | None) -> str:
    d = _dt(iso)
    return d.strftime("%b %d, %Y") if d else "–"


def day_label(day: str) -> str:
    return datetime.strptime(day, "%Y-%m-%d").strftime("%b %d")


def ago(iso: str | None) -> str:
    d = _dt(iso)
    if not d:
        return "never"
    s = (datetime.now(timezone.utc) - d).total_seconds()
    if s < 90:
        return "just now"
    if s < 3600:
        return f"{round(s / 60)} min ago"
    if s < 2 * 86400:
        return f"{round(s / 3600)} h ago"
    return f"{round(s / 86400)} days ago"


def tier(t) -> str:
    if t is None:
        return "–"
    return "Nightmare" if t >= 17 else f"T{t}"


def by_fmt(v, kind: str) -> str:
    return {
        "hours": lambda: num(v, 1) + " h" if v is not None else "–",
        "int": lambda: num(v),
        "num1": lambda: num(v, 1),
        "num2": lambda: num(v, 2),
        "pct": lambda: pct(v),
        "dur": lambda: dur(v, short=True),
        "tier": lambda: tier(v),
    }.get(kind, lambda: str(v))()
