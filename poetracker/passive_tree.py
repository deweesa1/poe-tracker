"""The character passive tree, from Grinding Gear Games' official
skilltree-export (github.com/grindinggear/skilltree-export).

Downloaded the first time a profile snapshot is opened (not shipped with the
app) into the data folder (passivetree/): a name index (node number -> name,
kind, ascendancy, stats; mastery effect texts), the drawing layout (positions,
links, group backgrounds, class starts, ascendancies) and the sprite sheets
the drawing uses. Refreshed every few days.
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
from .atlas_tree import _angle

log = logging.getLogger(__name__)

RAW = "https://raw.githubusercontent.com/grindinggear/skilltree-export/master/"
ZOOM = "0.3835"
SHEETS = ("normalActive", "normalInactive", "notableActive", "notableInactive", "keystoneActive", "keystoneInactive",
          "masteryInactive", "masteryActiveSelected", "ascendancy", "startNode", "groupBackground", "frame",
          "jewel", "background")
REFRESH_S = 3 * 86400
FORMAT = 2                     # bump when build_layout() changes
_state = {"busy": False, "error": None, "index": None, "mtime": 0.0, "layout": None, "lmtime": 0.0}


def cache_dir() -> Path:
    d = paths.data_dir() / "passivetree"
    d.mkdir(exist_ok=True)
    return d


def _file() -> Path:
    return cache_dir() / "index.json"


def ensure() -> None:
    f, lf = _file(), cache_dir() / "layout.json"
    if _state["busy"] or (f.exists() and lf.exists() and time.time() - lf.stat().st_mtime < REFRESH_S
                          and layout() is not None):
        return
    _state["busy"] = True
    threading.Thread(target=_download, daemon=True, name="passive-tree").start()


def _get(url: str, timeout: float = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "poe-tracker (passive tree view)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _sheet(tree: dict, key: str) -> dict | None:
    sheet = tree["sprites"].get(key) or {}
    return sheet.get(ZOOM) or (sheet[max(sheet, key=float)] if sheet else None)


def _download() -> None:
    try:
        d = cache_dir()
        raw = _get(RAW + "data.json")
        tree = json.loads(raw)
        ver = hashlib.sha1(raw).hexdigest()[:12]
        old = _read(d / "layout.json") or {}
        if old.get("version") != ver or old.get("format") != FORMAT:
            for key in SHEETS:
                z = _sheet(tree, key)
                if not z:
                    continue
                name, tag = z["filename"].split("/")[-1].split("?")[0], z["filename"].split("?")[-1]
                if not (d / name).exists() or (old.get("tags") or {}).get(name) != tag:
                    (d / name).write_bytes(_get(RAW + "assets/" + name))
            lay = build_layout(tree)
            lay["version"], lay["format"] = ver, FORMAT
            _write(d / "layout.json", lay)
            _write(_file(), build(tree))
        else:
            (d / "layout.json").touch()
            _file().touch()
        _state["error"] = None
    except Exception as e:
        log.warning("passive tree download failed: %s", e)
        _state["error"] = f"Couldn't download the passive tree ({type(e).__name__}). It will try again later."
    finally:
        _state["busy"] = False


def _write(p: Path, data) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def build(tree: dict) -> dict:
    nodes, effects = {}, {}
    for k, n in tree["nodes"].items():
        if k == "root":
            continue
        kind = ("keystone" if n.get("isKeystone") else "mastery" if n.get("isMastery") else
                "jewel" if n.get("isJewelSocket") else "notable" if n.get("isNotable") else
                "start" if n.get("classStartIndex") is not None else "normal")
        nodes[k] = [n.get("name") or "", kind, n.get("ascendancyName") or "", n.get("stats") or []]
        for e in n.get("masteryEffects") or []:
            effects[str(e["effect"])] = [n.get("name") or "", e.get("stats") or []]
    return {"nodes": nodes, "effects": effects}


def build_layout(tree: dict) -> dict:
    """Positions, links and sprites for drawing (see ui/tree_scene.py)."""
    c = tree["constants"]
    radii, per = c["orbitRadii"], c["skillsPerOrbit"]
    groups, nodes = tree["groups"], tree["nodes"]
    classes = [cl["name"] for cl in tree.get("classes") or []]
    pos: dict[str, tuple[float, float, float]] = {}
    for k, n in nodes.items():
        g = groups.get(str(n.get("group")))
        if not g or n.get("isProxy") or g.get("isProxy") or n.get("expansionJewel", {}).get("parent"):
            continue
        a = _angle(n["orbit"], n["orbitIndex"], per)
        r = radii[n["orbit"]]
        pos[k] = (g["x"] + r * math.sin(math.radians(a)), g["y"] - r * math.cos(math.radians(a)), a)
    out_nodes = []
    for k, n in nodes.items():
        if k not in pos:
            continue
        kind = ("start" if n.get("classStartIndex") is not None else "ascstart" if n.get("isAscendancyStart") else
                "mastery" if n.get("isMastery") else "jewel" if n.get("isJewelSocket") else
                "keystone" if n.get("isKeystone") else "notable" if n.get("isNotable") else "normal")
        nd = {"h": k, "x": round(pos[k][0], 1), "y": round(pos[k][1], 1), "k": kind, "g": n.get("group"),
              "n": n.get("name") or "", "i": n.get("icon") or "", "s": n.get("stats") or [],
              "a": n.get("ascendancyName") or ""}
        if kind == "mastery":
            nd["ai"], nd["ii"] = n.get("activeIcon") or "", n.get("inactiveIcon") or ""
        if kind == "start":
            nd["cls"] = classes[n["classStartIndex"]] if n["classStartIndex"] < len(classes) else ""
        out_nodes.append(nd)
    links, seen = [], set()
    for k, n in nodes.items():
        for o in n.get("out", []):
            pair = tuple(sorted((k, o)))
            if pair in seen or k not in pos or o not in pos:
                continue
            seen.add(pair)
            a, b = nodes[k], nodes[o]
            if a.get("isMastery") or b.get("isMastery") or (a.get("ascendancyName") or "") != (b.get("ascendancyName") or ""):
                continue
            if a.get("classStartIndex") is not None and b.get("isAscendancyStart"):
                continue
            x1, y1, a1 = pos[k]
            x2, y2, a2 = pos[o]
            if a.get("group") == b.get("group") and a["orbit"] == b["orbit"] and a["orbit"] > 0:
                r = radii[a["orbit"]]
                sweep = 1 if (a2 - a1) % 360 <= 180 else 0
                dd = f"M{x1:.0f} {y1:.0f}A{r} {r} 0 0 {sweep} {x2:.0f} {y2:.0f}"
                g = groups[str(a["group"])]
                arc = [round(g["x"], 1), round(g["y"], 1), r, a1, a2, sweep]
            else:
                dd = f"M{x1:.0f} {y1:.0f}L{x2:.0f} {y2:.0f}"
                arc = None
            links.append({"a": k, "b": o, "d": dd, "asc": a.get("ascendancyName") or "",
                          "p": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)], "c": arc})
    # group backgrounds, the way the game picks them: by the largest of orbits 1-3
    bgs = []
    asc_groups = {str(n.get("group")) for n in nodes.values() if n.get("ascendancyName")}
    for gid, g in groups.items():
        if gid in asc_groups or g.get("isProxy"):
            continue
        orbits = set(g.get("orbits") or [])
        if any(nodes.get(str(x), {}).get("classStartIndex") is not None for x in g.get("nodes") or []):
            continue
        img = ("PSGroupBackground3" if 3 in orbits else "PSGroupBackground2" if 2 in orbits else
               "PSGroupBackground1" if 1 in orbits else None)
        if img:
            bgs.append({"x": g["x"], "y": g["y"], "img": img})
    sprites, tags = {}, {}
    for key in SHEETS:
        z = _sheet(tree, key)
        if z:
            f = z["filename"].split("/")[-1].split("?")[0]
            sprites[key] = {"file": f, "w": z["w"], "h": z["h"], "c": z["coords"],
                            "zoom": float(ZOOM) if (tree["sprites"].get(key) or {}).get(ZOOM) else
                            float(max(tree["sprites"][key], key=float))}
            tags[f] = z["filename"].split("?")[-1]
    main = [n for n in out_nodes if not n["a"]]
    bounds = [min(n["x"] for n in main), min(n["y"] for n in main), max(n["x"] for n in main), max(n["y"] for n in main)]
    return {"nodes": out_nodes, "links": links, "sprites": sprites, "group_bgs": bgs, "tags": tags,
            "bounds": bounds, "jewel_slots": [str(x) for x in tree.get("jewelSlots") or []],
            "asc_base": {a["id"]: cl["name"] for cl in tree.get("classes") or [] for a in cl.get("ascendancies") or []}}


def layout() -> dict | None:
    f = cache_dir() / "layout.json"
    if not f.exists():
        return None
    mt = f.stat().st_mtime
    if _state["layout"] is None or mt != _state["lmtime"]:
        _state["layout"], _state["lmtime"] = _read(f), mt
    lay = _state["layout"]
    return lay if lay and lay.get("format") == FORMAT else None


def index() -> dict | None:
    f = _file()
    if not f.exists():
        return None
    mt = f.stat().st_mtime
    if _state["index"] is None or mt != _state["mtime"]:
        got = _read(f)
        if got is None:
            return None
        _state["index"], _state["mtime"] = got, mt
    return _state["index"]


def status() -> dict:
    return {"ready": _file().exists() and layout() is not None, "busy": _state["busy"],
            "error": _state["error"]}
