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
        table, patterns = {}, {}
        for boss, spec in (ctx.config.milestones.get("bosses") or {}).items():
            area = re.compile(spec["area"])
            speaker = spec.get("speaker", boss)
            for line in spec.get("kill_lines") or []:
                # several bosses can share a line (Izaro in every Labyrinth); the area decides
                table.setdefault((speaker, line.strip()), []).append((boss, area))
            for rx in spec.get("kill_regex") or []:
                patterns.setdefault(speaker, []).append((re.compile(rx), boss, area))
        _cache.clear()
        _cache[key] = (table, patterns)
    return _cache[key]


@on("npc")
def boss_defeat_line(ctx: Context, ev: Event) -> None:
    table, patterns = _kill_lines(ctx)
    text = ev.data["text"].strip()
    hits = table.get((ev.data["speaker"], text)) or \
        [(boss, area) for rx, boss, area in patterns.get(ev.data["speaker"], []) if rx.search(text)]
    if not hits:
        return
    st = ctx.state
    row = ctx.con.execute("SELECT area_id FROM area_visit WHERE id=?", (st["visit_id"],)).fetchone() if st["visit_id"] else None
    if not row:
        return
    boss = next((b for b, rx in hits if rx.search(row[0])), None)
    if not boss:
        return
    # one kill per visit (the Maven can say several "you won" lines in one Crucible)
    if ctx.con.execute("SELECT 1 FROM boss_kill WHERE boss=? AND visit_id=?", (boss, st["visit_id"])).fetchone():
        return
    ctx.insert("boss_kill", {"boss": boss, "character_id": st["char_id"], "run_id": st["visit_run"],
                             "visit_id": st["visit_id"], "ts_utc": db.iso(ev.ts)}, ev)
