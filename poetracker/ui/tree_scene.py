"""Scenes for the canvas tree viewer (the Atlas tree and a snapshot's passive
tree). A scene is plain data: the sprite sheets, what to draw where, the links
and the hover spots. The browser draws it on a canvas (see TREE_JS in
layout.py), which keeps panning and zooming smooth even with ~3000 nodes.

Scene format:
  vb     [x, y, w, h]        whole tree;  start: the first view (or null)
  img    [url, ...]          images (sprite sheets, jewel icons)
  bg     {"i", "s": [sx,sy,sw,sh], "tile": [w,h]} tiled background, or
         {"i", "cover": [x,y,w,h], "a": alpha} stretched picture
  under  [[i, sx,sy,sw,sh, dx,dy,dw,dh, alpha, flip], ...]   drawn before links
  links  [[tier, x1,y1,x2,y2]] lines or [[tier, x1,y1,x2,y2, cx,cy,r,t1,t2,ccw]] arcs
         tier 0 = not taken, 1 = next to your points, 2 = yours
  over   like `under`, drawn after the links (nodes, frames)
  hits   [[x, y, r, tip], ...];  tips: [[title, text, note, colour], ...]
"""
from __future__ import annotations

import math

from .. import passive_tree
from . import fmt

ATLAS_FRAMES = {"normal": ("PSSkillFrameActive", "PSSkillFrameHighlighted", "PSSkillFrame"),
                "notable": ("NotableFrameAllocated", "NotableFrameCanAllocate", "NotableFrameUnallocated"),
                "keystone": ("KeystoneFrameAllocated", "KeystoneFrameCanAllocate", "KeystoneFrameUnallocated"),
                "wormhole": ("WormholeFrameAllocated", "WormholeFrameCanAllocate", "WormholeFrameUnallocated")}
PASSIVE_FRAMES = {"normal": ATLAS_FRAMES["normal"], "notable": ATLAS_FRAMES["notable"],
                  "keystone": ATLAS_FRAMES["keystone"],
                  "jewel": ("JewelFrameAllocated", "JewelFrameCanAllocate", "JewelFrameUnallocated")}
ASC_FRAMES = {"big": ("AscendancyFrameLargeAllocated", "AscendancyFrameLargeCanAllocate", "AscendancyFrameLargeNormal"),
              "small": ("AscendancyFrameSmallAllocated", "AscendancyFrameSmallCanAllocate", "AscendancyFrameSmallNormal")}
HIT = {"normal": 50, "notable": 74, "keystone": 104, "jewel": 74, "mastery": 86, "ascstart": 36, "wormhole": 130}

_cache: dict = {}


class _Scene:
    def __init__(self, lay: dict, url_prefix: str):
        self.sp = lay["sprites"]
        self.img: list[str] = []
        self.sheet_i: dict[str, int] = {}
        for k, s in self.sp.items():
            self.sheet_i[k] = len(self.img)
            self.img.append(url_prefix + s["file"])
        self.under: list = []
        self.over: list = []
        self.links: list = []
        self.hits: list = []
        self.tips: list = []

    def image(self, url: str) -> int:
        self.img.append(url)
        return len(self.img) - 1

    def sprite(self, layer: list, sheet: str, name: str, cx: float, cy: float, scale: float = 1.0,
               alpha: float = 1.0, half: bool = False) -> None:
        s = self.sp.get(sheet)
        c = s and s["c"].get(name)
        if not c:
            return
        w, h = c["w"] / s["zoom"] * scale, c["h"] / s["zoom"] * scale
        i = self.sheet_i[sheet]
        if half:                              # stored as its top half; the bottom is the mirror image
            layer.append([i, c["x"], c["y"], c["w"], c["h"], round(cx - w / 2), round(cy - h), round(w), round(h), alpha, 0])
            layer.append([i, c["x"], c["y"], c["w"], c["h"], round(cx - w / 2), round(cy), round(w), round(h), alpha, 1])
        else:
            layer.append([i, c["x"], c["y"], c["w"], c["h"], round(cx - w / 2), round(cy - h / 2), round(w), round(h), alpha, 0])

    def link(self, ln: dict, tier: int, dx: float = 0, dy: float = 0) -> None:
        x1, y1, x2, y2 = ln["p"]
        row = [tier, round(x1 + dx), round(y1 + dy), round(x2 + dx), round(y2 + dy)]
        if ln.get("c"):
            cx, cy, r, a1, a2, sweep = ln["c"]
            t1, t2 = math.radians(a1 - 90), math.radians(a2 - 90)
            row += [round(cx + dx), round(cy + dy), r, round(t1, 4), round(t2, 4), 0 if sweep else 1]
        self.links.append(row)

    def hit(self, x: float, y: float, r: float, title: str, text: str = "", note: str = "", colour: str = "") -> None:
        self.tips.append([title, text, note, colour])
        self.hits.append([round(x), round(y), r, len(self.tips) - 1])

    def out(self, vb, start=None, bg=None, extra_layers=()) -> dict:
        layers = [["d", self.under], ["l", self.links], ["d", self.over], *extra_layers]
        return {"vb": [round(v) for v in vb], "start": [round(v) for v in start] if start else None, "img": self.img,
                "bg": bg, "layers": layers, "hits": self.hits, "tips": self.tips}


def _near(lay: dict, lit: set) -> set:
    neigh: dict[str, set] = {}
    for ln in lay["links"]:
        neigh.setdefault(ln["a"], set()).add(ln["b"])
        neigh.setdefault(ln["b"], set()).add(ln["a"])
    return {o for h in lit for o in neigh.get(h, ())} - lit


# ---------------------------------------------------------------- atlas
def atlas(lay: dict, got: dict[str, str]) -> dict:
    key = ("atlas", lay.get("version"), tuple(sorted(got)))
    if key in _cache:
        return _cache[key]
    sc = _Scene(lay, "/atlastree/")
    nodes = lay["nodes"]
    start = next((n["h"] for n in nodes if n["k"] == "start"), None)
    lit = set(got) | ({start} if start else set())
    near = _near(lay, lit)
    groups_on = {n["g"] for n in nodes if n["h"] in got}
    x0, y0, x1, y1 = lay["bounds"]
    pad = 900
    vb = (x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
    bg = None
    if "atlasBackground" in sc.sp:
        s = sc.sp["atlasBackground"]
        bg = {"i": sc.sheet_i["atlasBackground"], "cover": list(vb), "s": [0, 0, s["w"], s["h"]], "a": 0.55}
    for g in lay["group_bgs"]:
        sc.sprite(sc.under, "groupBackground", g["img"], g["x"], g["y"])
    for n in nodes:
        if n["k"] == "start":
            sc.sprite(sc.under, "startNode", "AtlasPassiveSkillScreenStart", n["x"], n["y"])
    for ln in lay["links"]:
        sc.link(ln, (ln["a"] in lit) + (ln["b"] in lit))
    for n in nodes:
        k, h, x, y = n["k"], n["h"], n["x"], n["y"]
        if k == "start":
            continue
        if k == "mastery":
            sc.sprite(sc.over, "mastery", n["i"], x, y, alpha=1.0 if n["g"] in groups_on else 0.4)
            continue
        st = 0 if h in lit else 1 if h in near else 2
        sheet = ("wormhole" if k == "wormhole" else k) + ("Active" if st == 0 else "Inactive")
        sc.sprite(sc.over, sheet, "Wormhole" if k == "wormhole" else n["i"], x, y)
        sc.sprite(sc.over, "frame", ATLAS_FRAMES[k][st], x, y)
        sc.hit(x, y, HIT.get(k, 50), n["n"], "\n".join(n["s"]), ("Allocated " + fmt.when(got[h])) if h in got else "")
    res = sc.out(vb, None, bg)
    _put(key, res)
    return res


# ---------------------------------------------------------------- passive tree
def passive(snap_id: int, passives: dict, base_class: str, ascendancy: str) -> dict | None:
    lay = passive_tree.layout()
    if not lay:
        return None
    key = ("passive", lay.get("version"), snap_id)
    if key in _cache:
        return _cache[key]
    idx = passive_tree.index() or {"effects": {}}
    sc = _Scene(lay, "/passivetree/")
    nodes = lay["nodes"]
    by = {n["h"]: n for n in nodes}
    on = {str(h) for h in passives.get("hashes") or []}
    me = passives.get("mastery_effects") or {}
    pairs = me.items() if isinstance(me, dict) else [((int(v) & 0xFFFF), int(v) >> 16) for v in me]
    mastery_pick = {str(nd): str(eff) for nd, eff in pairs}
    slots = lay.get("jewel_slots") or []
    jewels = {}
    for j in passives.get("items") or []:
        x = j.get("x")
        if isinstance(x, int) and 0 <= x < len(slots):
            jewels[slots[x]] = j
    start = next((n for n in nodes if n["k"] == "start" and n.get("cls", "").lower() == (base_class or "").lower()), None)
    lit = set(on) | ({start["h"]} if start else set())

    # the ascendancy sits over the tree next to your class start, like in game
    mine = [n for n in nodes if n["a"] and n["a"].lower() == (ascendancy or "").lower()]
    off = (0.0, 0.0)
    asc_center = None
    if mine:
        astart = next((n for n in mine if n["k"] == "ascstart"), mine[0])
        lit.add(astart["h"])
        xs, ys = [n["x"] for n in mine], [n["y"] for n in mine]
        mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        bgc = sc.sp.get("ascendancy", {}).get("c", {}).get(f"Classes{mine[0]['a']}")
        rad = (bgc["w"] / sc.sp["ascendancy"]["zoom"] / 2) if bgc else 700
        sx, sy = (start["x"], start["y"]) if start else (0.0, 0.0)
        dist = math.hypot(sx, sy)
        if dist > 500:                        # toward the middle of the tree from the class start
            ux, uy = -sx / dist, -sy / dist
            cx, cy = sx + ux * (rad + 420), sy + uy * (rad + 420)
        else:                                 # Scion starts in the middle
            cx, cy = sx, sy + rad + 420
        off = (cx - mx, cy - my)
        asc_center = (cx, cy, rad)
    near = _near(lay, lit)

    x0, y0, x1, y1 = lay["bounds"]
    pad = 500
    vb = (x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
    pts = [(by[h]["x"], by[h]["y"]) for h in lit if h in by and not by[h]["a"]]
    if asc_center:
        pts += [(asc_center[0] - asc_center[2], asc_center[1] - asc_center[2]),
                (asc_center[0] + asc_center[2], asc_center[1] + asc_center[2])]
    start_vb = None
    if len(pts) > 1:
        ax0, ax1 = min(p[0] for p in pts), max(p[0] for p in pts)
        ay0, ay1 = min(p[1] for p in pts), max(p[1] for p in pts)
        w, h = max(ax1 - ax0, 3500) + 1200, max(ay1 - ay0, 2600) + 1200
        start_vb = ((ax0 + ax1) / 2 - w / 2, (ay0 + ay1) / 2 - h / 2, w, h)
    bg = None
    bgt = sc.sp.get("background", {}).get("c", {}).get("Background2")
    if bgt:
        z = sc.sp["background"]["zoom"]
        bg = {"i": sc.sheet_i["background"], "s": [bgt["x"], bgt["y"], bgt["w"], bgt["h"]],
              "tile": [round(bgt["w"] / z), round(bgt["h"] / z)]}

    for g in lay["group_bgs"]:
        sc.sprite(sc.under, "groupBackground", g["img"], g["x"], g["y"], half=g["img"] == "PSGroupBackground3")
    for n in nodes:
        if n["k"] == "start":
            name = f"center{n.get('cls', '').lower()}" if start and n["h"] == start["h"] else "PSStartNodeBackgroundInactive"
            sc.sprite(sc.under, "startNode", name, n["x"], n["y"])
    for ln in lay["links"]:
        if not ln.get("asc"):
            sc.link(ln, (ln["a"] in lit) + (ln["b"] in lit))
    for n in nodes:
        if n["a"] or n["k"] == "start":
            continue
        _passive_node(sc, n, lit, near, on, mastery_pick, idx, jewels.get(n["h"]) if n["k"] == "jewel" else None)

    extra = []
    if mine:
        cx, cy, rad = asc_center
        main_over, main_links = sc.over, sc.links
        sc.over, sc.links = [], []
        sc.sprite(sc.over, "ascendancy", f"Classes{mine[0]['a']}", cx, cy)
        asc_bg, sc.over = sc.over, []
        ids = {n["h"] for n in mine}
        hit0 = len(sc.hits)
        for ln in lay["links"]:
            if ln["a"] in ids:
                sc.link(ln, (ln["a"] in lit) + (ln["b"] in lit), off[0], off[1])
        for n in mine:
            _passive_node(sc, {**n, "x": n["x"] + off[0], "y": n["y"] + off[1]}, lit, near, on, mastery_pick, idx, None)
        extra = [["d", asc_bg], ["l", sc.links], ["d", sc.over]]
        sc.over, sc.links = main_over, main_links
    res = sc.out(vb, start_vb, bg, extra)
    if mine:
        res["cover"] = [round(asc_center[0]), round(asc_center[1]), round(asc_center[2]), hit0]
    _put(key, res)
    return res


def _passive_node(sc: _Scene, n: dict, lit: set, near: set, on: set, mastery_pick: dict, idx: dict, jewel) -> None:
    k, h, x, y = n["k"], n["h"], n["x"], n["y"]
    asc = bool(n["a"])
    st = 0 if h in lit else 1 if h in near else 2
    stats = list(n["s"])
    title, note, colour = n["n"], "", ""
    if k == "mastery":
        chosen = h in mastery_pick or h in on
        if chosen:
            sc.sprite(sc.over, "masteryActiveSelected", n.get("ai") or "", x, y)
            eff = idx["effects"].get(mastery_pick.get(h, ""))
            if eff:
                stats = list(eff[1])
                note = "Chosen mastery"
        else:
            sc.sprite(sc.over, "masteryInactive", n.get("ii") or "", x, y, alpha=0.55)
    elif k == "ascstart":
        sc.sprite(sc.over, "ascendancy", "AscendancyMiddle", x, y)
    elif k == "jewel":
        sc.sprite(sc.over, "frame", PASSIVE_FRAMES["jewel"][st], x, y)
        if jewel:
            title = " ".join(x_ for x_ in (jewel.get("name"), jewel.get("typeLine")) if x_) or title
            stats = [m if isinstance(m, str) else str(m.get("text") or m) for m in (jewel.get("explicitMods") or [])]
            note = n["n"]
            colour = {0: "#c8c8c8", 1: "#8888ff", 2: "#ffff77", 3: "#af6025"}.get(jewel.get("frameType"), "")
            if jewel.get("icon"):
                i = sc.image(jewel["icon"])
                sc.over.append([i, 0, 0, 0, 0, round(x - 38), round(y - 38), 76, 76, 1.0, 0])   # sw=0: whole image
    else:
        sheet = k + ("Active" if st == 0 else "Inactive")
        sc.sprite(sc.over, sheet, n["i"], x, y)
        if asc:
            sc.sprite(sc.over, "ascendancy", ASC_FRAMES["big" if k in ("notable", "keystone") else "small"][st], x, y)
        else:
            sc.sprite(sc.over, "frame", PASSIVE_FRAMES[k][st], x, y)
    sc.hit(x, y, HIT.get(k, 50), title, "\n".join(stats), note, colour)


def _put(key, res) -> None:
    if len(_cache) > 16:
        _cache.clear()
    _cache[key] = res
