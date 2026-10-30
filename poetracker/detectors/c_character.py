"""Who is playing: level-ups and deaths name the character.

Party members' level-ups and deaths appear in the log too, so each login
keeps a score per name (level-up 3 points, death 1 point) and the leading
name is taken as the player. Whenever the leader changes, every row
recorded so far in that login (visits, runs, passive changes) is
re-attributed. Until a login names anyone, the previous login's character
is assumed.
"""
from __future__ import annotations

from .. import db
from ..pipeline import Context, on
from ..logline import Event

WEIGHTS = {"level_up": 3, "death": 1}


def identify(ctx: Context, name: str, ev: Event, cls: str | None = None, level: int | None = None) -> int:
    st = ctx.state
    names = st.setdefault("login_names", {})
    names[name] = names.get(name, 0) + WEIGHTS.get(ev.kind, 1)
    cid = ctx.find_or_create_character(name, ev, cls, level)
    ch = ctx.character(cid)
    if ch and ch.get("other"):
        names.pop(name, None)
        return cid
    leader = max(names, key=names.get)
    if leader == name and (st["char_id"] != cid or st["char_source"] != "log"):
        if st["login_id"] is not None:
            for table in ("area_visit", "run", "passive_change"):
                ctx.con.execute(f"UPDATE {table} SET character_id=? WHERE login_id=?", (cid, st["login_id"]))
            ctx.update("login", st["login_id"], character_id=cid, char_source="log")
        st["char_id"], st["char_source"] = cid, "log"
        st["last_known_char"] = cid
    ctx.touch_character(cid, ev, cls, level)
    return cid


@on("level_up")
def level_up(ctx: Context, ev: Event) -> None:
    level = int(ev.data["level"])
    cid = identify(ctx, ev.data["character"], ev, ev.data.get("class"), level)
    own = cid == ctx.state["char_id"]
    ctx.insert(
        "level_up",
        {"character_id": cid, "class": ev.data.get("class"), "level": level, "ts_utc": db.iso(ev.ts),
         "visit_id": ctx.state["visit_id"] if own else None},
        ev,
    )


@on("death")
def death(ctx: Context, ev: Event) -> None:
    cid = identify(ctx, ev.data["character"], ev)
    own = cid == ctx.state["char_id"]
    ctx.insert(
        "death",
        {"character_id": cid, "ts_utc": db.iso(ev.ts), "visit_id": ctx.state["visit_id"] if own else None,
         "run_id": ctx.state["visit_run"] if own else None},
        ev,
    )


@on("area_presence")
def area_presence(ctx: Context, ev: Event) -> None:
    """Someone joined or left your area, so that name is another player."""
    name = ev.data["character"]
    st = ctx.state
    rows = ctx.con.execute("SELECT id FROM character WHERE name=?", (name,)).fetchall()
    own = ctx.character(st["char_id"])
    if own and own["name"] == name:
        # We had taken this player for you in this login: undo that.
        st.get("login_names", {}).pop(name, None)
        names = st.get("login_names") or {}
        if names:
            leader = max(names, key=names.get)
            back = ctx.find_or_create_character(leader, ev)
        else:
            back = st.get("login_prev_char")
        if st["login_id"] is not None:
            for table in ("area_visit", "run", "passive_change"):
                ctx.con.execute(f"UPDATE {table} SET character_id=? WHERE login_id=?", (back, st["login_id"]))
            ctx.update("login", st["login_id"], character_id=back, char_source="log" if names else "inferred")
        st["char_id"], st["char_source"] = back, ("log" if names else "inferred")
        st["last_known_char"] = back
    if rows:
        ctx.con.execute("UPDATE character SET other=1 WHERE name=?", (name,))
        for r in rows:
            ctx._char_cache.pop(r[0], None)
    else:
        cid = ctx.find_or_create_character(name, ev)
        ctx.con.execute("UPDATE character SET other=1 WHERE id=?", (cid,))
        ctx._char_cache.pop(cid, None)
    st.get("login_names", {}).pop(name, None)
