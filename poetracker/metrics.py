"""Gold layer queries: everything the dashboard shows comes from here.

Each public function takes a read connection plus filters and returns plain
dicts/lists (JSON-ready). Times are UTC ISO strings; durations are seconds.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from .config import Config

EPILOGUE_ACT = 11


def _rows(con: sqlite3.Connection, sql: str, args=()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def _ts(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _secs(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return max(0.0, (_ts(b) - _ts(a)).total_seconds())


# ---------------------------------------------------------------- filters

def own_characters(con, league: str | None = None) -> list[dict]:
    sql = """
        SELECT c.id, c.name, c.class, c.level, c.league, c.first_seen, c.last_seen,
               (SELECT COALESCE(SUM(active_s),0) FROM v_visit_active v WHERE v.character_id=c.id) AS active_s,
               (SELECT COUNT(*) FROM run r WHERE r.character_id=c.id AND r.kind='map') AS maps,
               (SELECT COUNT(*) FROM death d WHERE d.character_id=c.id) AS deaths
        FROM v_own_character c
    """
    args: tuple = ()
    if league:
        sql += " WHERE c.league=?"
        args = (league,)
    sql += " ORDER BY c.last_seen DESC"
    return _rows(con, sql, args)


def _char_filter(con, league: str | None, character_id: int | None, alias: str = "x") -> tuple[str, list]:
    """SQL fragment limiting rows (with a character_id column) to a league/character."""
    if character_id:
        return f" AND {alias}.character_id = ?", [character_id]
    if league:
        return f" AND {alias}.character_id IN (SELECT id FROM v_own_character WHERE league=?)", [league]
    return f" AND {alias}.character_id IN (SELECT id FROM v_own_character)", []


def leagues(con, config: Config) -> list[dict]:
    out = []
    names_with_chars = {r[0] for r in con.execute("SELECT DISTINCT league FROM v_own_character")}
    for lg in sorted(config.leagues, key=lambda l: l.start, reverse=True):
        if lg.name in names_with_chars:
            out.append({"name": lg.name, "start": lg.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end": lg.end.strftime("%Y-%m-%dT%H:%M:%SZ") if lg.end else None})
    for n in sorted(names_with_chars - {o["name"] for o in out}):
        out.append({"name": n, "start": None, "end": None})
    return out


# ---------------------------------------------------------------- overview

def overview(con, config: Config, league: str | None, character_id: int | None, days: int = 30) -> dict:
    f, a = _char_filter(con, league, character_id, "v")
    daily = _rows(con, f"""
        SELECT v.day, SUM(v.active_s) AS active_s,
               SUM(CASE WHEN v.kind IN ('map','side') OR (v.run_id IS NOT NULL AND v.kind NOT IN ('town','campaign')) THEN v.active_s ELSE 0 END) AS mapping_s,
               SUM(CASE WHEN v.kind='campaign' OR (v.kind='town' AND v.act IS NOT NULL AND v.act < 11) THEN v.active_s ELSE 0 END) AS campaign_s
        FROM v_visit_active v WHERE 1=1 {f}
        GROUP BY v.day ORDER BY v.day
    """, a)
    fr, ar = _char_filter(con, league, character_id, "r")
    runs_daily = {r["day"]: r["n"] for r in _rows(con, f"SELECT r.day, COUNT(*) n FROM run r WHERE r.kind='map' {fr} GROUP BY r.day", ar)}
    fd, ad = _char_filter(con, league, character_id, "d")
    deaths_daily = {r["day"]: r["n"] for r in _rows(con, f"""
        SELECT substr(v.day,1,10) day, COUNT(*) n FROM death d JOIN area_visit v ON v.id=d.visit_id WHERE 1=1 {fd} GROUP BY v.day""", ad)}
    for d in daily:
        d["maps"] = runs_daily.get(d["day"], 0)
        d["deaths"] = deaths_daily.get(d["day"], 0)
    totals = {
        "active_s": sum(d["active_s"] or 0 for d in daily),
        "mapping_s": sum(d["mapping_s"] or 0 for d in daily),
        "campaign_s": sum(d["campaign_s"] or 0 for d in daily),
        "maps": sum(runs_daily.values()),
        "deaths": sum(deaths_daily.values()),
        "days_played": len([d for d in daily if (d["active_s"] or 0) > 0]),
    }
    last_day = daily[-1]["day"] if daily else None
    today = next((d for d in daily if d["day"] == last_day), None)
    recent = runs(con, config, league, character_id, limit=30)
    chars = own_characters(con, league)
    if character_id:
        chars = [c for c in chars if c["id"] == character_id]
    return {"daily": daily[-days:] if days else daily, "all_daily": daily, "totals": totals,
            "last_day": today, "recent_runs": recent, "characters": chars}


# ---------------------------------------------------------------- runs / maps

def _mechanic_maps(config: Config):
    side = [(re.compile(k), v) for k, v in config.side_mechanics.items()]
    return config.speakers, side


def runs(con, config: Config, league: str | None, character_id: int | None, kind: str | None = "map",
         limit: int | None = 500, since: str | None = None) -> list[dict]:
    f, a = _char_filter(con, league, character_id, "r")
    where = f
    if kind:
        where += " AND r.kind = ?"
        a.append(kind)
    if since:
        where += " AND r.start_utc >= ?"
        a.append(since)
    sql = f"""
        SELECT r.id, r.kind, r.activity, r.area_id, r.area_name, r.area_level, r.tier, r.start_utc, r.end_utc, r.day,
               r.atlas_hash, c.name AS character,
               (SELECT COALESCE(SUM(v.active_s),0) FROM v_visit_active v WHERE v.run_id=r.id) AS active_s,
               (SELECT COUNT(*) FROM area_visit v WHERE v.run_id=r.id AND v.kind NOT IN ('side','other') ) AS entries,
               (SELECT COUNT(*) FROM death d WHERE d.run_id=r.id) AS deaths,
               (SELECT group_concat(v.area_id, '|') FROM area_visit v WHERE v.run_id=r.id AND v.area_id != r.area_id) AS side_ids,
               (SELECT group_concat(s.speaker, '|') FROM run_speaker s WHERE s.run_id=r.id) AS speakers,
               m.quantity, m.item_rarity, m.pack_size, m.rarity AS map_rarity, m.corrupted, m.properties, m.name AS map_name
        FROM run r
        LEFT JOIN character c ON c.id=r.character_id
        LEFT JOIN map_capture m ON m.run_id=r.id
        WHERE 1=1 {where}
        ORDER BY r.start_utc DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    out = _rows(con, sql, a)
    speakers_map, side = _mechanic_maps(config)
    for r in out:
        mech = set()
        for sp in (r.pop("speakers") or "").split("|"):
            if sp in speakers_map:
                mech.add(speakers_map[sp])
        for sid in set((r.pop("side_ids") or "").split("|")) - {""}:
            for rx, name in side:
                if rx.search(sid):
                    mech.add(name)
                    break
        r["mechanics"] = sorted(mech)
        r["wall_s"] = _secs(r["start_utc"], r["end_utc"])
        if r.get("properties"):
            r["properties"] = json.loads(r["properties"])
    return out


def maps_summary(con, config: Config, league: str | None, character_id: int | None) -> dict:
    rs = runs(con, config, league, character_id, kind="map", limit=None)
    by_tier: dict[int, list] = defaultdict(list)
    by_map: dict[str, list] = defaultdict(list)
    by_day: dict[str, list] = defaultdict(list)
    mech = Counter()
    for r in rs:
        by_tier[r["tier"] or 0].append(r)
        by_map[r["area_name"] or r["area_id"]].append(r)
        by_day[r["day"]].append(r)
        for m in r["mechanics"]:
            mech[m] += 1

    total_runs = len(rs)
    total_act = sum(r["active_s"] for r in rs)

    def agg(lst):
        act = sorted(x["active_s"] for x in lst if x["active_s"])
        t = sum(act)
        deaths = sum(x["deaths"] for x in lst)
        return {
            "runs": len(lst),
            "share": len(lst) / total_runs if total_runs else 0,
            "active_s": t,
            "avg_active_s": t / len(act) if act else 0,
            "median_active_s": act[len(act) // 2] if act else 0,
            "fastest_s": act[0] if act else None,
            "maps_per_hour": len(lst) / (t / 3600) if t > 300 else None,
            "deaths": deaths,
            "deaths_per_map": deaths / len(lst) if lst else None,
            "deathless_share": sum(1 for x in lst if not x["deaths"]) / len(lst) if lst else None,
            "avg_quantity": _avg([x["quantity"] for x in lst]),
            "avg_pack_size": _avg([x["pack_size"] for x in lst]),
            "avg_tier": _avg([x["tier"] for x in lst]),
            "first": min(x["start_utc"] for x in lst) if lst else None,
            "last": max(x["start_utc"] for x in lst) if lst else None,
        }

    tiers = [{"tier": t, **agg(v)} for t, v in sorted(by_tier.items())]
    top_maps = sorted(({"map": k, **agg(v)} for k, v in by_map.items()), key=lambda x: -x["runs"])
    days = []
    for d, lst in sorted(by_day.items()):
        act = sum(x["active_s"] for x in lst)
        days.append({"day": d, "runs": len(lst), "max_tier": max((x["tier"] or 0) for x in lst),
                     "avg_tier": _avg([x["tier"] for x in lst]), "active_s": act,
                     "deaths": sum(x["deaths"] for x in lst),
                     "maps_per_hour": len(lst) / (act / 3600) if act > 600 else None})
    return {
        "totals": {"runs": total_runs, "active_s": total_act, "deaths": sum(r["deaths"] for r in rs),
                   "maps_per_hour": total_runs / (total_act / 3600) if total_act > 600 else None,
                   "avg_active_s": total_act / total_runs if rs else 0,
                   "deaths_per_map": sum(r["deaths"] for r in rs) / total_runs if rs else None,
                   "max_tier": max((r["tier"] or 0) for r in rs) if rs else None,
                   "captured": sum(1 for r in rs if r["quantity"] is not None)},
        "tiers": tiers, "top_maps": top_maps, "days": days,
        "mechanics": [{"mechanic": k, "runs": v, "share": v / total_runs if total_runs else 0} for k, v in mech.most_common()],
        "runs": rs,
    }


def content_of(config: Config, area_id: str, fallback: str | None) -> tuple[str, str]:
    for rule in config.content_rules:
        if re.search(rule["match"], area_id):
            return rule["group"], rule["name"]
    return "Other", fallback or area_id


def other_runs(con, config, league, character_id) -> dict:
    """Non-map endgame content grouped by what it is (areas.yaml -> content)."""
    f, a = _char_filter(con, league, character_id, "r")
    rows = _rows(con, f"""
        SELECT r.id, r.area_id, r.area_name, r.start_utc,
               (SELECT COALESCE(SUM(v.active_s),0) FROM v_visit_active v WHERE v.run_id=r.id) AS active_s,
               (SELECT COUNT(*) FROM death d WHERE d.run_id=r.id) AS deaths
        FROM run r WHERE r.kind != 'map' {f}
    """, a)
    items: dict[tuple, dict] = {}
    for r in rows:
        g, n = content_of(config, r["area_id"], r["area_name"])
        it = items.setdefault((g, n), {"group": g, "name": n, "runs": 0, "active_s": 0.0, "deaths": 0, "last": None})
        it["runs"] += 1
        it["active_s"] += r["active_s"] or 0
        it["deaths"] += r["deaths"]
        it["last"] = max(it["last"] or "", r["start_utc"])
    out = sorted(items.values(), key=lambda x: -x["active_s"])
    for it in out:
        it["avg_s"] = it["active_s"] / it["runs"] if it["runs"] else None
    groups: dict[str, dict] = {}
    for it in out:
        g = groups.setdefault(it["group"], {"group": it["group"], "runs": 0, "active_s": 0.0, "deaths": 0})
        g["runs"] += it["runs"]; g["active_s"] += it["active_s"]; g["deaths"] += it["deaths"]
    return {"items": out, "groups": sorted(groups.values(), key=lambda x: -x["active_s"])}


# ---------------------------------------------------------------- map modifiers (copied maps)

_NUM = re.compile(r"[+-]?\d+(?:\.\d+)?")


def normalize_mod(mod: str) -> str:
    """'Monsters have 40% increased Area of Effect' -> 'Monsters have #% increased Area of Effect'."""
    return _NUM.sub("#", mod).strip()


def map_mod_runs(con, config: Config, league: str | None, character_id: int | None) -> list[dict]:
    """Every map run that has a copied map linked, with its (normalized) mods."""
    f, a = _char_filter(con, league, character_id, "r")
    rows = _rows(con, f"""
        SELECT r.id, r.area_name, r.tier, r.start_utc, m.mods, m.quantity, m.pack_size, m.item_rarity,
               (SELECT COALESCE(SUM(v.active_s),0) FROM v_visit_active v WHERE v.run_id=r.id) AS active_s,
               (SELECT COUNT(*) FROM death d WHERE d.run_id=r.id) AS deaths
        FROM run r JOIN map_capture m ON m.run_id=r.id WHERE r.kind='map' {f}
    """, a)
    for r in rows:
        r["mods"] = sorted({normalize_mod(x) for x in json.loads(r["mods"] or "[]")})
    return rows


def map_mod_stats(rows: list[dict], selected: list[str] | None = None) -> dict:
    """Per-mod numbers, plus a with/without comparison for the selected mods (all must be present)."""
    per: dict[str, list] = defaultdict(list)
    for r in rows:
        for m in r["mods"]:
            per[m].append(r)

    def agg(lst):
        n = len(lst)
        t = sum(x["active_s"] for x in lst)
        d = sum(x["deaths"] for x in lst)
        return {"maps": n, "deaths": d, "deaths_per_map": d / n if n else None,
                "deathless_share": sum(1 for x in lst if not x["deaths"]) / n if n else None,
                "avg_active_s": t / n if n else None, "avg_quantity": _avg([x["quantity"] for x in lst]),
                "avg_pack_size": _avg([x["pack_size"] for x in lst])}

    mods = sorted(({"mod": m, **agg(v)} for m, v in per.items()), key=lambda x: -x["maps"])
    sel = [m for m in (selected or []) if m]
    compare = None
    if sel:
        with_ = [r for r in rows if all(m in r["mods"] for m in sel)]
        without = [r for r in rows if not all(m in r["mods"] for m in sel)]
        compare = {"with": agg(with_), "without": agg(without)}
    return {"mods": mods, "all": agg(rows), "compare": compare, "maps": len(rows)}


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------- campaign

def campaign_for(con, character_id: int) -> dict | None:
    visits = _rows(con, """
        SELECT id, area_id, area_name, kind, act, start_utc, end_utc, active_s, run_id
        FROM v_visit_active WHERE character_id=? ORDER BY start_utc, id
    """, (character_id,))
    start_i = next((i for i, v in enumerate(visits) if v["area_id"] == "1_1_1"), None)
    if start_i is None:
        return None
    vs = visits[start_i:]
    # Walk forward through the acts. An act only advances to the next act
    # (or skips ahead on a story zone, not a town), so a stray visit that
    # was attributed to the wrong character can't derail the splits.
    end_i, end_reason = None, None
    cur_act = 1
    boundaries: list[tuple[int, int]] = [(0, 1)]   # (visit index, act)
    for i, v in enumerate(vs):
        a = v["act"]
        if cur_act >= 10 and (a == EPILOGUE_ACT or v["kind"] == "map"):
            end_i, end_reason = i, ("epilogue" if a == EPILOGUE_ACT else "first map")
            break
        if a is not None and a < EPILOGUE_ACT and (a == cur_act + 1 or (a > cur_act + 1 and v["kind"] == "campaign")):
            cur_act = a
            boundaries.append((i, a))
    seg = vs[:end_i] if end_i is not None else vs
    ch = con.execute("SELECT name, class, league, league_start FROM v_own_character WHERE id=?", (character_id,)).fetchone()
    levels = _rows(con, "SELECT level, ts_utc FROM level_up WHERE character_id=? ORDER BY ts_utc", (character_id,))
    deaths = [r["ts_utc"] for r in _rows(con, "SELECT ts_utc FROM death WHERE character_id=? AND visit_id IS NOT NULL", (character_id,))]

    acts: list[dict] = []
    for n, (bi, a) in enumerate(boundaries):
        nxt = boundaries[n + 1][0] if n + 1 < len(boundaries) else len(seg)
        chunk = seg[bi:nxt]
        if not chunk:
            continue
        acts.append({
            "act": a, "start": chunk[0]["start_utc"],
            "end": seg[nxt]["start_utc"] if nxt < len(seg) else (vs[end_i]["start_utc"] if end_i is not None else chunk[-1]["end_utc"]),
            "active_s": sum(v["active_s"] or 0 for v in chunk),
            "zones": sum(1 for v in chunk if v["kind"] == "campaign"),
        })
    for act in acts:
        act["deaths"] = sum(1 for d in deaths if act["start"] <= d < (act["end"] or "9999"))
        lv = [l["level"] for l in levels if l["ts_utc"] < (act["end"] or "9999")]
        act["level_end"] = max(lv) if lv else 1
    start = seg[0]["start_utc"]
    end = acts[-1]["end"]
    total_active = sum(a["active_s"] for a in acts)
    league_start = ch["league_start"] if ch else None
    return {
        "character_id": character_id, "character": ch["name"] if ch else None, "class": ch["class"] if ch else None,
        "league": ch["league"] if ch else None, "start": start, "end": end,
        "completed": end_i is not None, "end_reason": end_reason,
        "active_s": total_active, "wall_s": _secs(start, end),
        "after_league_start_s": _secs(league_start, start) if league_start else None,
        "deaths": sum(a["deaths"] for a in acts), "level_end": acts[-1]["level_end"],
        "acts": acts,
    }


def campaigns(con, league: str | None) -> list[dict]:
    out = []
    for c in own_characters(con, league):
        cp = campaign_for(con, c["id"])
        if cp:
            out.append(cp)
    out.sort(key=lambda x: x["start"])
    return out


# ---------------------------------------------------------------- character

def character_detail(con, character_id: int) -> dict:
    ch = con.execute("SELECT * FROM v_own_character WHERE id=?", (character_id,)).fetchone()
    if not ch:
        return {}
    levels = _rows(con, "SELECT level, ts_utc FROM level_up WHERE character_id=? ORDER BY ts_utc", (character_id,))
    # Level vs cumulative play time
    visits = _rows(con, "SELECT start_utc, active_s, day, kind FROM v_visit_active WHERE character_id=? ORDER BY start_utc", (character_id,))
    cum, played = [], 0.0
    vi = 0
    for l in levels:
        while vi < len(visits) and visits[vi]["start_utc"] <= l["ts_utc"]:
            played += visits[vi]["active_s"] or 0
            vi += 1
        cum.append({"level": l["level"], "ts_utc": l["ts_utc"], "played_s": played})
    daily = defaultdict(float)
    for v in visits:
        daily[v["day"]] += v["active_s"] or 0
    deaths = _rows(con, """
        SELECT d.ts_utc, v.area_name, v.kind, v.area_level FROM death d LEFT JOIN area_visit v ON v.id=d.visit_id
        WHERE d.character_id=? AND d.visit_id IS NOT NULL ORDER BY d.ts_utc DESC
    """, (character_id,))
    death_by_kind = Counter(d["kind"] or "?" for d in deaths)
    tree = passive_state(con, character_id=character_id, tree="character")
    masteries = passive_state(con, character_id=character_id, tree="mastery")
    return {
        "character": dict(ch), "levels": cum, "daily": [{"day": k, "active_s": v} for k, v in sorted(daily.items())],
        "deaths": deaths[:200], "death_count": len(deaths), "death_by_kind": dict(death_by_kind),
        "tree": tree, "masteries": masteries,
        "total_active_s": sum(daily.values()),
    }


def passive_state(con, character_id: int | None = None, league: str | None = None, tree: str = "character") -> dict:
    """Replay allocate/unallocate changes to get what is allocated now."""
    if tree == "atlas":
        rows = _rows(con, "SELECT * FROM passive_change WHERE tree='atlas' AND league=? ORDER BY ts_utc, id", (league,))
    else:
        rows = _rows(con, "SELECT * FROM passive_change WHERE tree=? AND character_id=? ORDER BY ts_utc, id", (tree, character_id))
    alloc: dict[str, dict] = {}
    changes = []
    for r in rows:
        if r["action"] == "allocated":
            alloc[r["node_id"]] = {"node_id": r["node_id"], "name": r["name"], "since": r["ts_utc"]}
        else:
            alloc.pop(r["node_id"], None)
        changes.append({"ts_utc": r["ts_utc"], "action": r["action"], "node_id": r["node_id"], "name": r["name"]})
    by_name = Counter(v["name"] for v in alloc.values())
    return {
        "allocated": sorted(alloc.values(), key=lambda x: x["since"]),
        "count": len(alloc),
        "by_name": [{"name": k, "count": v} for k, v in by_name.most_common()],
        "changes": changes[-300:][::-1],
        "change_count": len(changes),
        "note": "Only points changed while the log was recording are known.",
    }


# ---------------------------------------------------------------- atlas

def atlas(con, config: Config, league: str) -> dict:
    state = passive_state(con, league=league, tree="atlas")
    rs = runs(con, config, league, None, kind="map", limit=None)
    by_hash: dict[str, list] = defaultdict(list)
    for r in rs:
        by_hash[r["atlas_hash"] or "-"].append(r)
    versions = []
    for h, lst in by_hash.items():
        act = sum(x["active_s"] for x in lst)
        versions.append({"atlas_hash": h, "runs": len(lst), "first": min(x["start_utc"] for x in lst),
                         "last": max(x["start_utc"] for x in lst), "avg_active_s": act / len(lst),
                         "deaths": sum(x["deaths"] for x in lst), "avg_tier": _avg([x["tier"] for x in lst]),
                         "maps_per_hour": len(lst) / (act / 3600) if act > 600 else None})
    versions.sort(key=lambda x: x["first"])
    # Group atlas node names into mechanics by their id ("atlas_breach_4_4" -> breach)
    groups = Counter()
    for n in state["allocated"]:
        m = re.match(r"atlas_([a-z]+)", n["node_id"])
        groups[(m.group(1) if m else "other")] += 1
    state["groups"] = [{"group": k, "count": v} for k, v in groups.most_common()]
    return {"tree": state, "versions": versions}


# ---------------------------------------------------------------- leagues

def league_summaries(con, config: Config) -> list[dict]:
    """One row per league you played, with the numbers the Standard page compares."""
    map_stats = {r["league"]: r for r in _rows(con, """
        SELECT c.league, COUNT(DISTINCT r.id) AS maps, MAX(r.tier) AS max_tier,
               COALESCE(SUM(v.active_s), 0) AS map_active_s
        FROM run r JOIN v_own_character c ON c.id=r.character_id
        LEFT JOIN v_visit_active v ON v.run_id=r.id
        WHERE r.kind='map' GROUP BY c.league""")}
    map_deaths = {r["league"]: r["n"] for r in _rows(con, """
        SELECT c.league, COUNT(*) n FROM death d JOIN run r ON r.id=d.run_id
        JOIN v_own_character c ON c.id=d.character_id WHERE r.kind='map' GROUP BY c.league""")}
    divs = {}
    for lg_name in {r[0] for r in con.execute("SELECT DISTINCT league FROM currency_snapshot")}:
        snaps = currency(con, lg_name)["snapshots"]
        if snaps and snaps[0].get("total_divine") is not None:
            divs[lg_name] = snaps[0]["total_divine"]
    out = []
    for lg in leagues(con, config):
        chars = own_characters(con, lg["name"])
        if not chars:
            continue
        cps = [c for c in campaigns(con, lg["name"]) if c["completed"]]
        best = min(cps, key=lambda c: c["active_s"]) if cps else None
        days = con.execute("""SELECT COUNT(DISTINCT day), MIN(start_utc), MAX(start_utc) FROM area_visit
                              WHERE character_id IN (SELECT id FROM v_own_character WHERE league=?)""", (lg["name"],)).fetchone()
        ms = map_stats.get(lg["name"], {})
        maps = ms.get("maps") or 0
        map_s = ms.get("map_active_s") or 0
        active = sum(c["active_s"] for c in chars)
        out.append({
            **lg, "characters": len(chars), "active_s": active, "hours": active / 3600,
            "maps": maps, "max_tier": ms.get("max_tier"), "map_active_s": map_s,
            "map_share": map_s / active if active else None,
            "maps_per_hour": maps / (map_s / 3600) if map_s > 600 else None,
            "avg_map_s": map_s / maps if maps else None,
            "map_deaths": map_deaths.get(lg["name"], 0),
            "deaths_per_map": map_deaths.get(lg["name"], 0) / maps if maps else None,
            "deaths": sum(c["deaths"] for c in chars),
            "max_level": max((c["level"] or 0) for c in chars), "days_played": days[0],
            "hours_per_day": active / 3600 / days[0] if days[0] else None,
            "first_play": days[1], "last_play": days[2],
            "best_campaign": {"character": best["character"], "active_s": best["active_s"]} if best else None,
            "best_campaign_s": best["active_s"] if best else None,
            "avg_campaign_s": sum(c["active_s"] for c in cps) / len(cps) if cps else None,
            "campaigns_completed": len(cps),
            "characters_95": sum(1 for c in chars if (c["level"] or 0) >= 95),
            "top_character": max(chars, key=lambda c: c["active_s"])["name"],
            "divines": divs.get(lg["name"]),
        })
    return out


# What the Standard page compares between leagues: key, label, format, higher-is-better
COMPARE = [
    ("hours", "Hours played", "hours", True),
    ("days_played", "Days played", "int", True),
    ("hours_per_day", "Hours per day played", "num1", True),
    ("maps", "Maps run", "int", True),
    ("maps_per_hour", "Maps per hour (in maps)", "num1", True),
    ("avg_map_s", "Average map time", "dur", False),
    ("deaths_per_map", "Deaths per map", "num2", False),
    ("map_share", "Share of time mapping", "pct", True),
    ("best_campaign_s", "Fastest campaign", "dur", False),
    ("characters", "Characters played", "int", None),
    ("max_level", "Highest level", "int", True),
    ("max_tier", "Highest map tier", "tier", True),
    ("divines", "Divines at last snapshot", "num1", True),
]


def standard(con, config: Config, focus: str | None) -> dict:
    """Account-wide totals plus how one league compares with the others."""
    rows = league_summaries(con, config)
    tot_active = sum(r["active_s"] for r in rows)
    tot_maps = sum(r["maps"] for r in rows)
    tot_map_s = sum(r["map_active_s"] for r in rows)
    all_cps = []
    for r in rows:
        if r["best_campaign"]:
            all_cps.append((r["best_campaign"]["active_s"], r["best_campaign"]["character"], r["name"]))
    first = min((r["first_play"] for r in rows if r["first_play"]), default=None)
    totals = {
        "leagues": len(rows), "active_s": tot_active, "maps": tot_maps, "map_active_s": tot_map_s,
        "deaths": sum(r["deaths"] for r in rows), "characters": sum(r["characters"] for r in rows),
        "days_played": sum(r["days_played"] or 0 for r in rows),
        "campaigns": sum(r["campaigns_completed"] for r in rows),
        "fastest_campaign": min(all_cps) if all_cps else None,
        "maps_per_hour": tot_maps / (tot_map_s / 3600) if tot_map_s > 600 else None,
        "avg_hours_per_league": tot_active / 3600 / len(rows) if rows else 0,
        "avg_maps_per_league": tot_maps / len(rows) if rows else 0,
        "avg_map_hours_per_league": tot_map_s / 3600 / len(rows) if rows else 0,
        "first_play": first,
        "max_level": max((r["max_level"] for r in rows), default=None),
    }
    divs = [r["divines"] for r in rows if r["divines"] is not None]
    totals["avg_divines_per_league"] = sum(divs) / len(divs) if divs else None

    compare = []
    focus_row = next((r for r in rows if r["name"] == focus), None)
    if focus_row:
        others = [r for r in rows if r["name"] != focus]
        for key, label, fmt, better in COMPARE:
            vals = [o[key] for o in others if o.get(key) is not None]
            v = focus_row.get(key)
            avg = sum(vals) / len(vals) if vals else None
            ranked = sorted([x for x in [*vals, v] if x is not None], reverse=(better is not False))
            rank = ranked.index(v) + 1 if v is not None else None
            diff = (v - avg) / avg if v is not None and avg else None
            compare.append({"key": key, "label": label, "fmt": fmt, "better": better, "value": v,
                            "others_avg": avg, "diff": diff, "rank": rank, "of": len(ranked)})
    return {"leagues": rows, "totals": totals, "focus": focus, "compare": compare, "pace": league_pace(con, config)}


def league_pace(con, config: Config, max_days: int = 90) -> dict:
    """Cumulative hours and maps by day since each league started."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(config.timezone)
    starts = {}
    for lg in config.leagues:
        starts[lg.name] = lg.start.astimezone(tz).date()
    hours = defaultdict(lambda: defaultdict(float))
    maps = defaultdict(lambda: defaultdict(int))
    for r in _rows(con, """SELECT c.league, v.day, SUM(v.active_s) s FROM v_visit_active v
                           JOIN v_own_character c ON c.id=v.character_id GROUP BY c.league, v.day"""):
        if r["league"] in starts and r["day"]:
            d = (datetime.strptime(r["day"], "%Y-%m-%d").date() - starts[r["league"]]).days
            if 0 <= d < max_days:
                hours[r["league"]][d] += (r["s"] or 0) / 3600
    for r in _rows(con, """SELECT c.league, r.day, COUNT(*) n FROM run r JOIN v_own_character c ON c.id=r.character_id
                           WHERE r.kind='map' GROUP BY c.league, r.day"""):
        if r["league"] in starts and r["day"]:
            d = (datetime.strptime(r["day"], "%Y-%m-%d").date() - starts[r["league"]]).days
            if 0 <= d < max_days:
                maps[r["league"]][d] += r["n"]
    out = {}
    for lg in hours:
        last = max(max(hours[lg], default=0), max(maps[lg], default=0))
        h = m = 0.0
        series = []
        for d in range(last + 1):
            h += hours[lg].get(d, 0)
            m += maps[lg].get(d, 0)
            series.append({"day": d + 1, "hours": round(h, 2), "maps": int(m)})
        out[lg] = series
    return out


# ---------------------------------------------------------------- sessions

def last_session(con, league: str, character_id: int | None) -> dict | None:
    """The most recent game session that included play in this league
    (and character, if one is picked), with a breakdown per character."""
    f, a = _char_filter(con, league, character_id, "v")
    row = con.execute(f"SELECT v.session_id FROM area_visit v WHERE 1=1 {f} ORDER BY v.start_utc DESC LIMIT 1", a).fetchone()
    if not row:
        return None
    sid = row[0]
    s = con.execute("SELECT * FROM game_session WHERE id=?", (sid,)).fetchone()
    vis = _rows(con, f"SELECT v.* FROM v_visit_active v WHERE v.session_id=? {f}", [sid, *a])
    q = lambda n: ",".join("?" * n)
    run_ids = sorted({v["run_id"] for v in vis if v["run_id"]})
    runs_ = _rows(con, f"SELECT id, kind, tier, character_id FROM run WHERE id IN ({q(len(run_ids))})", run_ids) if run_ids else []
    map_ids = {r["id"] for r in runs_ if r["kind"] == "map"}
    visit_ids = [v["id"] for v in vis]
    deaths = _rows(con, f"SELECT character_id, COUNT(*) n FROM death WHERE visit_id IN ({q(len(visit_ids))}) GROUP BY character_id",
                   visit_ids) if visit_ids else []
    deaths_by = {d["character_id"]: d["n"] for d in deaths}
    chars = sorted({v["character_id"] for v in vis if v["character_id"]})
    end = s["end_utc"] or s["start_utc"]
    lv = {r["character_id"]: r for r in _rows(con, f"""
        SELECT character_id, MIN(level) lo, MAX(level) hi, COUNT(*) n FROM level_up
        WHERE ts_utc BETWEEN ? AND ? AND character_id IN ({q(len(chars))}) GROUP BY character_id""",
        [s["start_utc"], end, *chars])} if chars else {}
    info = {r["id"]: r for r in _rows(con, f"SELECT id, name, class, level FROM character WHERE id IN ({q(len(chars))})", chars)} if chars else {}
    per_char = []
    for cid in chars:
        cv = [v for v in vis if v["character_id"] == cid]
        cm = {v["run_id"] for v in cv if v["run_id"] in map_ids}
        per_char.append({
            "id": cid, "name": info.get(cid, {}).get("name"), "class": info.get(cid, {}).get("class"),
            "level": info.get(cid, {}).get("level"), "active_s": sum(v["active_s"] for v in cv),
            "start": min(v["start_utc"] for v in cv), "maps": len(cm),
            "deaths": deaths_by.get(cid, 0), "levels_gained": lv[cid]["n"] if cid in lv else 0,
            "areas": len(cv),
        })
    per_char.sort(key=lambda x: x["start"])
    map_s = sum(v["active_s"] for v in vis if v["run_id"] in map_ids)
    camp_s = sum(v["active_s"] for v in vis if v["kind"] == "campaign")
    afk_s = sum(v["afk_s"] for v in vis)
    offers = con.execute("SELECT COUNT(*) FROM whisper WHERE direction='From' AND trade_kind='buy_offer' AND ts_utc BETWEEN ? AND ?",
                         (s["start_utc"], end)).fetchone()[0]
    sess = _rows(con, f"SELECT v.session_id, SUM(v.active_s) s FROM v_visit_active v WHERE 1=1 {f} GROUP BY v.session_id", a)
    avg_s = sum(x["s"] for x in sess) / len(sess) if sess else None
    active = sum(v["active_s"] for v in vis)
    tiers = [r["tier"] for r in runs_ if r["kind"] == "map" and r["tier"]]
    return {
        "start": s["start_utc"], "end": s["end_utc"], "active_s": active, "afk_s": afk_s,
        "maps": len(map_ids), "map_s": map_s, "campaign_s": camp_s,
        "maps_per_hour": len(map_ids) / (map_s / 3600) if map_s > 300 else None,
        "avg_map_s": map_s / len(map_ids) if map_ids else None,
        "max_tier": max(tiers) if tiers else None,
        "deaths": sum(deaths_by.values()), "levels_gained": sum(x["levels_gained"] for x in per_char),
        "areas": len(vis), "other_runs": sum(1 for r in runs_ if r["kind"] != "map"),
        "trade_offers": offers, "characters": per_char,
        "avg_session_s": avg_s, "sessions": len(sess),
    }


# ---------------------------------------------------------------- trades

def trades(con, league: str | None, days: int = 0) -> dict:
    rows = _rows(con, """SELECT ts_utc, day, direction, who, message, trade_kind, item, price_amount, price_currency, trade_league
                         FROM whisper ORDER BY ts_utc DESC""")
    if league:
        lg_rows = [r for r in rows if r["trade_kind"] != "buy_offer" or (r["trade_league"] or "").lower() in league.lower() or league.lower() in (r["trade_league"] or "").lower()]
    else:
        lg_rows = rows
    offers = [r for r in lg_rows if r["trade_kind"] == "buy_offer"]
    incoming = [r for r in offers if r["direction"] == "From"]
    outgoing = [r for r in offers if r["direction"] == "To"]
    results = Counter(r[0] for r in con.execute("SELECT result FROM trade_result"))
    by_day = defaultdict(lambda: {"incoming": 0, "outgoing": 0})
    for r in offers:
        by_day[r["day"]]["incoming" if r["direction"] == "From" else "outgoing"] += 1
    def top(lst):
        c = Counter(r["item"] for r in lst)
        return [{"item": k, "count": v} for k, v in c.most_common(20)]
    return {
        "incoming": incoming[:200], "outgoing": outgoing[:200],
        "counts": {"incoming": len(incoming), "outgoing": len(outgoing), "accepted": results.get("accepted", 0),
                   "cancelled": results.get("cancelled", 0), "whispers": len(lg_rows)},
        "by_day": [{"day": k, **v} for k, v in sorted(by_day.items())][-120:],
        "top_sold": top(incoming), "top_bought": top(outgoing),
        "note": "Offers are whispers in the trade-site format. Whether a trade completed can't be told from the log for certain.",
    }


# ---------------------------------------------------------------- currency (manual)

def currency(con, league: str | None) -> dict:
    snaps = _rows(con, "SELECT * FROM currency_snapshot WHERE (? IS NULL OR league=?) ORDER BY ts_utc", (league, league))
    for s in snaps:
        items = _rows(con, "SELECT item, qty, chaos_each FROM currency_snapshot_item WHERE snapshot_id=? ORDER BY item", (s["id"],))
        s["items"] = items
        total = 0.0
        for it in items:
            each = it["chaos_each"]
            if each is None:
                if it["item"] == "Chaos Orb":
                    each = 1.0
                elif it["item"] == "Divine Orb":
                    each = s["divine_chaos"] or 0
                else:
                    each = 0
            total += it["qty"] * each
        s["total_chaos"] = total
        s["total_divine"] = total / s["divine_chaos"] if s["divine_chaos"] else None
    # profit between consecutive snapshots, with play time in between
    for prev, cur in zip(snaps, snaps[1:]):
        played = con.execute("SELECT COALESCE(SUM(active_s),0) FROM v_visit_active WHERE start_utc>=? AND start_utc<?",
                             (prev["ts_utc"], cur["ts_utc"])).fetchone()[0]
        cur["delta_chaos"] = cur["total_chaos"] - prev["total_chaos"]
        cur["played_s"] = played
        cur["chaos_per_hour"] = cur["delta_chaos"] / (played / 3600) if played > 600 else None
    return {"snapshots": snaps[::-1]}


def add_currency_snapshot(con, data: dict) -> int:
    ts = data.get("ts_utc") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = con.execute(
        "INSERT INTO currency_snapshot(ts_utc, league, character, note, divine_chaos) VALUES (?,?,?,?,?)",
        (ts, data.get("league"), data.get("character"), data.get("note"), _num(data.get("divine_chaos"))),
    )
    sid = cur.lastrowid
    for it in data.get("items") or []:
        name = (it.get("item") or "").strip()
        qty = _num(it.get("qty"))
        if not name or qty is None:
            continue
        con.execute("INSERT OR REPLACE INTO currency_snapshot_item(snapshot_id, item, qty, chaos_each) VALUES (?,?,?,?)",
                    (sid, name, qty, _num(it.get("chaos_each"))))
    con.commit()
    return sid


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- captures

def captures(con, limit: int = 100) -> list[dict]:
    rows = _rows(con, """SELECT m.id, m.ts_utc, m.rarity, m.name, m.base, m.tier, m.quantity, m.item_rarity, m.pack_size,
                                m.properties, m.mods, m.corrupted, m.identified, m.run_id, r.area_name, r.start_utc AS run_start
                         FROM map_capture m LEFT JOIN run r ON r.id=m.run_id ORDER BY m.ts_utc DESC LIMIT ?""", (limit,))
    for r in rows:
        r["properties"] = json.loads(r["properties"] or "{}")
        r["mods"] = json.loads(r["mods"] or "[]")
    return rows


# ---------------------------------------------------------------- milestones / voidstones

def boss_progress(con, config: Config, league: str, character_id: int | None = None) -> dict[str, dict]:
    """For every boss in milestones.yaml: attempts, deaths and first kill in this
    league (or by one character)."""
    bosses = (config.milestones or {}).get("bosses") or {}
    own = [character_id] if character_id else [r[0] for r in con.execute("SELECT id FROM v_own_character WHERE league=?", (league,))]
    if not own:
        return {}
    q = ",".join("?" * len(own))
    names = {r[0]: r[1] for r in con.execute(f"SELECT id, name FROM character WHERE id IN ({q})", own)}
    kills = defaultdict(list)
    for r in _rows(con, f"SELECT boss, character_id, ts_utc FROM boss_kill WHERE character_id IN ({q}) ORDER BY ts_utc", own):
        kills[r["boss"]].append(r)
    out = {}
    seen_areas = [r[0] for r in con.execute(f"SELECT DISTINCT area_id FROM area_visit WHERE character_id IN ({q})", own)]
    for boss, spec in bosses.items():
        rx = re.compile(spec["area"])
        area_ids = [a for a in seen_areas if rx.search(a)]
        visits = []
        if area_ids:
            qa = ",".join("?" * len(area_ids))
            visits = _rows(con, f"""SELECT v.id, v.seed, v.character_id, v.start_utc, v.end_utc, v.active_s, v.area_name,
                                    (SELECT COUNT(*) FROM death d WHERE d.visit_id=v.id) AS deaths
                                    FROM v_visit_active v WHERE v.character_id IN ({q}) AND v.area_id IN ({qa})
                                    ORDER BY v.start_utc""", [*own, *area_ids])
        instances = defaultdict(list)
        for v in visits:
            instances[(v["character_id"], v["seed"])].append(v)
        first_kill, how = None, None
        if kills.get(boss):
            k = kills[boss][0]
            first_kill, how = {"ts_utc": k["ts_utc"], "character": names.get(k["character_id"])}, "dialogue"
        elif spec.get("no_death"):
            need = spec["no_death"].get("min_seconds", 60)
            for inst in sorted(instances.values(), key=lambda x: x[0]["start_utc"]):
                last = inst[-1]
                dur = _secs(last["start_utc"], last["end_utc"])
                if last["deaths"] == 0 and dur >= need:
                    first_kill, how = {"ts_utc": last["end_utc"], "character": names.get(last["character_id"])}, "likely"
                    break
        before = [i for i in instances.values() if not first_kill or i[0]["start_utc"] <= first_kill["ts_utc"]]
        out[boss] = {
            "boss": boss, "area_name": visits[0]["area_name"] if visits else None,
            "attempts": len(instances), "entries": len(visits),
            "deaths": sum(v["deaths"] for v in visits),
            "attempts_to_kill": len(before) if first_kill else None,
            "deaths_before_kill": sum(v["deaths"] for i in before for v in i) if first_kill else None,
            "kills": len(kills.get(boss, [])) if how == "dialogue" else (1 if first_kill else 0),
            "first_kill": first_kill, "detected": how, "count_only": bool(spec.get("count_only")),
            "first_seen": visits[0]["start_utc"] if visits else None,
            "time_in_arena_s": sum(v["active_s"] for v in visits),
        }
    # The Maven's Crucible: the first four you finish in a league are the quest
    # invitations that lead to the Maven (3/4/5/6 bosses); every one after that
    # (Kirac's repeatable 10-boss invitation) only counts as a Crucible ran.
    if "The Maven's Crucible" in out:
        # the invitations are Atlas progress, shared by all your characters in the league
        own = [r[0] for r in con.execute("SELECT id FROM v_own_character WHERE league=?", (league,))] or own
        q = ",".join("?" * len(own))
        names = {r[0]: r[1] for r in con.execute(f"SELECT id, name FROM character WHERE id IN ({q})", own)}
        done = _rows(con, f"""SELECT b.ts_utc, b.character_id, b.visit_id FROM boss_kill b
                              WHERE b.boss = 'The Maven''s Crucible' AND b.character_id IN ({q}) ORDER BY b.ts_utc""", own)
        for n in range(1, 5):
            hit = done[n - 1] if len(done) >= n else None
            out[crucible_step(n)] = {
                "boss": crucible_step(n), "attempts": None, "deaths": None, "kills": 1 if hit else 0,
                "first_kill": {"ts_utc": hit["ts_utc"], "character": names.get(hit["character_id"])} if hit else None,
                "detected": "dialogue" if hit else None, "count_only": False, "area_name": "The Maven's Crucible",
            }
        out["The Maven's Crucible"]["repeat_kills"] = [d["ts_utc"] for d in done[4:]]
    return out


def crucible_step(n: int) -> str:
    return f"Maven's Crucible {n} of 4"


def voidstones(con, config: Config, league: str, character_id: int | None = None, bp: dict | None = None) -> dict:
    bp = bp if bp is not None else boss_progress(con, config, league, character_id)
    lg = next((l for l in config.leagues if l.name == league), None)
    lg_start = lg.start.strftime("%Y-%m-%dT%H:%M:%SZ") if lg else None
    stones = []
    for vs in (config.milestones or {}).get("voidstones") or []:
        names_ = []
        for st_ in vs.get("steps", []):
            names_ += [crucible_step(n) for n in range(1, 5)] if st_ == "The Maven's Crucible" else [st_]
        steps = [bp.get(s) or {"boss": s, "attempts": 0, "first_kill": None, "count_only": False} for s in names_]
        req = [bp.get(r) for r in vs.get("requires", [])]
        done = bool(req) and all(r and r["first_kill"] for r in req)
        when = max(r["first_kill"]["ts_utc"] for r in req) if done else None
        likely = done and any(r["detected"] == "likely" for r in req)
        countable = [s for s in steps if not s.get("count_only")]
        stones.append({
            "name": vs["name"], "from": vs.get("from"), "obtained": done, "likely": likely, "when": when,
            "days_into_league": _secs(lg_start, when) / 86400 if when and lg_start else None,
            "steps": steps, "steps_done": sum(1 for s in countable if s.get("first_kill")), "steps_total": len(countable),
        })
    return {"voidstones": stones, "obtained": sum(1 for s in stones if s["obtained"]), "total": len(stones)}


# ---------------------------------------------------------------- league start

TRIALS = [   # (lab, zone id, zone) - must match the "Trial: ..." entries in milestones.yaml
    ("Normal", "1_1_7_1", "The Lower Prison"), ("Normal", "1_2_5_1", "The Crypt Level 1"),
    ("Normal", "1_2_6_2", "The Chamber of Sins Level 2"), ("Normal", "1_3_3_1", "The Crematorium"),
    ("Normal", "1_3_6", "The Catacombs"), ("Normal", "1_3_15", "The Imperial Gardens"),
    ("Cruel", "2_6_7_1", "The Lower Prison"), ("Cruel", "2_7_4", "The Crypt"),
    ("Cruel", "2_7_5_2", "The Chamber of Sins Level 2"),
    ("Merciless", "2_8_5", "The Bath House"), ("Merciless", "2_9_7", "The Tunnel"), ("Merciless", "2_10_9", "The Ossuary"),
]

# Quests that give passive skill points: (act, name as /passives prints it,
# points, town where the reward is handed out, NPC, what to do). 24 in total.
QUEST_PASSIVES = [
    (1, "The Dweller of the Deep", 1, "1_1_town", "Tarkleigh", "Kill the Deep Dweller in The Flooded Depths"),
    (1, "The Marooned Mariner", 1, "1_1_town", "Bestel", "Allflame from The Ship Graveyard Cave, then kill Fairgraves"),
    (2, "The Way Forward", 1, "1_1_town", "Bestel", "Kill Arteri in The Western Forest, open Prisoner's Gate"),
    (2, "Through Sacred Ground", 1, "1_2_town", "Yeena", "Golden Hand in The Crypt Level 2"),
    (2, "Deal with the Bandits", 1, "1_2_town", "Eramir", "Kill all three bandits"),
    (3, "Victario's Secrets", 1, "1_3_town", "Hargan", "Three busts in The Sewers"),
    (3, "Piety's Pets", 1, "1_3_town", "Grigor", "Kill Piety in The Lunaris Temple Level 2"),
    (4, "An Indomitable Spirit", 1, "1_4_town", "Tasuni", "Free Deshret's spirit in The Mines Level 2"),
    (5, "In Service to Science", 1, "1_5_town", "Vilenta", "Miasmeter in The Control Blocks"),
    (5, "Kitava's Torments", 1, "1_5_town", "Lani", "Three torments in The Reliquary"),
    (6, "The Father of War", 1, "2_6_town", "Tarkleigh", "Kill Tukohama in The Karui Fortress"),
    (6, "The Puppet Mistress", 1, "2_6_town", "Tarkleigh", "Kill Ryslatha in The Wetlands"),
    (6, "The Cloven One", 1, "2_6_town", "Bestel", "Kill Abberath in Prisoner's Gate"),
    (7, "The Master of a Million Faces", 1, "2_7_town", "Eramir", "Kill Ralakesh (as Greust) in The Ashen Fields"),
    (7, "Queen of Despair", 1, "2_7_town", "Eramir", "Kill Gruthkul in The Dread Thicket"),
    (7, "Kishara's Star", 1, "2_7_town", "Weylam", "Kishara's Star in The Causeway"),
    (8, "Love is Dead", 1, "2_8_town", "Clarissa", "Ankh in The Quay, kill Tolman"),
    (8, "Reflection of Terror", 1, "2_8_town", "Sin", "Kill Yugul in The High Gardens"),
    (8, "The Gemling Legion", 1, "2_8_town", "Maramoa", "Kill the Gemling Legion in The Grain Gate"),
    (9, "Queen of the Sands", 1, "2_9_town", "Irasha", "Kill Shakari in The Oasis"),
    (9, "The Ruler of Highgate", 1, "2_9_town", "Irasha", "Kill Garukhan in The Quarry"),
    (10, "Vilenta's Vengeance", 1, "2_10_town", "Lani", "Kill Vilenta in The Control Blocks"),
    (10, "An End to Hunger", 2, "2_10_town", "Lani", "Kill Kitava in The Feeding Trough, then talk to Lani"),
]

TOWN_NAMES = {"1_1_town": "Lioneye's Watch", "1_2_town": "The Forest Encampment", "1_3_town": "The Sarn Encampment",
              "1_4_town": "Highgate", "1_5_town": "Overseer's Tower", "2_6_town": "Lioneye's Watch",
              "2_7_town": "The Bridge Encampment", "2_8_town": "The Sarn Encampment", "2_9_town": "Highgate",
              "2_10_town": "Oriath Docks"}

LAB_BOSSES = ["Normal Labyrinth", "Cruel Labyrinth", "Merciless Labyrinth", "Eternal Labyrinth"]


def current_league(config: Config) -> str | None:
    """The newest league in leagues.yaml that has started."""
    now = datetime.now(timezone.utc)
    started = [l for l in config.leagues if l.start <= now]
    return started[-1].name if started else None


def league_start_status(con, config: Config, league: str | None = None) -> dict:
    """Which league start phase a league is in:
    campaign (until the first character finishes Act 10), mapping (until all
    Voidstones), done."""
    league = league or current_league(config)
    out = {"league": league, "phase": "done", "starter": None, "campaign_end": None,
           "voidstones": 0, "voidstones_total": 4}
    if not league:
        return out
    starter = campaign_character(con, league)
    cp = campaign_for(con, starter) if starter else None
    out["starter"] = starter
    out["mapping_char"] = mapping_character(con, league) if cp and cp["completed"] else None
    names = {r[0]: r[1] for r in con.execute("SELECT id, name FROM character WHERE id IN (?, ?)", (starter, out["mapping_char"]))}
    out["campaign_name"], out["mapping_name"] = names.get(starter), names.get(out["mapping_char"])
    if not cp or not cp["completed"]:
        out["phase"] = "campaign"
        return out
    out["campaign_end"] = cp["end"]
    vs = voidstones(con, config, league)
    out["voidstones"], out["voidstones_total"] = vs["obtained"], vs["total"]
    end, reason = league_start_end(config, league, vs)
    out["end_utc"], out["end_reason"] = end, reason
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["phase"] = "mapping" if not end or end > now else "done"
    return out


def league_start_end(config: Config, league: str, vs: dict) -> tuple[str | None, str | None]:
    """When league start ends: the last Voidstone, or league_start_days (14)
    after the league launched, whichever comes first. Returns (time, reason)
    where reason is "voidstones" or "days"; the time can be in the future."""
    days = float((config.settings or {}).get("league_start_days", 14) or 0)
    lg = next((l for l in config.leagues if l.name == league), None)
    cap = (lg.start + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ") if lg and days > 0 else None
    stones = vs.get("voidstones") or []
    last = max((x["when"] for x in stones if x["when"]), default=None) if stones and all(x["obtained"] for x in stones) else None
    if last and (not cap or last <= cap):
        return last, "voidstones"
    return cap, ("days" if cap else None)


def campaign_lock(con, league: str | None) -> dict:
    """Who League Start Campaign shows, and why."""
    cid = campaign_character(con, league)
    cp = campaign_for(con, cid) if cid else None
    name = con.execute("SELECT name FROM character WHERE id=?", (cid,)).fetchone() if cid else None
    return {"id": cid, "name": name[0] if name else None, "completed": bool(cp and cp["completed"])}


def mapping_lock(con, league: str | None) -> dict:
    """Who League Start Mapping shows, and why."""
    cid = mapping_character(con, league)
    name = con.execute("SELECT name FROM character WHERE id=?", (cid,)).fetchone() if cid else None
    t16 = bool(cid and con.execute("SELECT 1 FROM run WHERE kind='map' AND tier>=16 AND character_id=? LIMIT 1", (cid,)).fetchone())
    return {"id": cid, "name": name[0] if name else None, "t16": t16}


def campaign_character(con, league: str | None) -> int | None:
    """The character League Start Campaign is locked to: the first to finish
    the campaign in this league; until someone has, the one furthest along."""
    done, going = [], []
    for c in campaign_characters(con, league):
        cp = campaign_for(con, c["id"])
        if not cp:
            continue
        if cp["completed"]:
            done.append((cp["end"], c["id"]))
        else:
            going.append((len(cp["acts"]), cp["acts"][-1]["start"] if cp["acts"] else "", c["id"]))
    if done:
        return min(done)[1]
    return max(going)[2] if going else None


def mapping_character(con, league: str | None) -> int | None:
    """The character League Start Mapping is locked to: the first to run a
    T16 map; until someone has, the one that reached the highest tier first."""
    if not league:
        return None
    rows = con.execute("""SELECT character_id, tier FROM run WHERE kind='map' AND tier IS NOT NULL
                          AND character_id IN (SELECT id FROM v_own_character WHERE league=?) ORDER BY start_utc""",
                       (league,)).fetchall()
    hit = next((r[0] for r in rows if r[1] >= 16), None)
    if hit:
        return hit
    if rows:
        top = max(r[1] for r in rows)
        return next(r[0] for r in rows if r[1] == top)
    return campaign_character(con, league)


def _level_lookup(con, ids: list[int]):
    """level_at(character_id, ts) -> the character's level at that moment."""
    if not ids:
        return lambda cid, ts: None
    q = ",".join("?" * len(ids))
    per: dict[int, list] = defaultdict(list)
    for r in con.execute(f"SELECT character_id, level, ts_utc FROM level_up WHERE character_id IN ({q}) ORDER BY ts_utc", ids):
        per[r[0]].append((r[2], r[1]))

    def level_at(cid, ts):
        lst = per.get(cid) or []
        best = 1
        for t, lv in lst:
            if ts and t > ts:
                break
            best = max(best, lv)
        return best
    return level_at


# Story bosses that block the way forward: (act, boss, arena zone, zones that
# can only be reached after the kill). Optional bosses (Fairgraves, the Weaver,
# Abberath...) write nothing to the log when they die, so they can't be confirmed.
CAMPAIGN_BOSSES = [
    (1, "Hillock", "1_1_1", ["1_1_town", "1_1_2"]),
    (1, "Brutus, the Warden", "1_1_7_2", ["1_1_8"]),
    (1, "Merveil", "1_1_11_2", ["1_2_1", "1_2_town"]),
    (2, "The Vaal Oversoul", "1_2_14_3", ["1_3_1", "1_3_town"]),
    (3, "Piety", "1_3_14_2", ["1_3_18_1"]),
    (3, "Dominus", "1_3_18_2", ["1_4_1", "1_4_town"]),
    (4, "Voll, Emperor of Purity", "1_4_2", ["1_4_3_1"]),
    (4, "King Kaom", "1_4_4_3", ["1_4_6_1"]),
    (4, "Daresso, King of Swords", "1_4_5_2", ["1_4_6_1"]),
    (4, "Malachai, the Nightmare", "1_4_6_3", ["1_4_7", "1_5_1"]),
    (5, "High Templar Avarius / Innocence", "1_5_5", ["1_5_4b"]),
    (5, "Kitava", "1_5_8", ["2_6_town", "2_6_1"]),
    (6, "Tukohama", "2_6_5", ["2_6_6"]),
    (6, "The Brine King", "2_6_15", ["2_7_town", "2_7_1"]),
    (7, "Arakaali", "2_7_12_2", ["2_8_town", "2_8_1"]),
    (8, "Doedre", "2_8_2_2", ["2_8_3"]),
    (8, "Solaris and Lunaris", "2_8_13", ["2_9_town", "2_9_1"]),
    (9, "The Depraved Trinity", "2_9_10_2", ["2_10_town", "2_10_1"]),
    (10, "Avarius, Reassembled", "2_10_1", ["2_10_2"]),
    (10, "Kitava, the Insatiable", "2_10_6", ["2_11_endgame_town"]),
]


def _campaign_zone_counts(con) -> dict[int, int]:
    """How many story zones each act has (from every campaign you've played)."""
    out = defaultdict(int)
    for act, n in con.execute("""SELECT act, COUNT(DISTINCT area_id) FROM area_visit
                                 WHERE kind='campaign' AND act BETWEEN 1 AND 10 AND area_id NOT LIKE '%SideArea%'
                                 GROUP BY act"""):
        out[act] = n
    return out


def campaign_splits(con, character_id: int) -> dict | None:
    """Speedrun-style splits for one character's campaign: per act and per
    zone, with the play-time clock (AFK left out) at each point."""
    base = campaign_for(con, character_id)
    if not base:
        return None
    sql = """SELECT id, area_id, area_name, kind, act, start_utc, end_utc, active_s
             FROM v_visit_active WHERE character_id=? AND start_utc>=?"""
    args: list = [character_id, base["start"]]
    if base["completed"]:
        sql += " AND start_utc<?"
        args.append(base["end"])
    visits = _rows(con, sql + " ORDER BY start_utc, id", args)
    deaths_by_visit = Counter(r[0] for r in con.execute(
        "SELECT visit_id FROM death WHERE character_id=? AND visit_id IS NOT NULL", (character_id,)))
    level_at = _level_lookup(con, [character_id])
    clock, cum = [], 0.0          # play time at the start of each visit
    for v in visits:
        clock.append(cum)
        cum += v["active_s"] or 0

    def clock_at(ts):
        t = 0.0
        for v, c in zip(visits, clock):
            if v["start_utc"] > ts:
                break
            t = c + min(v["active_s"] or 0, _secs(v["start_utc"], ts))
        return t

    acts_in = base["acts"]
    acts = []
    for n, a in enumerate(acts_in):
        nxt_start = acts_in[n + 1]["start"] if n + 1 < len(acts_in) else None
        idx = [i for i, v in enumerate(visits) if v["start_utc"] >= a["start"] and (nxt_start is None or v["start_utc"] < nxt_start)]
        finished = nxt_start is not None or base["completed"]
        zones: dict[str, dict] = {}
        town_s = other_s = 0.0
        for i in idx:
            v = visits[i]
            d = deaths_by_visit.get(v["id"], 0)
            if v["kind"] == "campaign":
                z = zones.get(v["area_id"])
                if not z:
                    z = zones[v["area_id"]] = {
                        "zone": v["area_name"] or v["area_id"], "area_id": v["area_id"], "zone_act": v["act"], "entered": clock[i],
                        "entered_utc": v["start_utc"], "level_in": level_at(character_id, v["start_utc"]),
                        "time_s": 0.0, "deaths": 0, "visits": 0}
                z["time_s"] += v["active_s"] or 0
                z["deaths"] += d
                z["visits"] += 1
                z["level_out"] = level_at(character_id, v["end_utc"] or v["start_utc"])
            elif v["kind"] == "town":
                town_s += v["active_s"] or 0
            else:
                other_s += v["active_s"] or 0
        end_ts = a["end"]
        act_s = sum(visits[i]["active_s"] or 0 for i in idx)
        start_clock = clock[idx[0]] if idx else None
        acts.append({
            "act": a["act"], "start_utc": a["start"], "end_utc": end_ts if finished else None, "finished": finished,
            "split": (start_clock or 0) + act_s if finished else None, "start_split": start_clock,
            "time_s": act_s, "level_start": level_at(character_id, a["start"]),
            "level_end": level_at(character_id, end_ts) if finished else level_at(character_id, None),
            "deaths": sum(deaths_by_visit.get(visits[i]["id"], 0) for i in idx),
            "zones": list(zones.values()), "zone_count": len(zones), "town_s": town_s, "other_s": other_s,
        })
    # Labyrinths this character finished (at any point, campaign or later).
    labs = []
    # League start ends with the campaign: nothing after the Act 10 finish counts here
    cut = base["end"] if base["completed"] else "9999"
    # quest rewards and /passives get 10 minutes' grace (Lani hands out An End
    # to Hunger just after Kitava; people type /passives right away)
    qcut = (datetime.fromisoformat(cut.replace("Z", "+00:00")) + timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M:%SZ") if base["completed"] else "9999"
    kills = {r[0]: r[1] for r in con.execute(
        "SELECT boss, MIN(ts_utc) FROM boss_kill WHERE character_id=? AND ts_utc<=? GROUP BY boss", (character_id, cut))}
    for i, boss in enumerate(LAB_BOSSES[:3]):
        prefix = f"{i + 1}_Labyrinth"
        lab_v = _rows(con, """SELECT v.id, v.start_utc, v.active_s, (SELECT COUNT(*) FROM death d WHERE d.visit_id=v.id) AS deaths
                              FROM v_visit_active v WHERE v.character_id=? AND v.area_id LIKE ? ORDER BY v.start_utc""",
                      (character_id, prefix + "%"))
        ts = kills.get(boss)
        before = [v for v in lab_v if not ts or v["start_utc"] <= ts]
        labs.append({
            "lab": boss, "done": bool(ts), "ts_utc": ts,
            "split": clock_at(ts) if ts and (not base["completed"] or ts < base["end"]) else None,
            "after_campaign": bool(ts and base["completed"] and ts >= base["end"]),
            "level": level_at(character_id, ts) if ts else None,
            "time_s": sum(v["active_s"] or 0 for v in before), "deaths": sum(v["deaths"] for v in before),
            "entered": bool(lab_v),
        })
    total = acts[-1]["split"] if base["completed"] and acts else cum

    # progress: finished acts count fully; the running act by zones entered
    expected = _campaign_zone_counts(con)
    for a in acts:
        exp = expected.get(a["act"]) or max(a["zone_count"], 1)
        a["progress"] = 1.0 if a["finished"] else min(0.95, a["zone_count"] / exp)
    progress = sum(a["progress"] for a in acts) / 10
    last_zone = next((v for v in reversed(visits) if v["kind"] == "campaign"), None)

    # story bosses: done once you reach a zone behind them
    first_entry: dict[str, tuple[int, dict]] = {}
    for i, v in enumerate(visits):
        first_entry.setdefault(v["area_id"], (i, v))
    bosses = []
    for act, boss, arena, proof in CAMPAIGN_BOSSES:
        if arena not in first_entry:
            bosses.append({"act": act, "boss": boss, "zone": None, "done": False, "entered": False})
            continue
        ai, av = first_entry[arena]
        after = [first_entry[p] for p in proof if p in first_entry and first_entry[p][0] > ai]
        done_i, done_v = min(after, key=lambda x: x[0]) if after else (None, None)
        arena_v = [(i, v) for i, v in enumerate(visits) if v["area_id"] == arena and (done_i is None or i < done_i)]
        bosses.append({
            "act": act, "boss": boss, "zone": av["area_name"], "entered": True, "done": done_i is not None,
            "split": clock[done_i] if done_i is not None else None,
            "level": level_at(character_id, done_v["start_utc"]) if done_v else None,
            "time_s": sum(v["active_s"] or 0 for _, v in arena_v),
            "deaths": sum(deaths_by_visit.get(v["id"], 0) for _, v in arena_v),
        })

    if base["completed"] and bosses and not bosses[-1]["done"] and bosses[-1]["entered"]:
        # the epilogue (proof for the last Kitava) is where the campaign ends
        bosses[-1].update(done=True, split=total, level=acts[-1]["level_end"] if acts else None)
    # Trials of Ascendancy (Izaro's line when one is finished)
    trial_kills = {r[0]: r[1] for r in con.execute(
        "SELECT boss, MIN(ts_utc) FROM boss_kill WHERE character_id=? AND boss LIKE 'Trial: %' AND ts_utc<=? GROUP BY boss",
        (character_id, cut))}
    trials = []
    for i, (diff, aid, zone) in enumerate(TRIALS):
        name = f"Trial: {diff} · {zone}"
        ts = trial_kills.get(name)
        zv = [v for v in visits if v["area_id"] == aid and (not ts or v["start_utc"] <= ts)]
        late = bool(ts and base["completed"] and ts >= base["end"])
        trials.append({"lab": diff, "zone": zone, "act": int(aid.split("_")[1]), "done": bool(ts),
                       "entered": bool(zv), "after_campaign": late, "ts_utc": ts,
                       "split": clock_at(ts) if ts and not late else None,
                       "level": level_at(character_id, ts) if ts else None,
                       "time_s": sum(v["active_s"] or 0 for v in zv),
                       "deaths": sum(deaths_by_visit.get(v["id"], 0) for v in zv)})

    # ---- passive points from quests
    qpts = _rows(con, """SELECT q.ts_utc, q.area_id, q.points FROM quest_point q LEFT JOIN area_visit v ON v.id=q.visit_id
                         WHERE COALESCE(v.character_id, q.character_id)=? AND q.ts_utc<=? ORDER BY q.ts_utc""", (character_id, qcut))
    rep_rows = _rows(con, """SELECT r.report_utc, r.quest, r.points FROM quest_report r LEFT JOIN area_visit v ON v.id=r.visit_id
                             WHERE COALESCE(v.character_id, r.character_id)=? AND r.report_utc<=? ORDER BY r.report_utc""",
                     (character_id, qcut))
    report_utc = rep_rows[-1]["report_utc"] if rep_rows else None
    report = {r["quest"]: r["points"] for r in rep_rows if r["report_utc"] == report_utc}
    got_by_town = defaultdict(list)
    for q in qpts:
        got_by_town[q["area_id"]].extend([q["ts_utc"]] * (q["points"] or 1))
    # Deal with the Bandits: helping one gives a stat instead of the point
    br = con.execute("""SELECT b.reward, b.ts_utc FROM bandit_reward b LEFT JOIN area_visit v ON v.id=b.visit_id
                        WHERE COALESCE(v.character_id, b.character_id)=? AND b.ts_utc<=? ORDER BY b.ts_utc DESC LIMIT 1""",
                     (character_id, qcut)).fetchone()
    helped = None
    if br:
        r = br[0].lower()
        who = "Alira" if "resist" in r else "Oak" if "life" in r else "Kraityn" if "speed" in r else "a bandit"
        helped = {"bandit": who, "reward": br[0], "ts_utc": br[1]}
    town_quests = defaultdict(list)
    for qd in QUEST_PASSIVES:
        if helped and qd[1] == "Deal with the Bandits":
            continue                 # no point to expect from this one
        town_quests[qd[3]].append(qd)
    acts_finished = {a["act"] for a in acts if a["finished"]}
    quests = []
    for act, name, pts_, town, npc, how in QUEST_PASSIVES:
        in_town = town_quests[town]
        need = sum(q[2] for q in in_town)
        got = got_by_town.get(town, [])
        when = None
        # from the log: points received in the town that hands this quest out
        reached = act in acts_finished
        if len(got) >= need:
            status = "done"
        elif not got:
            status = "missed" if reached else "pending"
        else:
            status = "maybe"          # this town gave some of its points, not all
        source = "log"
        if helped and name == "Deal with the Bandits":
            status = "helped"
        # /passives (when you've typed it) names each quest exactly
        if report_utc:
            a_ = next((x for x in acts if x["act"] == act and x["finished"]), None)
            act_end = a_["end_utc"] if a_ else None
            if report.get(name, 0) > 0:
                status, source = "done", "/passives"
            elif status not in ("done", "helped") and (name in report or (act_end and report_utc >= act_end)):
                status, source = ("missed" if reached else "pending"), "/passives"
        if status == "done" and len(in_town) == 1 and got:
            when = got[0]
        late = bool(when and base["completed"] and when >= base["end"])
        extra = {"helped": f"Helped {helped['bandit']}", "reward": helped["reward"]} if status == "helped" else {}
        quests.append({**extra, "act": act, "quest": name, "points": pts_, "npc": npc, "how": how, "status": status,
                       "town": TOWN_NAMES.get(town, town),
                       "source": source, "ts_utc": when, "after_campaign": late,
                       "split": clock_at(when) if when and not late else None,
                       "level": level_at(character_id, when) if when else None})
    total_qp = sum(q[2] for q in QUEST_PASSIVES)
    got_qp = sum(q["points"] for q in quests if q["status"] == "done")
    got_qp += sum(len(got_by_town.get(t, [])) for t in {qd[3] for qd in QUEST_PASSIVES}
                  if any(q["status"] == "maybe" for q, qd in zip(quests, QUEST_PASSIVES) if qd[3] == t))
    if helped and any(q["status"] == "helped" for q in quests):
        total_qp -= 1               # that point was traded for the bandit's reward
    passives = {"got": min(got_qp, total_qp), "total": total_qp, "helped": helped, "quests": quests, "report_utc": report_utc,
                "in_campaign": sum(q["points"] or 1 for q in qpts if not base["completed"] or q["ts_utc"] <= base["end"])}

    hours = (total or 0) / 3600
    zones_entered = len({v["area_id"] for v in visits if v["kind"] == "campaign"})
    acts_done = sum(1 for a in acts if a["finished"])
    level_end = acts[-1]["level_end"] if acts else 1
    deaths_total = sum(a["deaths"] for a in acts)
    rates = {"zones_per_h": zones_entered / hours if hours else None,
             "acts_per_h": acts_done / hours if hours else None,
             "levels_per_h": (level_end - 1) / hours if hours else None,
             "deaths_per_h": deaths_total / hours if hours else None,
             "zones": zones_entered, "acts_done": acts_done}
    return {**{k: base[k] for k in ("character_id", "character", "class", "league", "start", "end", "completed",
                                    "after_league_start_s", "wall_s")},
            "play_s": total, "deaths": sum(a["deaths"] for a in acts),
            "level_end": acts[-1]["level_end"] if acts else 1, "acts": acts, "labs": labs,
            "progress": 1.0 if base["completed"] else progress, "current_zone": last_zone["area_name"] if last_zone else None,
            "bosses": bosses, "trials": trials, "rates": rates, "passives": passives,
            "current_act": next((a["act"] for a in acts if not a["finished"]), None)}


def campaign_characters(con, league: str | None) -> list[dict]:
    """Characters in a league that started the campaign, league starter first."""
    if not league:
        return []
    return _rows(con, """
        SELECT c.id, c.name, c.class, c.level, MIN(v.start_utc) AS started FROM v_own_character c
        JOIN area_visit v ON v.character_id=c.id AND v.area_id='1_1_1'
        WHERE c.league=? GROUP BY c.id ORDER BY started""", (league,))


def mapping_progress(con, config: Config, league: str, status: dict | None = None) -> dict:
    """League start endgame for the mapping character (see mapping_character):
    tier progression and milestones, with the league day and that character's
    play time when each was reached."""
    mchar = mapping_character(con, league)
    own = [mchar] if mchar else []
    lg = next((l for l in config.leagues if l.name == league), None)
    lg_start = lg.start.strftime("%Y-%m-%dT%H:%M:%SZ") if lg else None
    if not own:
        return {"milestones": [], "tiers": [], "kpis": {}}
    status = status or league_start_status(con, config, league)
    # League start is over at the last Voidstone or after league_start_days:
    # nothing after that moment counts on this page.
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = status.get("end_utc")
    cut = end if end and end <= now else None
    lim = cut or "9999"
    q = ",".join("?" * len(own))
    names = {r[0]: r[1] for r in con.execute(f"SELECT id, name FROM character WHERE id IN ({q})", own)}
    ids_by_name = {v: k for k, v in names.items()}
    vis = con.execute(f"SELECT start_utc, active_s FROM v_visit_active WHERE character_id IN ({q}) AND start_utc<=? ORDER BY start_utc",
                      [*own, lim]).fetchall()
    starts, cum, t = [], [], 0.0
    for s, a in vis:
        t += a or 0
        starts.append(s)
        cum.append(t)

    def played_at(ts):
        import bisect
        i = bisect.bisect_right(starts, ts)
        return cum[i - 1] if i else 0.0
    level_at = _level_lookup(con, own)

    def stamp(ts, cid=None, **extra):
        if ts and cut and ts > cut:
            ts = None                  # happened after league start ended
        return {"ts_utc": ts, "days": _secs(lg_start, ts) / 86400 if ts and lg_start else None,
                "played_s": played_at(ts) if ts else None, "character": names.get(cid),
                "level": level_at(cid, ts) if ts and cid else None, "done": bool(ts), **extra}

    runs_ = _rows(con, f"""
        SELECT r.id, r.character_id, r.tier, r.area_name, r.start_utc,
               (SELECT COALESCE(SUM(v.active_s),0) FROM v_visit_active v WHERE v.run_id=r.id) AS active_s,
               (SELECT COUNT(*) FROM death d WHERE d.run_id=r.id) AS deaths
        FROM run r WHERE r.kind='map' AND r.character_id IN ({q}) AND r.start_utc<=? ORDER BY r.start_utc""", [*own, lim])
    tiers = []
    top = max([r["tier"] or 0 for r in runs_] or [0])
    for tier in range(1, max(16, top) + 1):
        rs = [r for r in runs_ if r["tier"] == tier]
        first = rs[0] if rs else None
        done = [r for r in rs if r["active_s"]]
        tiers.append({"tier": tier, **stamp(first["start_utc"] if first else None, first["character_id"] if first else None),
                      "first_map": first["area_name"] if first else None, "maps": len(rs),
                      "avg_s": _avg([r["active_s"] for r in done]), "fastest_s": min([r["active_s"] for r in done], default=None),
                      "deaths": sum(r["deaths"] for r in rs)})

    ms: list[dict] = []
    starter = status["starter"]
    row = stamp(status["campaign_end"], starter)
    if starter != mchar:
        row["played_s"] = None      # that was another character's clock
        row["character"], row["level"] = status.get("campaign_name"), None
    ms.append({"group": "Atlas", "name": "Campaign finished", **row})

    def first_run(pred):
        return next((r for r in runs_ if pred(r)), None)
    for label, pred in [("First map", lambda r: True),
                        ("First yellow map (T6)", lambda r: (r["tier"] or 0) >= 6),
                        ("First red map (T11)", lambda r: (r["tier"] or 0) >= 11),
                        ("First T16 map", lambda r: (r["tier"] or 0) >= 16)]:
        r = first_run(pred)
        ms.append({"group": "Atlas", "name": label, **stamp(r["start_utc"] if r else None, r["character_id"] if r else None,
                                                            detail=r["area_name"] if r else None)})
    if top >= 17:
        r = first_run(lambda r: (r["tier"] or 0) >= 17)
        ms.append({"group": "Atlas", "name": "First Nightmare map", **stamp(r["start_utc"], r["character_id"], detail=r["area_name"])})

    lvl_rows = con.execute(f"SELECT character_id, level, ts_utc FROM level_up WHERE character_id IN ({q}) AND ts_utc<=? ORDER BY ts_utc",
                           [*own, lim]).fetchall()
    for n in (70, 75, 80, 85, 90):
        hit = next((r for r in lvl_rows if r[1] >= n), None)
        ms.append({"group": "Character", "name": f"Level {n}", **stamp(hit[2] if hit else None, hit[0] if hit else None)})

    bp = boss_progress(con, config, league, mchar)
    for boss in ("Merciless Labyrinth", "Eternal Labyrinth"):
        b = bp.get(boss) or {}
        fk = b.get("first_kill")
        cid = ids_by_name.get(fk["character"]) if fk else None
        ms.append({"group": "Labyrinth", "name": boss, **stamp(fk["ts_utc"] if fk else None, cid),
                   "attempts": b.get("attempts"), "deaths": b.get("deaths")})
    vs = voidstones(con, config, league, mchar, bp=bp)
    if cut:
        for st_ in vs["voidstones"]:
            if st_["when"] and st_["when"] > cut:
                st_.update(obtained=False, when=None, likely=False)
        vs["obtained"] = sum(x["obtained"] for x in vs["voidstones"])
    for s in vs["voidstones"]:
        for st in s["steps"]:
            if st.get("count_only"):
                continue
            b = bp.get(st["boss"]) or {}
            fk = b.get("first_kill")
            cid = ids_by_name.get(fk["character"]) if fk else None
            ms.append({"group": s["name"], "name": st["boss"], **stamp(fk["ts_utc"] if fk else None, cid),
                       "attempts": b.get("attempts"), "deaths": b.get("deaths"), "kills": b.get("kills"),
                       "likely": b.get("detected") == "likely"})
        ms.append({"group": s["name"], "name": f"{s['name']} obtained", "voidstone": True, **stamp(s["when"]),
                   "likely": s["likely"]})

    total_played = cum[-1] if cum else 0.0
    camp_played = played_at(status["campaign_end"]) if status["campaign_end"] else None

    # ---- since entering maps: the first map this character ran
    first = runs_[0] if runs_ else None
    entered = None
    rates = {"maps_per_h": None, "tiers_per_h": None, "levels_per_h": None, "deaths_per_h": None}
    bar = []
    if first:
        e_ts = first["start_utc"]
        e_played = played_at(e_ts)
        map_s = max(total_played - e_played, 0.0)
        lvl_in = level_at(mchar, e_ts)
        lvl_now = level_at(mchar, cut)
        deaths_since = con.execute("SELECT COUNT(*) FROM death WHERE character_id=? AND ts_utc>=? AND ts_utc<=?",
                                   (mchar, e_ts, lim)).fetchone()[0]
        entered = {"ts_utc": e_ts, "tier": first["tier"], "area": first["area_name"],
                   "after_launch_s": _secs(lg_start, e_ts) if lg_start else None, "level": lvl_in,
                   "played_s": map_s, "start_played_s": e_played}
        # tiers: when each was first reached, on this character's play clock
        reach = {}
        for r in runs_:
            t_ = min(r["tier"] or 0, 16)        # Nightmare (T17) maps count as the top of the climb
            if t_ and t_ not in reach:
                reach[t_] = played_at(r["start_utc"])
        hours = map_s / 3600 if map_s >= 600 else None        # under 10 minutes the rates are noise
        top_t = max(reach) if reach else None
        if hours:
            rates["maps_per_h"] = len(runs_) / hours
            rates["levels_per_h"] = ((lvl_now or 0) - (lvl_in or 0)) / hours if lvl_in and lvl_now else None
            rates["deaths_per_h"] = deaths_since / hours
        # tier pace: tiers climbed up to the moment the highest tier was first reached
        # (so it doesn't sag while you farm T16s afterwards)
        if top_t and first["tier"] and top_t > first["tier"]:
            climb_s = reach[top_t] - e_played
            if climb_s > 0:
                rates["tiers_per_h"] = (top_t - first["tier"]) / (climb_s / 3600)
        rates.update(climb_from=first["tier"], climb_to=top_t,
                     climb_s=(reach[top_t] - e_played) if top_t else None,
                     levels=((lvl_now or 0) - (lvl_in or 0)) if lvl_in and lvl_now else None, deaths=deaths_since,
                     maps=len(runs_))
        # progress bar T1-T16: how long you stayed at each tier before the next one
        reached = sorted(reach)
        for tier in range(1, 17):
            if tier in reach:
                nxt = next((x for x in reached if x > tier), None)
                end = reach[nxt] if nxt else total_played
                bar.append({"tier": tier, "state": "done" if nxt else "current", "time_s": max(end - reach[tier], 0.0)})
            elif top_t and tier < top_t:
                bar.append({"tier": tier, "state": "skipped", "time_s": None})
            else:
                bar.append({"tier": tier, "state": "pending", "time_s": None})

    return {
        "status": status, "milestones": ms, "tiers": tiers, "character_id": mchar, "character": names.get(mchar),
        "entered": entered, "rates": rates, "bar": bar, "voidstones": vs,
        "crucibles_ran": sum(1 for t_ in (bp.get("The Maven's Crucible") or {}).get("repeat_kills") or [] if not cut or t_ <= cut),
        "ended": {"ts_utc": cut, "reason": status.get("end_reason")} if cut else None,
        "ends_utc": end if end and not cut else None, "ends_reason": status.get("end_reason"),
        "kpis": {
            "voidstones": vs["obtained"], "voidstones_total": vs["total"], "top_tier": top or None,
            "maps": len(runs_), "map_deaths": sum(r["deaths"] for r in runs_),
            "played_s": total_played,
            "mapping_played_s": entered["played_s"] if entered else (total_played - camp_played if camp_played is not None else None),
            "level": max([level_at(c, cut) for c in own] or [None]),
            "days": _secs(lg_start, cut or now) / 86400 if lg_start else None,
        },
    }


def map_checklist(con, league: str, manual: dict | None = None, until: str | None = None) -> dict:
    """Every Atlas map and unique map for the league, with the first time any of
    your characters in the league ran it. `manual` is {map name: [done, ts]}
    from ticking boxes by hand, which wins over the log."""
    from .atlas_maps import ATLAS_POOLS, NOT_REGULAR, UNIQUE_MAPS
    manual = manual or {}
    rows = _rows(con, """
        SELECT v.area_id, v.area_name, v.start_utc, c.name AS character, r.tier
        FROM area_visit v JOIN v_own_character c ON c.id=v.character_id
        LEFT JOIN run r ON r.id=v.run_id
        WHERE c.league=? AND (v.area_id LIKE 'MapWorlds%' OR v.area_id LIKE 'Synthesis_Map%') AND v.start_utc<=?
        ORDER BY v.start_utc""", (league, until or "9999"))
    first_by_id, first_by_name = {}, {}
    for r in rows:
        first_by_id.setdefault(r["area_id"], r)
        if r["area_id"].startswith("MapWorlds") and not any(x in r["area_id"] for x in NOT_REGULAR):
            first_by_name.setdefault(r["area_name"], r)
    pool = ATLAS_POOLS.get(league)
    names = sorted(set(pool or ()) | set(first_by_name))

    def item(name, hit, extra=False):
        m = manual.get(name)
        if m is not None:
            done, ts, how = bool(m[0]), (m[1] if m[0] else None), "manual"
        else:
            done, ts, how = bool(hit), hit["start_utc"] if hit else None, "log" if hit else None
        return {"name": name, "done": done, "ts_utc": ts, "how": how, "ran_utc": hit["start_utc"] if hit else None,
                "tier": hit["tier"] if hit else None, "character": hit["character"] if hit else None,
                "extra": extra}
    maps = [item(n, first_by_name.get(n), extra=bool(pool) and n not in pool) for n in names]
    uniques = []
    for name, ids in UNIQUE_MAPS:
        hits = [first_by_id[i] for i in ids if i in first_by_id]
        uniques.append(item(name, min(hits, key=lambda h: h["start_utc"]) if hits else None))
    return {"maps": maps, "uniques": uniques, "has_pool": bool(pool),
            "maps_done": sum(m["done"] for m in maps), "uniques_done": sum(u["done"] for u in uniques)}


# ---------------------------------------------------------------- mini window

def mini_status(con, config: Config, league: str | None = None, force_phase: str | None = None) -> dict:
    """Everything the always-on-top mini window shows, for the league being
    started (campaign or mapping phase) or the latest league. force_phase
    (developer mode) shows the campaign or mapping view whatever the data says."""
    status = league_start_status(con, config, league)
    if force_phase in ("campaign", "mapping", "done"):
        status = {**status, "phase": force_phase}
    lg = status["league"]
    out: dict = {"league": lg, "phase": status["phase"], "voidstones": status.get("voidstones"),
                 "voidstones_total": status.get("voidstones_total", 4)}
    if not lg:
        return out
    cid = status.get("starter")
    if status["phase"] == "campaign" or (status["phase"] != "mapping" and not status.get("mapping_char")):
        out["view"] = "campaign"
        if not cid:
            return out
        sp = campaign_splits(con, cid)
        if not sp:
            return out
        last = con.execute("""SELECT v.start_utc, v.end_utc, v.area_name, v.kind, v.session_id FROM area_visit v
                              WHERE v.character_id=? ORDER BY v.start_utc DESC LIMIT 1""", (cid,)).fetchone()
        afk = con.execute("SELECT 1 FROM afk_period WHERE session_id=? AND end_utc IS NULL LIMIT 1",
                          (last["session_id"],)).fetchone() if last else None
        acts = sp["acts"]
        cur = next((a for a in acts if not a["finished"]), None)
        done = [a for a in acts if a["finished"]]
        nxt_boss = next((b for b in sp["bosses"] if not b["done"]), None)
        nxt_trial = next((t for t in sp["trials"] if not t["done"]), None)
        open_visit = bool(last and last["end_utc"] is None and not sp["completed"])
        out["campaign"] = {
            "character": sp["character"], "class": sp["class"], "completed": sp["completed"],
            "play_s": sp["play_s"], "anchor_utc": last["start_utc"] if open_visit else None,
            "afk": bool(afk), "zone": last["area_name"] if last else None,
            "act": cur["act"] if cur else (acts[-1]["act"] if acts else None),
            "act_s": cur["time_s"] if cur else None,
            "level": sp["level_end"], "deaths": sp["deaths"], "progress": sp["progress"],
            "splits": [{"act": a["act"], "split": a["split"], "time_s": a["time_s"]} for a in done],
            "act_progress": cur["progress"] if cur else 1.0,
            "labs": [{"lab": l["lab"].split()[0], "split": l["split"], "done": bool(l["split"] is not None),
                      "time_s": l["time_s"]}
                     for l in sp["labs"]],
            "next_boss": {"boss": nxt_boss["boss"], "act": nxt_boss["act"],
                          "zone": next((z for (_, b_, z, _p) in CAMPAIGN_BOSSES if b_ == nxt_boss["boss"]), None)}
                         if nxt_boss else None,
            "next_trial": {"lab": nxt_trial["lab"], "zone": nxt_trial["zone"], "act": nxt_trial["act"]} if nxt_trial else None,
            "trials": sum(1 for t in sp["trials"] if t["done"]),
            "quest_points": sp["passives"]["got"], "quest_total": sp["passives"]["total"],
        }
        # area id -> name for the next boss's zone
        if out["campaign"]["next_boss"] and out["campaign"]["next_boss"]["zone"]:
            r = con.execute("SELECT area_name FROM area_visit WHERE area_id=? AND area_name IS NOT NULL LIMIT 1",
                            (out["campaign"]["next_boss"]["zone"],)).fetchone()
            out["campaign"]["next_boss"]["zone"] = r[0] if r else None
        return out
    # mapping (or league start finished): the mapping character's endgame
    out["view"] = "mapping"
    m = mapping_progress(con, config, lg, status)
    k = m["kpis"]
    nxt = [x for x in m["milestones"] if not x["done"] and not x.get("voidstone")][:3]
    mc = m.get("character_id")
    last = con.execute("""SELECT v.start_utc, v.end_utc, v.area_name, v.session_id FROM area_visit v
                          WHERE v.character_id=? ORDER BY v.start_utc DESC LIMIT 1""", (mc,)).fetchone() if mc else None
    afk = con.execute("SELECT 1 FROM afk_period WHERE session_id=? AND end_utc IS NULL LIMIT 1",
                      (last["session_id"],)).fetchone() if last else None
    rt = m.get("rates") or {}
    # voidstones with their steps, timed on the mapping clock (play time since the first map)
    base = (m.get("entered") or {}).get("start_played_s")

    def clock(x):
        return (x["played_s"] - base) if x.get("done") and x.get("played_s") is not None and base is not None else None
    stones = []
    for s_ in (m.get("voidstones") or {}).get("voidstones") or []:
        rows = [x for x in m["milestones"] if x["group"] == s_["name"]]
        got = next((x for x in rows if x.get("voidstone")), {})
        stones.append({"name": s_["name"].replace(" Voidstone", ""), "done": s_["obtained"], "t": clock(got),
                       "steps": [{"name": x["name"] + (f" ×{x['kills']}" if (x.get("kills") or 0) > 1
                                                       and not x["name"].startswith("Maven's Crucible") else ""),
                                  "done": x["done"], "t": clock(x), "likely": x.get("likely")}
                                 for x in rows if not x.get("voidstone")]})
    out["mapping"] = {
        "anchor_utc": last["start_utc"] if last and last["end_utc"] is None and m.get("entered") and not m.get("ended") else None,
        "ended": (m.get("ended") or {}).get("ts_utc"),
        "afk": bool(afk), "zone": last["area_name"] if last else None,
        "maps_per_h": rt.get("maps_per_h"), "tiers_per_h": rt.get("tiers_per_h"),
        "bar": [b["state"] for b in m.get("bar") or []],
        "stones": stones,
        "end_reason": (m.get("ended") or {}).get("reason"),
        "character": m.get("character"), "top_tier": k.get("top_tier"), "maps": k.get("maps"),
        "voidstones": k.get("voidstones"), "voidstones_total": k.get("voidstones_total"),
        "level": k.get("level"), "mapping_s": k.get("mapping_played_s"), "deaths": rt.get("deaths", k.get("map_deaths")),
        "next": [{"group": x["group"], "name": x["name"]} for x in nxt],
    }
    return out


# ---------------------------------------------------------------- profile snapshots

def snapshot_triggers(con, config: Config, league: str | None = None) -> list[dict]:
    """League start moments that call for a profile snapshot:
    campaign - the end of each act (League Start Campaign's character);
    mapping  - every 10th level, first yellow (T6) and red (T11) map, each
               Voidstone (League Start Mapping's character).
    Each: {key, label, character_id, character, event_utc}. Nothing once
    league start has been over for a while."""
    st = league_start_status(con, config, league)
    lg = st["league"]
    if not lg:
        return []
    now = datetime.now(timezone.utc)
    if st["phase"] == "done":
        end = st.get("end_utc")
        if not end or (now - datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() > 3600:
            return []
    names = {r[0]: r[1] for r in con.execute("SELECT id, name FROM character WHERE league_id=(SELECT id FROM league WHERE name=?)",
                                              (lg,))}
    out: list[dict] = []

    def add(key, label, cid, ts):
        if cid and ts and names.get(cid):
            out.append({"key": key, "label": label, "character_id": cid, "character": names[cid], "event_utc": ts})
    cid = st.get("starter")
    if cid:
        sp = campaign_splits(con, cid)
        for a in (sp or {}).get("acts") or []:
            if a.get("finished") and a.get("end_utc"):
                add(f"act{a['act']}", f"Act {a['act']} finished", cid, a["end_utc"])
    mc = st.get("mapping_char")
    if mc and st.get("campaign_end"):
        runs_ = con.execute("SELECT start_utc, tier FROM run WHERE character_id=? AND kind='map' AND tier IS NOT NULL "
                            "ORDER BY start_utc", (mc,)).fetchall()
        for key, label, t in (("t6", "First yellow map (T6)", 6), ("t11", "First red map (T11)", 11)):
            r = next((r for r in runs_ if r[1] >= t), None)
            if r:
                add(key, label, mc, r[0])
        first_map = runs_[0][0] if runs_ else None
        if first_map:
            for lvl, ts in con.execute("SELECT level, MIN(ts_utc) FROM level_up WHERE character_id=? AND level % 10 = 0 "
                                       "AND ts_utc>=? GROUP BY level ORDER BY level", (mc, first_map)):
                add(f"level{lvl}", f"Level {lvl}", mc, ts)
        vs = voidstones(con, config, lg)
        for s in vs.get("voidstones") or []:
            if s.get("obtained") and s.get("when"):
                add(f"voidstone:{s['name']}", s["name"], mc, s["when"])
    return out
