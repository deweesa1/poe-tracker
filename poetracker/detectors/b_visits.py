"""Area visits and runs.

Every area load writes a "Generating level N area <id> with seed S" line,
including portal re-entries. A map instance is (area id, seed): going back
into the same map through a portal keeps the same seed, so it stays one run.

Rules for a non-town area:
  * same (area id, seed) as the open run       -> same run
  * entered from inside the open run, and it is a side area / unknown
    high-level area (Vaal side area, league encounter) -> joins that run
  * otherwise                                   -> the open run ends, a new run starts
Towns and hideouts keep the open run going; a campaign zone ends it.
"""
from __future__ import annotations

from .. import db
from ..areas import map_tier
from ..pipeline import Context, on
from ..logline import Event

RUN_KINDS = {"map", "boss", "activity", "side", "other"}


def close_visit(ctx: Context, end_iso: str | None) -> None:
    st = ctx.state
    if st["visit_id"] is None:
        return
    ctx.update("area_visit", st["visit_id"], end_utc=end_iso)
    if st["visit_run"] is not None:
        st["run_last_end"] = end_iso
    st["visit_id"] = st["visit_run"] = st["visit_kind"] = None


def close_run(ctx: Context) -> None:
    st = ctx.state
    if st["run_id"] is None:
        return
    ctx.update("run", st["run_id"], end_utc=st["run_last_end"])
    st["run_id"] = st["run_area"] = st["run_seed"] = st["run_last_end"] = None


def close_everything(ctx: Context, end_iso: str | None) -> None:
    close_visit(ctx, end_iso)
    close_run(ctx)
    if ctx.state["afk_id"] is not None:
        ctx.update("afk_period", ctx.state["afk_id"], end_utc=end_iso)
        ctx.state["afk_id"] = None


@on("generating")
def generating(ctx: Context, ev: Event) -> None:
    from .a_sessions import ensure_session, start_login

    ensure_session(ctx, ev)
    st = ctx.state
    if st["login_id"] is None:
        start_login(ctx, ev)

    area_id = ev.data["area_id"]
    level = int(ev.data["level"])
    seed = int(ev.data["seed"])
    info = ctx.classifier.classify(area_id, level)
    now = db.iso(ev.ts)

    check_inferred_character(ctx, info)
    prev_run_of_visit = st["visit_run"]
    close_visit(ctx, now)

    run_id = None
    if info.kind == "campaign":
        close_run(ctx)
    elif info.kind in RUN_KINDS:
        same_instance = st["run_id"] is not None and st["run_area"] == area_id and st["run_seed"] == seed
        from_inside = st["run_id"] is not None and prev_run_of_visit == st["run_id"]
        if same_instance:
            run_id = st["run_id"]
        elif from_inside and info.kind in ("side", "other"):
            run_id = st["run_id"]
        elif from_inside and info.kind == "activity" and info.activity == st.get("run_activity"):
            run_id = st["run_id"]   # next room of the Labyrinth / Heist / Sanctum
        else:
            close_run(ctx)
            kind = "other" if info.kind == "side" else info.kind
            league = ctx.current_league(ev)
            run_id = ctx.insert(
                "run",
                {
                    "session_id": st["session_id"], "login_id": st["login_id"], "character_id": st["char_id"],
                    "kind": kind, "activity": info.activity, "area_id": area_id, "area_level": level,
                    "tier": map_tier(level) if kind == "map" else None, "seed": seed,
                    "start_utc": now, "day": ev.day, "atlas_hash": ctx.atlas_hash(league),
                },
                ev,
            )
            st["run_id"], st["run_area"], st["run_seed"] = run_id, area_id, seed
            st["run_activity"] = info.activity

    st["visit_id"] = ctx.insert(
        "area_visit",
        {
            "session_id": st["session_id"], "login_id": st["login_id"], "character_id": st["char_id"],
            "run_id": run_id, "area_id": area_id, "area_level": level, "seed": seed, "kind": info.kind,
            "act": info.act, "start_utc": now, "day": ev.day,
        },
        ev,
    )
    st["visit_run"] = run_id
    st["visit_kind"] = info.kind
    st["login_visits"] = st.get("login_visits", 0) + 1
    if st["char_id"] is not None and info.act is not None and info.kind in ("campaign", "town"):
        acts = st.setdefault("char_acts", {})
        key = str(st["char_id"])
        acts[key] = max(acts.get(key, 0), info.act)


def check_inferred_character(ctx: Context, info) -> None:
    """A login we assumed is the previous character, but whose first area
    doesn't fit that character's campaign progress, is someone else
    (e.g. a quick switch to an alt). Mark it unknown instead."""
    st = ctx.state
    if st.get("login_visits", 0) != 0 or st["char_source"] != "inferred" or st["char_id"] is None:
        return
    if info.act is None or info.kind not in ("campaign", "town"):
        return
    prev_act = st.get("char_acts", {}).get(str(st["char_id"]))
    if not prev_act or prev_act >= 11:
        return
    if info.act > prev_act + 1 or info.act < prev_act - 1:
        st["char_id"], st["char_source"] = None, "unknown"
        ctx.update("login", st["login_id"], character_id=None, char_source="unknown")


@on("entered")
def entered(ctx: Context, ev: Event) -> None:
    st = ctx.state
    if st["visit_id"] is None:
        return
    name = ev.data["area_name"]
    ctx.update("area_visit", st["visit_id"], area_name=name)
    if st["run_id"] is not None and st["visit_run"] == st["run_id"]:
        ctx.con.execute(
            "UPDATE run SET area_name=? WHERE id=? AND area_name IS NULL AND area_id=?",
            (name, st["run_id"], st["run_area"]),
        )
