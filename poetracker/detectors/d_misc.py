"""Passive/atlas points, AFK, NPC dialogue, whispers and trades."""
from __future__ import annotations

import re

from .. import db
from ..pipeline import Context, on
from ..logline import Event

BUY_RE = re.compile(
    r"^Hi, I would like to buy your (?P<item>.+?) listed for (?P<amount>[\d.]+) (?P<currency>.+?) in (?P<league>.+?)(?: \(| \.|\.|$)"
)
BULK_RE = re.compile(
    r"^Hi, I'd like to buy your (?P<item>.+?) for my (?P<amount>[\d.]+) (?P<currency>.+?) in (?P<league>[^.]+)\."
)
CURRENCY_ALIASES = {
    "chaos": "Chaos Orb", "chaos orb": "Chaos Orb", "divine": "Divine Orb", "divine orb": "Divine Orb",
    "exalted": "Exalted Orb", "exalted orb": "Exalted Orb", "mirror": "Mirror of Kalandra",
}


@on("passive", "mastery")
def passive(ctx: Context, ev: Event) -> None:
    if ev.kind == "mastery":
        tree, action, node = "mastery", "allocated", f'{ev.data["mastery"]}:{ev.data["effect_id"]}'
    else:
        node = ev.data["node_id"]
        tree = "atlas" if node.startswith("atlas") else "character"
        action = ev.data["action"]
    league = ctx.current_league(ev)
    ctx.insert(
        "passive_change",
        {"character_id": ctx.state["char_id"], "login_id": ctx.state["login_id"], "league": league,
         "tree": tree, "action": action, "node_id": node, "name": ev.data.get("name"), "ts_utc": db.iso(ev.ts)},
        ev,
    )
    if tree == "atlas":
        nodes = set(ctx.state["atlas"].get(league, []))
        (nodes.add if action == "allocated" else nodes.discard)(node)
        ctx.state["atlas"][league] = sorted(nodes)


@on("afk")
def afk(ctx: Context, ev: Event) -> None:
    st = ctx.state
    if ev.data["state"] == "ON":
        if st["afk_id"] is None and st["session_id"] is not None:
            st["afk_id"] = ctx.insert("afk_period", {"session_id": st["session_id"], "start_utc": db.iso(ev.ts)}, ev)
    elif st["afk_id"] is not None:
        ctx.update("afk_period", st["afk_id"], end_utc=db.iso(ev.ts))
        st["afk_id"] = None


@on("npc")
def npc(ctx: Context, ev: Event) -> None:
    run_id = ctx.state["visit_run"]
    if run_id is None:
        return
    ctx.con.execute(
        "INSERT INTO run_speaker(run_id, speaker, lines, first_utc) VALUES (?,?,1,?) "
        "ON CONFLICT(run_id, speaker) DO UPDATE SET lines=lines+1",
        (run_id, ev.data["speaker"], db.iso(ev.ts)),
    )


@on("whisper")
def whisper(ctx: Context, ev: Event) -> None:
    msg = ev.data.get("message", "")
    row = {"ts_utc": db.iso(ev.ts), "day": ev.day, "direction": ev.data["direction"],
           "who": ev.data.get("who", "").strip(), "message": msg[:500]}
    m = BUY_RE.match(msg) or BULK_RE.match(msg)
    if m:
        cur = m["currency"].strip()
        row.update(trade_kind="buy_offer", item=m["item"].strip(), price_amount=float(m["amount"]),
                   price_currency=CURRENCY_ALIASES.get(cur.lower(), cur), trade_league=m["league"].strip())
    ctx.insert("whisper", row, ev)


@on("trade_result")
def trade_result(ctx: Context, ev: Event) -> None:
    ctx.insert("trade_result", {"ts_utc": db.iso(ev.ts), "result": ev.data["result"]}, ev)


@on("quest_point")
def quest_point(ctx: Context, ev: Event) -> None:
    st = ctx.state
    row = ctx.con.execute("SELECT area_id FROM area_visit WHERE id=?", (st["visit_id"],)).fetchone() if st["visit_id"] else None
    ctx.insert("quest_point", {"character_id": st["char_id"], "visit_id": st["visit_id"],
                               "area_id": row[0] if row else None, "points": int(ev.data.get("points") or 1),
                               "ts_utc": db.iso(ev.ts)}, ev)


@on("quest_report_start")
def quest_report_start(ctx: Context, ev: Event) -> None:
    ctx.state["quest_report_utc"] = db.iso(ev.ts)


@on("quest_report")
def quest_report(ctx: Context, ev: Event) -> None:
    st = ctx.state
    if not st.get("quest_report_utc"):
        return
    ctx.insert("quest_report", {"character_id": st["char_id"], "visit_id": st["visit_id"], "report_utc": st["quest_report_utc"],
                                "quest": ev.data["quest"].strip(), "points": int(ev.data["points"])}, ev)


@on("bandit_reward")
def bandit_reward(ctx: Context, ev: Event) -> None:
    st = ctx.state
    ctx.insert("bandit_reward", {"character_id": st["char_id"], "visit_id": st["visit_id"],
                                 "reward": ev.data["reward"].strip(), "ts_utc": db.iso(ev.ts)}, ev)
