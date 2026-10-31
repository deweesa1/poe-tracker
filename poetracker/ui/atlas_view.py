"""Draws the Atlas passive tree as one SVG, with your allocated points lit up.
Panning, zooming and the hover card are handled in the browser (layout.py)."""
from __future__ import annotations

import html

from .. import atlas_tree
from . import fmt

_cache: dict = {}

FRAMES = {"normal": ("PSSkillFrameActive", "PSSkillFrameHighlighted", "PSSkillFrame"),
          "notable": ("NotableFrameAllocated", "NotableFrameCanAllocate", "NotableFrameUnallocated"),
          "keystone": ("KeystoneFrameAllocated", "KeystoneFrameCanAllocate", "KeystoneFrameUnallocated"),
          "wormhole": ("WormholeFrameAllocated", "WormholeFrameCanAllocate", "WormholeFrameUnallocated")}

HIT = {"normal": 52, "notable": 76, "keystone": 108, "wormhole": 140}     # hover area, tree units


def svg(lay: dict, got: dict[str, str]) -> str:
    """The whole tree. `got` maps allocated node -> when it was allocated."""
    key = (lay.get("version"), tuple(sorted(got.items())))
    if key in _cache:
        return _cache[key]
    sp = lay["sprites"]
    esc = html.escape
    defs = "".join(f'<image id="pt-sh-{k}" href="/atlastree/{s["file"]}" width="{s["w"]}" height="{s["h"]}"/>'
                   for k, s in sp.items())

    def sprite(sheet: str, name: str, cx: float, cy: float, scale: float = 1.0, extra: str = "") -> str:
        s = sp.get(sheet)
        c = s and s["c"].get(name)
        if not c:
            return ""
        w, h = c["w"] / s["zoom"] * scale, c["h"] / s["zoom"] * scale
        return (f'<svg x="{cx - w / 2:.0f}" y="{cy - h / 2:.0f}" width="{w:.0f}" height="{h:.0f}" '
                f'viewBox="{c["x"]} {c["y"]} {c["w"]} {c["h"]}" preserveAspectRatio="none"{extra}>'
                f'<use href="#pt-sh-{sheet}"/></svg>')

    nodes = {n["h"]: n for n in lay["nodes"]}
    neigh: dict[str, set] = {}
    for ln in lay["links"]:
        neigh.setdefault(ln["a"], set()).add(ln["b"])
        neigh.setdefault(ln["b"], set()).add(ln["a"])
    start = next((n["h"] for n in lay["nodes"] if n["k"] == "start"), None)
    on = set(got)
    if start:
        on.add(start)
    near = {o for h in on for o in neigh.get(h, ())} - on
    groups_on = {nodes[h]["g"] for h in got if h in nodes}

    x0, y0, x1, y1 = lay["bounds"]
    pad = 900
    vb = (x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
    out = [f'<svg class="pt-atlas-svg" xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(f"{v:.0f}" for v in vb)}" '
           f'data-vb="{" ".join(f"{v:.0f}" for v in vb)}" preserveAspectRatio="xMidYMid meet"><defs>{defs}</defs>']
    bg = sp.get("atlasBackground")
    if bg:
        out.append(f'<svg x="{vb[0]:.0f}" y="{vb[1]:.0f}" width="{vb[2]:.0f}" height="{vb[3]:.0f}" '
                   f'viewBox="0 0 {bg["w"]} {bg["h"]}" preserveAspectRatio="xMidYMid slice" opacity=".55">'
                   f'<use href="#pt-sh-atlasBackground"/></svg>')
    for g in lay["group_bgs"]:
        out.append(sprite("groupBackground", g["img"], g["x"], g["y"]))
    if start:
        n = nodes[start]
        out.append(sprite("startNode", "AtlasPassiveSkillScreenStart", n["x"], n["y"]))
    # links: plain first, then the ones next to your points, then yours on top
    tiers = {0: [], 1: [], 2: []}
    for ln in lay["links"]:
        t = (ln["a"] in on) + (ln["b"] in on)
        tiers[t].append(ln["d"])
    for t, cls in ((0, "l0"), (1, "l1"), (2, "l2")):
        if tiers[t]:
            out.append(f'<path class="{cls}" d="{"".join(tiers[t])}"/>')
    for n in lay["nodes"]:
        k = n["k"]
        if k == "start":
            continue
        h, x, y = n["h"], n["x"], n["y"]
        if k == "mastery":
            out.append(sprite("mastery", n["i"], x, y, 1.0, "" if n["g"] in groups_on else ' opacity=".4"'))
            continue
        state = 0 if h in on else 1 if h in near else 2
        sheet = ("wormhole" if k == "wormhole" else k) + ("Active" if state == 0 else "Inactive")
        icon = "Wormhole" if k == "wormhole" else n["i"]
        tip = ' data-s="' + esc("\n".join(n["s"])) + '"' if n["s"] else ""
        when = f' data-a="{esc("Allocated " + fmt.when(got[h]))}"' if h in got else ""
        out.append(f'<g class="nd{" on" if state == 0 else ""}" data-n="{esc(n["n"])}"{tip}{when}>'
                   + sprite(sheet, icon, x, y) + sprite("frame", FRAMES[k][state], x, y)
                   + f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{HIT[k]}" fill="transparent"/></g>')
    out.append("</svg>")
    res = "".join(out)
    if len(_cache) > 6:
        _cache.clear()
    _cache[key] = res
    return res


def credit() -> str:
    return atlas_tree.CREDIT
