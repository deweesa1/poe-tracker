"""Draws a character's passive tree (and its ascendancy) from a profile
snapshot, with GGG's own art: the allocated path lit, jewels in their sockets,
chosen masteries. Panning, zooming and the hover card are in layout.py.

The SVG is served from /snaptree/<id> and fetched by the page, so the large
drawing isn't re-sent every time the Characters page refreshes."""
from __future__ import annotations

import html
import json

from .. import passive_tree

esc = html.escape
_cache: dict = {}

FRAMES = {"normal": ("PSSkillFrameActive", "PSSkillFrameHighlighted", "PSSkillFrame"),
          "notable": ("NotableFrameAllocated", "NotableFrameCanAllocate", "NotableFrameUnallocated"),
          "keystone": ("KeystoneFrameAllocated", "KeystoneFrameCanAllocate", "KeystoneFrameUnallocated"),
          "jewel": ("JewelFrameAllocated", "JewelFrameCanAllocate", "JewelFrameUnallocated")}
ASC_FRAMES = {"notable": ("AscendancyFrameLargeAllocated", "AscendancyFrameLargeCanAllocate", "AscendancyFrameLargeNormal"),
              "normal": ("AscendancyFrameSmallAllocated", "AscendancyFrameSmallCanAllocate", "AscendancyFrameSmallNormal")}
HIT = {"normal": 52, "notable": 76, "keystone": 108, "jewel": 76, "mastery": 90, "ascstart": 40}


def _sprite_fn(sp: dict, prefix: str):
    def sprite(sheet: str, name: str, cx: float, cy: float, scale: float = 1.0, extra: str = "", half: bool = False) -> str:
        s = sp.get(sheet)
        c = s and s["c"].get(name)
        if not c:
            return ""
        w, h = c["w"] / s["zoom"] * scale, c["h"] / s["zoom"] * scale
        def one(y, flip):
            el = (f'<svg x="{cx - w / 2:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
                  f'viewBox="{c["x"]} {c["y"]} {c["w"]} {c["h"]}" preserveAspectRatio="none"{extra}>'
                  f'<use href="#{prefix}{sheet}"/></svg>')
            return f'<g transform="matrix(1 0 0 -1 0 {2 * cy:.0f})">{el}</g>' if flip else el
        if half:                       # the big group circle is stored as its top half
            return one(cy - h, False) + one(cy - h, True)
        return one(cy - h / 2, False)
    return sprite


def _defs(sp: dict, prefix: str) -> str:
    return "".join(f'<image id="{prefix}{k}" href="/passivetree/{s["file"]}" width="{s["w"]}" height="{s["h"]}"/>'
                   for k, s in sp.items())


def _node_svg(n: dict, state: int, sprite, mastery_text: str = "", jewel: dict | None = None) -> str:
    """state: 0 allocated, 1 next to your points, 2 not taken."""
    k, x, y = n["k"], n["x"], n["y"]
    asc = bool(n["a"])
    stats = list(n["s"]) + ([mastery_text] if mastery_text else [])
    tip = f' data-s="{esc(chr(10).join(stats))}"' if stats else ""
    title = n["n"]
    body = ""
    if k == "mastery":
        if state == 0:
            body = sprite("masteryActiveSelected", n.get("ai") or "", x, y)
        else:
            body = sprite("masteryInactive", n.get("ii") or "", x, y, 1.0, ' opacity=".55"')
    elif k == "ascstart":
        body = sprite("ascendancy", "AscendancyMiddle", x, y)
    elif k == "jewel":
        body = sprite("frame", FRAMES["jewel"][state], x, y)
        if jewel:
            title = f"{n['n']}: {jewel.get('name') or ''} {jewel.get('typeLine') or ''}".strip()
            stats = [str(m) for m in (jewel.get("explicitMods") or [])]
            tip = f' data-s="{esc(chr(10).join(stats))}"' if stats else ""
            if jewel.get("icon"):
                body += (f'<image href="{esc(jewel["icon"])}" x="{x - 40:.0f}" y="{y - 40:.0f}" width="80" height="80"/>')
    else:
        sheet = k + ("Active" if state == 0 else "Inactive")
        body = sprite(sheet, n["i"], x, y)
        frames = ASC_FRAMES.get("notable" if k in ("notable", "keystone") else "normal") if asc else FRAMES[k]
        body += sprite("ascendancy" if asc else "frame", frames[state], x, y)
    return (f'<g class="nd{" on" if state == 0 else ""}" data-n="{esc(title)}"{tip}>{body}'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{HIT.get(k, 52)}" fill="transparent"/></g>')


def svg(snap_id: int, passives: dict, char_class: str, ascendancy: str, part: str = "main") -> str:
    """The tree for one snapshot. part: "main" or "asc" (the ascendancy)."""
    lay = passive_tree.layout()
    idx = passive_tree.index() or {"effects": {}}
    if not lay:
        return ""
    key = (lay.get("version"), snap_id, part)
    if key in _cache:
        return _cache[key]
    sp = lay["sprites"]
    prefix = f"pt-ps{part}-"
    sprite = _sprite_fn(sp, prefix)
    on = {str(h) for h in passives.get("hashes") or []}
    me = passives.get("mastery_effects") or {}
    pairs = me.items() if isinstance(me, dict) else [((int(v) & 0xFFFF), int(v) >> 16) for v in me]
    mastery_pick = {str(nd): str(eff) for nd, eff in pairs}
    jewels = {}
    slots = lay.get("jewel_slots") or []
    for j in passives.get("items") or []:
        x = j.get("x")
        if isinstance(x, int) and 0 <= x < len(slots):
            jewels[slots[x]] = j
    nodes = lay["nodes"]
    by = {n["h"]: n for n in nodes}
    neigh: dict[str, set] = {}
    for ln in lay["links"]:
        neigh.setdefault(ln["a"], set()).add(ln["b"])
        neigh.setdefault(ln["b"], set()).add(ln["a"])
    start = next((n["h"] for n in nodes if n["k"] == "start" and n.get("cls", "").lower() == char_class.lower()), None)
    lit = set(on) | ({start} if start else set())
    near = {o for h in lit for o in neigh.get(h, ())} - lit

    if part == "asc":
        mine = [n for n in nodes if n["a"] and n["a"].lower() == (ascendancy or "").lower()]
        if not mine:
            return ""
        astart = next((n for n in mine if n["k"] == "ascstart"), mine[0])
        lit |= {astart["h"]}
        near = {o for h in lit for o in neigh.get(h, ())} - lit
        xs, ys = [n["x"] for n in mine], [n["y"] for n in mine]
        bg = sp.get("ascendancy", {}).get("c", {}).get(f"Classes{mine[0]['a']}")
        r = (bg["w"] / sp["ascendancy"]["zoom"] / 2) if bg else 700
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        vb = (cx - r - 40, cy - r - 40, 2 * r + 80, 2 * r + 80)
        out = [_open(vb), f"<defs>{_defs(sp, prefix)}</defs>",
               sprite("ascendancy", f"Classes{mine[0]['a']}", cx, cy)]
        ids = {n["h"] for n in mine}
        out += _links([ln for ln in lay["links"] if ln["a"] in ids], lit)
        for n in mine:
            st = 0 if n["h"] in lit else 1 if n["h"] in near else 2
            out.append(_node_svg(n, st, sprite))
    else:
        x0, y0, x1, y1 = lay["bounds"]
        pad = 600
        vb = (x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
        pts = [(by[h]["x"], by[h]["y"]) for h in lit if h in by and not by[h]["a"]]
        start_vb = None
        if len(pts) > 1:                 # open on your part of the tree; the fit button shows all of it
            ax0, ax1 = min(p[0] for p in pts), max(p[0] for p in pts)
            ay0, ay1 = min(p[1] for p in pts), max(p[1] for p in pts)
            w, h = max(ax1 - ax0, 3500) + 1400, max(ay1 - ay0, 3000) + 1400
            start_vb = ((ax0 + ax1) / 2 - w / 2, (ay0 + ay1) / 2 - h / 2, w, h)
        bgt = sp.get("background", {}).get("c", {}).get("Background2")
        out = [_open(vb, start_vb), f"<defs>{_defs(sp, prefix)}"]
        if bgt:
            tw, th = bgt["w"] / sp["background"]["zoom"], bgt["h"] / sp["background"]["zoom"]
            out.append(f'<pattern id="{prefix}bgpat" patternUnits="userSpaceOnUse" width="{tw:.0f}" height="{th:.0f}">'
                       f'<svg width="{tw:.0f}" height="{th:.0f}" viewBox="{bgt["x"]} {bgt["y"]} {bgt["w"]} {bgt["h"]}" '
                       f'preserveAspectRatio="none"><use href="#{prefix}background"/></svg></pattern>')
        out.append("</defs>")
        if bgt:
            out.append(f'<rect x="{vb[0]:.0f}" y="{vb[1]:.0f}" width="{vb[2]:.0f}" height="{vb[3]:.0f}" '
                       f'fill="url(#{prefix}bgpat)" opacity=".8"/>')
        for g in lay["group_bgs"]:
            out.append(sprite("groupBackground", g["img"], g["x"], g["y"], half=g["img"] == "PSGroupBackground3"))
        for n in nodes:
            if n["k"] == "start":
                name = f"center{n.get('cls', '').lower()}" if n["h"] == start else "PSStartNodeBackgroundInactive"
                out.append(sprite("startNode", name, n["x"], n["y"]))
        out += _links([ln for ln in lay["links"] if not ln["asc"]], lit)
        groups_on = {by[h]["g"] for h in on if h in by}
        for n in nodes:
            if n["a"] or n["k"] == "start":
                continue
            if n["k"] == "mastery":
                st = 0 if (n["h"] in on or n["h"] in mastery_pick) else 2
                eff = idx["effects"].get(mastery_pick.get(n["h"], ""))
                out.append(_node_svg(n, st, sprite, " / ".join(eff[1]) if eff and st == 0 else ""))
                continue
            st = 0 if n["h"] in lit else 1 if n["h"] in near else 2
            out.append(_node_svg(n, st, sprite, jewel=jewels.get(n["h"]) if n["k"] == "jewel" else None))
        del groups_on
    out.append("</svg>")
    res = "".join(out)
    if len(_cache) > 12:
        _cache.clear()
    _cache[key] = res
    return res


def _open(vb, start_vb=None) -> str:
    v = " ".join(f"{x:.0f}" for x in vb)
    sv = " ".join(f"{x:.0f}" for x in (start_vb or vb))
    return (f'<svg class="pt-atlas-svg" xmlns="http://www.w3.org/2000/svg" viewBox="{sv}" data-vb="{v}" '
            f'preserveAspectRatio="xMidYMid meet">')


def _links(links: list[dict], lit: set) -> list[str]:
    tiers = {0: [], 1: [], 2: []}
    for ln in links:
        tiers[(ln["a"] in lit) + (ln["b"] in lit)].append(ln["d"])
    return [f'<path class="l{t}" d="{"".join(tiers[t])}"/>' for t in (0, 1, 2) if tiers[t]]


def counts(passives: dict) -> dict:
    """{points, asc} for the heading."""
    idx = passive_tree.index() or {"nodes": {}}
    pts = asc = 0
    for h in passives.get("hashes") or []:
        n = idx["nodes"].get(str(h))
        if not n or n[1] in ("mastery", "start"):
            continue
        if n[2]:
            asc += n[1] != "start"
        else:
            pts += 1
    return {"points": pts, "asc": asc}


def dumps(x) -> str:
    return json.dumps(x)
