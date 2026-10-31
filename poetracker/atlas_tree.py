"""The real Atlas passive tree, drawn from Grinding Gear Games' official export.

GGG publishes the Atlas tree (layout, node text and art) for tool makers at
github.com/grindinggear/atlastree-export. Nothing of it ships with PoE Tracker:
the first time the Atlas Tree page opens, the data and the few sprite sheets it
needs are downloaded into the data folder (atlastree/) and refreshed now and
then, so the tree follows each league's changes.

The log names atlas points by their internal id ("atlas_breach_4_4"); the
export keys nodes by a number. RePoE (github.com/repoe-fork), a community
export of the game data, has both, so it's downloaded once per tree version
to link them.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
import urllib.request
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

GGG = "https://raw.githubusercontent.com/grindinggear/atlastree-export/master/"
REPOE = "https://raw.githubusercontent.com/repoe-fork/repoe-fork.github.io/master/data/passive_skill_trees/Atlas.json"
ZOOM = "0.3835"                       # the sharpest sprite sheets the export has
SHEETS = ("normalActive", "normalInactive", "notableActive", "notableInactive", "keystoneActive",
          "keystoneInactive", "wormholeActive", "wormholeInactive", "mastery", "groupBackground",
          "startNode", "frame", "atlasBackground")
REFRESH_S = 3 * 86400                 # look for a new tree every few days
CREDIT = ("Atlas tree data and art © Grinding Gear Games, from their official atlastree-export; node ids linked "
          "with RePoE. PoE Tracker is unofficial and not affiliated with or endorsed by Grinding Gear Games.")

# angles (degrees, clockwise from 12 o'clock) for orbits that aren't evenly spaced
ORBIT_ANGLES = {
    16: [0, 30, 45, 60, 90, 120, 135, 150, 180, 210, 225, 240, 270, 300, 315, 330],
    40: [0, 10, 20, 30, 40, 45, 50, 60, 70, 80, 90, 100, 110, 120, 130, 135, 140, 150, 160, 170, 180, 190,
         200, 210, 220, 225, 230, 240, 250, 260, 270, 280, 290, 300, 310, 315, 320, 330, 340, 350],
}

_lock = threading.Lock()
_state = {"busy": False, "error": None, "layout": None, "mtime": 0.0}


def cache_dir() -> Path:
    d = paths.data_dir() / "atlastree"
    d.mkdir(exist_ok=True)
    return d


def _get(url: str, timeout: float = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "poe-tracker (atlas tree view)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def status() -> dict:
    """{ready, busy, error}: whether the tree can be drawn yet."""
    return {"ready": (cache_dir() / "layout.json").exists(), "busy": _state["busy"], "error": _state["error"]}


def ensure() -> None:
    """Download (or refresh) the tree in the background if it's missing or old."""
    f = cache_dir() / "layout.json"
    if _state["busy"] or (f.exists() and time.time() - f.stat().st_mtime < REFRESH_S):
        return
    _state["busy"] = True
    threading.Thread(target=_download, name="atlas-tree", daemon=True).start()


def _download() -> None:
    try:
        d = cache_dir()
        raw = _get(GGG + "data.json")
        tree = json.loads(raw)
        ver = hashlib.sha1(raw).hexdigest()[:12]
        old = _read_json(d / "layout.json") or {}
        if old.get("version") == ver:
            (d / "layout.json").touch()          # unchanged: check again in a few days
            return
        for key in SHEETS:                        # only the sheets the view uses
            sheet = (tree["sprites"].get(key) or {})
            z = sheet.get(ZOOM) or (sheet[max(sheet, key=float)] if sheet else None)
            if not z:
                continue
            name = z["filename"].split("/")[-1].split("?")[0]
            tag = z["filename"].split("?")[-1]
            if not (d / name).exists() or (old.get("tags") or {}).get(name) != tag:
                (d / name).write_bytes(_get(GGG + "assets/" + name))
        ids = {}
        try:
            for v in json.loads(_get(REPOE)).get("passives", {}).values():
                if v.get("id") and v.get("hash") is not None:
                    ids[v["id"]] = str(v["hash"])
        except Exception as e:                    # names still match most points without it
            log.warning("atlas tree: couldn't get RePoE ids: %s", e)
            ids = old.get("ids") or {}
        lay = build(tree, ids)
        lay["version"] = ver
        tmp = d / "layout.json.tmp"
        tmp.write_text(json.dumps(lay, separators=(",", ":")), encoding="utf-8")
        tmp.replace(d / "layout.json")
        _state["error"] = None
    except Exception as e:
        log.warning("atlas tree download failed: %s", e)
        _state["error"] = f"Couldn't download the atlas tree ({type(e).__name__}). It will try again later."
    finally:
        _state["busy"] = False


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def layout() -> dict | None:
    f = cache_dir() / "layout.json"
    if not f.exists():
        return None
    with _lock:
        mt = f.stat().st_mtime
        if _state["layout"] is None or mt != _state["mtime"]:
            _state["layout"], _state["mtime"] = _read_json(f), mt
        return _state["layout"]


def _angle(orbit: int, index: int, per_orbit: list[int]) -> float:
    n = per_orbit[orbit]
    return ORBIT_ANGLES[n][index] if n in ORBIT_ANGLES else 360.0 * index / n


def build(tree: dict, ids: dict) -> dict:
    """Turn the export into what the page draws: node positions, links, sprites."""
    c = tree["constants"]
    radii, per = c["orbitRadii"], c["skillsPerOrbit"]
    groups, nodes = tree["groups"], tree["nodes"]
    pos: dict[str, tuple[float, float, float]] = {}
    for k, n in nodes.items():
        g = groups.get(str(n.get("group")))
        if not g:
            continue
        a = _angle(n["orbit"], n["orbitIndex"], per)
        r = radii[n["orbit"]]
        pos[k] = (g["x"] + r * math.sin(math.radians(a)), g["y"] - r * math.cos(math.radians(a)), a)

    out_nodes = []
    for k, n in nodes.items():
        if k not in pos or k == "root":
            continue
        kind = ("start" if not n.get("name") else "mastery" if n.get("isMastery") else
                "keystone" if n.get("isKeystone") else "notable" if n.get("isNotable") else
                "wormhole" if n.get("isWormhole") else "normal")
        out_nodes.append({"h": k, "x": round(pos[k][0], 1), "y": round(pos[k][1], 1), "k": kind,
                          "g": n.get("group"), "n": n.get("name") or "", "i": n.get("icon") or "",
                          "s": n.get("stats") or [], "f": n.get("flavourText") or []})

    links, seen = [], set()
    for k, n in nodes.items():
        for o in n.get("out", []):
            pair = tuple(sorted((k, o)))
            if pair in seen or k not in pos or o not in pos:
                continue
            seen.add(pair)
            a, b = nodes[k], nodes[o]
            if a.get("isMastery") or b.get("isMastery") or (a.get("isWormhole") and b.get("isWormhole")):
                continue
            x1, y1, a1 = pos[k]
            x2, y2, a2 = pos[o]
            if a.get("group") == b.get("group") and a["orbit"] == b["orbit"] and a["orbit"] > 0:
                r = radii[a["orbit"]]
                sweep = 1 if (a2 - a1) % 360 <= 180 else 0
                d = f"M{x1:.1f} {y1:.1f}A{r} {r} 0 0 {sweep} {x2:.1f} {y2:.1f}"
            else:
                d = f"M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}"
            links.append({"a": k, "b": o, "d": d})

    sprites = {}
    for key in SHEETS:
        sheet = tree["sprites"].get(key) or {}
        z = sheet.get(ZOOM) or (sheet[max(sheet, key=float)] if sheet else None)
        if z:
            sprites[key] = {"file": z["filename"].split("/")[-1].split("?")[0], "w": z["w"], "h": z["h"],
                            "c": z["coords"], "zoom": float(ZOOM) if sheet.get(ZOOM) else float(max(sheet, key=float))}
    bgs = [{"x": g["x"] + (g["background"].get("offsetX") or 0), "y": g["y"] + (g["background"].get("offsetY") or 0),
            "img": g["background"]["image"]} for g in groups.values() if g.get("background")]
    tags = {}
    for key in SHEETS:
        sheet = tree["sprites"].get(key) or {}
        z = sheet.get(ZOOM) or (sheet[max(sheet, key=float)] if sheet else None)
        if z:
            tags[z["filename"].split("/")[-1].split("?")[0]] = z["filename"].split("?")[-1]
    return {"nodes": out_nodes, "links": links, "sprites": sprites, "group_bgs": bgs, "ids": ids, "tags": tags,
            "bounds": [tree["min_x"], tree["min_y"], tree["max_x"], tree["max_y"]],
            "points": (tree.get("points") or {}).get("totalPoints")}


def match(lay: dict, allocated: list[dict]) -> tuple[dict[str, str], list[dict]]:
    """Link the log's allocated points to tree nodes: ({node: since}, unmatched)."""
    by_hash = {n["h"]: n for n in lay["nodes"]}
    by_name: dict[str, list[str]] = {}
    for n in lay["nodes"]:
        by_name.setdefault(n["n"], []).append(n["h"])
    got, missing = {}, []
    for a in allocated:
        h = lay["ids"].get(a["node_id"])
        if h not in by_hash or (a.get("name") and by_hash[h]["n"] != a["name"]):
            cand = [x for x in by_name.get(a.get("name") or "", []) if x not in got]
            h = cand[0] if len(cand) == 1 else None
        if h:
            got[h] = a["since"]
        else:
            missing.append(a)
    return got, missing
