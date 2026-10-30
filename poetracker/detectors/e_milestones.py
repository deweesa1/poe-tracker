"""Boss kills for the milestone / Voidstone tracker (milestones.yaml)."""
from __future__ import annotations

import re

from .. import db
from ..pipeline import Context, on
from ..logline import Event

_cache: dict = {}


def _kill_lines(ctx: Context) -> dict:
    key = id(ctx.config)
    if key not in _cache:
        table = {}
        for boss, spec in (ctx.config.milestones.get("bosses") or {}).items():
            for line in spec.get("kill_lines") or []:
                # several bosses can share a line (Izaro in every Labyrinth); the area decides
                table.setdefault((spec.get("speaker", boss), line.strip()), []).append((boss, re.compile(spec["area"])))
        _cache.clear()
        _cache[key] = table
    return _cache[key]


@on("npc")
def boss_defeat_line(ctx: Context, ev: Event) -> None:
    hits = _kill_lines(ctx).get((ev.data["speaker"], ev.data["text"].strip()))
    if not hits:
        return
    st = ctx.state
    row = ctx.con.execute("SELECT area_id FROM area_visit WHERE id=?", (st["visit_id"],)).fetchone() if st["visit_id"] else None
    if not row:
        return
    boss = next((b for b, rx in hits if rx.search(row[0])), None)
    if not boss:
        return
    ctx.insert("boss_kill", {"boss": boss, "character_id": st["char_id"], "run_id": st["visit_run"],
                             "visit_id": st["visit_id"], "ts_utc": db.iso(ev.ts)}, ev)
