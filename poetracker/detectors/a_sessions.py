"""Game sessions and logins.

A session starts at "***** LOG FILE OPENING *****" (the game was launched)
and ends at "Closing game" or the last line before the next launch.
A login starts at "Async connecting to <server>login..." (character select).
"""
from __future__ import annotations

from .. import db
from ..pipeline import Context, on
from ..logline import Event
from .b_visits import close_everything


def end_session(ctx: Context, end_iso: str | None) -> None:
    st = ctx.state
    if st["session_id"] is None:
        return
    end_iso = end_iso or st["last_ts"]
    close_everything(ctx, end_iso)
    ctx.update("game_session", st["session_id"], end_utc=end_iso)
    st["session_id"] = None
    st["login_id"] = None


def start_session(ctx: Context, ev: Event) -> None:
    sid = ctx.insert("game_session", {"pid": ev.pid or None, "start_utc": db.iso(ev.ts), "day": ev.day}, ev)
    ctx.state["session_id"] = sid
    ctx.state["pid"] = ev.pid or None


@on("log_opening")
def log_opening(ctx: Context, ev: Event) -> None:
    end_session(ctx, ctx.state["last_ts"])
    start_session(ctx, ev)


@on("game_closing")
def game_closing(ctx: Context, ev: Event) -> None:
    end_session(ctx, db.iso(ev.ts))


def ensure_session(ctx: Context, ev: Event) -> None:
    """Lines can arrive without an opening line (e.g. the log was trimmed)."""
    st = ctx.state
    if st["session_id"] is None or (ev.pid and st["pid"] and ev.pid != st["pid"]):
        end_session(ctx, st["last_ts"])
        start_session(ctx, ev)


def start_login(ctx: Context, ev: Event) -> None:
    st = ctx.state
    # Until this login names a character, assume the last known one.
    char_id = st.get("last_known_char") or st["char_id"]
    src = "inferred" if char_id else None
    st["login_id"] = ctx.insert(
        "login",
        {"session_id": st["session_id"], "start_utc": db.iso(ev.ts), "character_id": char_id, "char_source": src},
        ev,
    )
    st["char_id"], st["char_source"] = char_id, src
    st["login_names"] = {}
    st["login_prev_char"] = char_id
    st["login_visits"] = 0


@on("login")
def login(ctx: Context, ev: Event) -> None:
    ensure_session(ctx, ev)
    start_login(ctx, ev)
