"""Profile snapshots on the Characters page: the timeline, gear, jewels,
passives, and what changed since the snapshot before."""
from __future__ import annotations

import html

from nicegui import ui

from .. import passive_tree, profile
from . import fmt
from .layout import STATE, league_start
from .widgets import card, empty, note

RARITY = {0: "#c8c8c8", 1: "#8888ff", 2: "#ffff77", 3: "#af6025", 4: "#1ba29b", 5: "#aa9e82", 6: "#aa9e82",
          9: "#82ad6a", 10: "#82ad6a"}
SLOTS = [("Weapon", "Weapon"), ("Offhand", "Off hand"), ("Helm", "Helmet"), ("BodyArmour", "Body armour"),
         ("Gloves", "Gloves"), ("Boots", "Boots"), ("Amulet", "Amulet"), ("Ring", "Ring"), ("Ring2", "Ring"),
         ("Belt", "Belt"), ("Weapon2", "Swap weapon"), ("Offhand2", "Swap off hand")]
esc = html.escape


def _item_name(it: dict) -> str:
    n = " ".join(x for x in (it.get("name"), it.get("typeLine")) if x).strip()
    return n or it.get("baseType") or "?"


def _mod_text(m) -> str:
    """A mod line; some kinds come as objects instead of plain text."""
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        for k in ("text", "name", "description", "mod"):
            if isinstance(m.get(k), str):
                return m[k]
        return " ".join(str(v) for v in m.values() if isinstance(v, (str, int, float)))
    return str(m)


def _mods_tip(it: dict) -> str:
    lines = []
    for key in ("enchantMods", "implicitMods", "fracturedMods", "explicitMods", "craftedMods", "mutatedMods",
                "crucibleMods", "veiledMods", "scourgeMods", "runeMods", "desecratedMods"):
        lines += [_mod_text(m) for m in (it.get(key) or []) if m]
    if it.get("corrupted"):
        lines.append("Corrupted")
    return "\n".join(x for x in lines if x)


def _gems(it: dict) -> list[str]:
    out = []
    for g in it.get("socketedItems") or []:
        if g.get("frameType") == 4 or g.get("support") is not None:
            lvl = next((p["values"][0][0] for p in g.get("properties") or [] if p.get("name") == "Level" and p.get("values")), "")
            out.append(f"{g.get('typeLine') or g.get('baseType')}{' ' + str(lvl).split()[0] if lvl else ''}")
    return out


def _item_key(it: dict) -> str:
    inv = it.get("inventoryId") or ""
    return f"Flask{it.get('x', 0)}" if inv == "Flask" else inv


def _passive_summary(p: dict | None) -> dict:
    """{points, asc, keystones, notables, asc_notables, masteries, names} from a get-passive-skills answer."""
    idx = passive_tree.index() or {"nodes": {}, "effects": {}}
    nodes = idx["nodes"]
    hashes = [str(h) for h in (p or {}).get("hashes") or []]
    out = {"points": 0, "asc": 0, "keystones": [], "notables": [], "asc_notables": [], "masteries": [], "names": {},
           "known": bool(nodes)}
    for h in hashes:
        name, kind, asc, _stats = nodes.get(h, ["", "normal", "", []])
        out["names"][h] = name
        if asc:
            out["asc"] += 1
            if kind in ("notable", "keystone"):
                out["asc_notables"].append(name)
            continue
        if kind == "mastery":
            continue
        out["points"] += 1
        if kind == "keystone":
            out["keystones"].append(name)
        elif kind == "notable":
            out["notables"].append(name)
    me = (p or {}).get("mastery_effects") or {}
    pairs = me.items() if isinstance(me, dict) else [((int(v) & 0xFFFF), int(v) >> 16) for v in me]
    for node, eff in pairs:
        mname = nodes.get(str(node), [""])[0]
        e = idx["effects"].get(str(eff))
        out["masteries"].append(f"{mname or (e[0] if e else 'Mastery')}: {' / '.join(e[1]) if e else eff}")
    return out


def section(character: str, league: str | None) -> None:
    """The Profile Snapshots card for one character."""
    passive_tree.ensure()
    sn = STATE.snaps
    acct = (STATE.cfg.settings or {}).get("poe_account") if STATE.cfg else ""
    ls = league_start()
    in_ls = ls["phase"] in ("campaign", "mapping") and ls.get("league") == league
    sel = {"id": None}
    pref_key = f"snap:{league}:{character}"

    @ui.refreshable
    def body():
        con = STATE.con()
        try:
            rows = profile.snapshots(con, character, league)
        finally:
            con.close()
        ok_rows = [r for r in rows if r["status"] in ("ok", "same")]
        with ui.row().classes("w-full items-center gap-3"):
            if ok_rows:
                opts = {r["id"]: f"{r['label']} · level {r['level'] or '?'} · {fmt.when(r['event_utc'])}"
                        + (" (no change)" if r["status"] == "same" else "") for r in reversed(ok_rows)}
                cur = STATE.pref(pref_key)
                sel["id"] = cur if cur in opts else next(iter(opts))
                ui.select(opts, value=sel["id"], label="Snapshot",
                          on_change=lambda e: (STATE.set_pref(pref_key, e.value), body.refresh())).props(
                    "outlined dense dark options-dense").style("min-width:340px")
            if not in_ls:
                b = ui.button("Snapshot now", icon="o_photo_camera", on_click=lambda: snap_now()).props("outline no-caps")
                if not acct:
                    b.disable()
                    b.tooltip("Add your account name in Settings → Profile Snapshots first")
            last = max(rows, key=lambda r: r["ts_utc"] or "", default=None)
            if last and last["status"] == "error":
                ui.label(f"Last try didn't work: {last['error']}").classes("pt-note").style("flex:1 1 260px")
        if not ok_rows:
            empty("No snapshots of this character yet. " + (
                "They're taken automatically during league start." if in_ls else
                "Press Snapshot now to save its gear, jewels and passive tree." if acct else
                "Add your account name in Settings → Profile Snapshots to take them."))
            return
        try:
            con = STATE.con()
            try:
                snap = profile.load(con, sel["id"])
                i = next((k for k, r in enumerate(ok_rows) if r["id"] == sel["id"]), 0)
                prev = profile.load(con, ok_rows[i - 1]["id"]) if i > 0 else None
            finally:
                con.close()
            with ui.column().classes("w-full gap-2"):
                _show(snap, prev)
        except Exception as e:                     # show what went wrong instead of a blank card
            import logging
            import traceback
            logging.getLogger(__name__).exception("showing profile snapshot failed")
            tb = traceback.extract_tb(e.__traceback__)[-1]
            ui.label(f"Couldn't show this snapshot: {type(e).__name__}: {e} "
                     f"({tb.name}, line {tb.lineno})").classes("pt-note").style("color:#e06050")

    watch = {"since": None}

    def snap_now():
        if not sn:
            return
        watch["since"] = sn.state.get("done", 0)
        sn.request(character, league)
        status.set_text("Reading your profile on pathofexile.com…")

    def check():                       # lives outside body() so refreshing it can't stop it
        if watch["since"] is None or not sn:
            return
        if sn.state.get("done", 0) == watch["since"]:
            return
        watch["since"] = None
        status.set_text("")
        last = sn.state.get("last") or {}
        if last.get("status") == "error":
            ui.notify(last.get("error"), type="warning", position="top", timeout=8000, multi_line=True)
        elif last.get("status") == "same":
            ui.notify("Nothing changed since the last snapshot.", position="top", timeout=3000)
        else:
            ui.notify("Snapshot saved.", type="positive", position="top", timeout=2500)
        STATE.set_pref(pref_key, None)
        body.refresh()

    with card("Profile Snapshots"):
        status = ui.label("").classes("pt-note").style("color:var(--ex-gold-hi, #e6c27a)")
        body()
        ui.timer(1.0, check)
        note("From your public pathofexile.com profile. During league start they're taken at the end of each act, "
             "then every 10 levels, your first yellow and red map, and each Voidstone. Hover an item for its mods.")


def _show(snap: dict | None, prev: dict | None) -> None:
    if not snap or not snap.get("items"):
        empty("This snapshot has no data.")
        return
    items = snap["items"].get("items") or []
    by = {_item_key(i): i for i in items}
    pv = {_item_key(i): i for i in (prev or {}).get("items", {}).get("items") or []} if prev and prev.get("items") else {}
    ps, pp = _passive_summary(snap.get("passives")), _passive_summary((prev or {}).get("passives")) if prev else None

    # ---- what changed
    if prev:
        changes = []
        for k in sorted(set(by) | set(pv)):
            a, b = pv.get(k), by.get(k)
            if (a or {}).get("id") != (b or {}).get("id"):
                slot = dict(SLOTS).get(k, "Flask" if k.startswith("Flask") else k)
                changes.append(f"{slot}: {esc(_item_name(a)) if a else '—'} → <b>{esc(_item_name(b)) if b else '—'}</b>")
        added = [n for n in ps["notables"] + ps["keystones"] + ps["asc_notables"]
                 if n not in pp["notables"] + pp["keystones"] + pp["asc_notables"]]
        removed = [n for n in pp["notables"] + pp["keystones"] + pp["asc_notables"]
                   if n not in ps["notables"] + ps["keystones"] + ps["asc_notables"]]
        dp, da = ps["points"] - pp["points"], ps["asc"] - pp["asc"]
        lines = []
        if dp or da:
            lines.append(f"Passives: {'+' if dp >= 0 else ''}{dp} points" + (f", {'+' if da >= 0 else ''}{da} ascendancy" if da else ""))
        if added:
            lines.append("New notables: <b>" + esc(", ".join(added)) + "</b>")
        if removed:
            lines.append("Respecced: " + esc(", ".join(removed)))
        lines += changes
        ui.html('<div class="pt-snapdiff"><div class="k">Since ' + esc(prev.get("label") or "the snapshot before") +
                "</div>" + ("".join(f"<div>{x}</div>" for x in lines) or "<div>No changes.</div>") + "</div>").classes("w-full")

    # ---- gear, jewels and skills
    with ui.row().classes("w-full gap-5 items-start pt-wrap q-mt-sm"):
        ui.html(_paperdoll(items), sanitize=False)
        jewels = (snap.get("passives") or {}).get("items") or []
        abyss = [g for it in items for g in it.get("socketedItems") or [] if g.get("abyssJewel")]
        with ui.column().classes("gap-2").style("flex:0 1 250px;min-width:200px"):
            ui.label(f"Jewels · {len(jewels) + len(abyss)}").classes("pt-snaphead")
            ui.html("".join(_jewel_row(j) for j in jewels + abyss) or '<div class="pt-note">No jewels.</div>')
        with ui.column().classes("gap-2").style("flex:1 1 320px;min-width:280px"):
            ui.label("Skills").classes("pt-snaphead")
            ui.html(_skills(items) or '<div class="pt-note">No gems.</div>')

    # ---- the passive tree, with the ascendancy over it like in game
    asc = (snap["items"].get("character") or {}).get("class") or snap.get("class") or ""
    head = f"Passive tree · {ps['points']} points" + (f" · {ps['asc']} ascendancy ({asc})" if ps["asc"] else "")
    ui.label(head).classes("pt-snaphead q-mt-md")
    if not passive_tree.status()["ready"]:
        ui.label("Getting the passive tree from GGG's official export (once, a few MB)… reopen this in a moment.").classes("pt-note")
    elif snap.get("passives"):
        with ui.element("div").classes("pt-atlas pt-canvas pt-tree w-full").props(
                f'data-scene="/scene/snap/{snap["id"]}" data-key="snap{snap["id"]}"'):
            with ui.element("div").classes("pt-atlas-ctl"):
                for icon, act in (("add", "in"), ("remove", "out"), ("fit_screen", "fit")):
                    ui.button(icon=icon).props(f'flat round dense size=sm data-atlas="{act}"')
        note("Scroll to zoom, drag to move, hover a point, gem or item for what it does. "
             "Tree and item art © Grinding Gear Games.")
    ui.label(f"Read from your profile {fmt.when(snap['ts_utc'])}"
             + (" (nothing had changed, so this shows the snapshot before)" if snap.get("status") == "same" else "")).classes(
        "pt-note q-mt-sm")


# ---- inventory, the way the game lays it out (8 x 8 cells) -----------------
_AREAS = {"Weapon": "1 / 1 / 5 / 3", "Offhand": "1 / 7 / 5 / 9", "Weapon2": "1 / 1 / 5 / 3", "Offhand2": "1 / 7 / 5 / 9",
          "Helm": "1 / 4 / 3 / 6", "Amulet": "3 / 6 / 4 / 7", "BodyArmour": "3 / 4 / 6 / 6", "Ring": "4 / 3 / 5 / 4",
          "Ring2": "4 / 6 / 5 / 7", "Gloves": "5 / 1 / 7 / 3", "Belt": "6 / 4 / 7 / 6", "Boots": "5 / 7 / 7 / 9",
          "Trinket": "8 / 1 / 9 / 3"}
_SOCKET = {"R": "#c0392b", "G": "#3f9a4a", "B": "#3b6fd1", "W": "#e8e8e8", "A": "#2b2b2b", "DV": "#888"}


def _sockets(it: dict) -> str:
    socks = it.get("sockets") or []
    if not socks:
        return ""
    w = 2 if (it.get("w") or 1) >= 2 else 1
    filled = {g.get("socket") for g in it.get("socketedItems") or []}
    pos = []
    for i in range(len(socks)):
        if w == 2:
            r, c = i // 2, (i % 2 if (i // 2) % 2 == 0 else 1 - i % 2)
        else:
            r, c = i, 0
        pos.append((r, c))
    out = ""
    for i in range(1, len(socks)):           # links between neighbours in the same group
        if socks[i].get("group") == socks[i - 1].get("group"):
            (r1, c1), (r2, c2) = pos[i - 1], pos[i]
            horiz = r1 == r2
            out += (f'<i class="lk {"h" if horiz else "v"}" style="--r:{min(r1, r2)};--c:{min(c1, c2)}"></i>')
    for i, sk in enumerate(socks):
        r, c = pos[i]
        col = _SOCKET.get(sk.get("sColour") or sk.get("attr") or "", "#777")
        out += f'<b class="{"on" if i in filled else ""}" style="--r:{r};--c:{c};--sc:{col}"></b>'
    return f'<span class="sk w{w}" style="--rows:{(len(socks) + w - 1) // w}">{out}</span>'


def _paperdoll(items: list[dict]) -> str:
    by = {}
    for it in items:
        by.setdefault(it.get("inventoryId") or "", []).append(it)

    def cell(it, area, extra=""):
        name = it.get("name") or ""
        base = it.get("typeLine") or it.get("baseType") or ""
        gems = ", ".join(_gem_label(g) for g in it.get("socketedItems") or [] if not g.get("abyssJewel"))
        icon = it.get("icon") or ""
        return (f'<div class="pt-inv pt-tipable {extra}" style="grid-area:{area}" data-n="{esc(name or base)}" '
                f'data-b="{esc(base if name else "")}" data-c="{RARITY.get(it.get("frameType"), "#c8c8c8")}" '
                f'data-s="{esc(_mods_tip(it))}" data-g="{esc(gems)}">'
                + (f'<img src="{esc(icon)}" alt="" loading="lazy">' if icon else f'<span>{esc(name or base)}</span>')
                + _sockets(it) + "</div>")
    html_ = ""
    has_swap = bool(by.get("Weapon2") or by.get("Offhand2"))
    for key, area in _AREAS.items():
        for it in by.get(key, [])[:1]:
            html_ += cell(it, area, "set2" if key.endswith("2") and key != "Ring2" else
                          "set1" if key in ("Weapon", "Offhand") else "")
    for key, area in (("Weapon", "1 / 1 / 5 / 3"), ("Offhand", "1 / 7 / 5 / 9"), ("Helm", "1 / 4 / 3 / 6"),
                      ("BodyArmour", "3 / 4 / 6 / 6"), ("Gloves", "5 / 1 / 7 / 3"), ("Boots", "5 / 7 / 7 / 9"),
                      ("Belt", "6 / 4 / 7 / 6"), ("Amulet", "3 / 6 / 4 / 7"), ("Ring", "4 / 3 / 5 / 4"),
                      ("Ring2", "4 / 6 / 5 / 7"), ("Trinket", "8 / 1 / 9 / 3")):
        if not by.get(key):
            html_ += f'<div class="pt-inv empty" style="grid-area:{area}"></div>'
    flasks = sorted(by.get("Flask", []), key=lambda i: i.get("x", 0))
    taken = {int(f.get("x", 0)) for f in flasks}
    for f in flasks:
        col = 3 + int(f.get("x", 0))
        html_ += cell(f, f"7 / {col} / 9 / {col + 1}")
    for x in range(5):
        if x not in taken:
            html_ += f'<div class="pt-inv empty" style="grid-area:7 / {3 + x} / 9 / {4 + x}"></div>'
    swap = ('<div class="pt-swap"><button class="on" data-set="1">I</button><button data-set="2">II</button></div>'
            if has_swap else "")
    return f'<div class="pt-paperdoll">{swap}<div class="grid">{html_}</div></div>'


def _gem_props(g: dict) -> tuple[str, str]:
    lvl = qual = ""
    for p in g.get("properties") or []:
        v = (p.get("values") or [[""]])[0][0] if p.get("values") else ""
        if p.get("name") == "Level":
            lvl = str(v).split()[0] if v else ""
        elif p.get("name") == "Quality":
            qual = str(v).lstrip("+").rstrip("%") if v else ""
    return lvl, qual


def _gem_label(g: dict) -> str:
    lvl, qual = _gem_props(g)
    return (g.get("typeLine") or g.get("baseType") or "?") + (f" {lvl}" if lvl else "") + (f"/{qual}%" if qual else "")


def _skills(items: list[dict]) -> str:
    """One row per linked group: gem art with level and quality, supports smaller."""
    order = [k for k, _ in SLOTS]
    rows = ""
    for it in sorted(items, key=lambda i: order.index(i.get("inventoryId")) if i.get("inventoryId") in order else 99):
        gems = [g for g in it.get("socketedItems") or [] if not g.get("abyssJewel")]
        if not gems or it.get("inventoryId") in ("Weapon2", "Offhand2"):
            continue
        socks = it.get("sockets") or []
        groups: dict = {}
        for g in gems:
            si = g.get("socket")
            grp = socks[si].get("group") if isinstance(si, int) and si < len(socks) else 0
            groups.setdefault(grp, []).append(g)
        label = dict(SLOTS).get(it.get("inventoryId"), it.get("inventoryId") or "")
        for grp in sorted(groups):
            gl = sorted(groups[grp], key=lambda g: bool(g.get("support")))
            cells = ""
            for g in gl:
                lvl, qual = _gem_props(g)
                sup = bool(g.get("support"))
                props = "\n".join(f'{p.get("name")}: {", ".join(str(v[0]) for v in p.get("values") or [])}'
                                   for p in g.get("properties") or [] if p.get("name") and p.get("values"))
                cells += (f'<span class="gem pt-tipable{" sup" if sup else ""}" data-n="{esc(g.get("typeLine") or "")}" '
                          f'data-c="#1ba29b" data-s="{esc(props)}" data-a="{"Support gem" if sup else "Skill gem"}">'
                          + (f'<img src="{esc(g.get("icon") or "")}" alt="" loading="lazy">' if g.get("icon") else "")
                          + f'<em>{esc(lvl or "?")}{("/" + esc(qual)) if qual else ""}</em>'
                          + (f'<small>{esc(g.get("typeLine") or "")}</small>' if not sup else "") + "</span>")
            rows += f'<div class="pt-skill"><div class="sl">{esc(label)} · {len(gl)}L</div><div class="gems">{cells}</div></div>'
    return rows


def _jewel_row(j: dict) -> str:
    col = RARITY.get(j.get("frameType"), "#c8c8c8")
    return (f'<div class="pt-jewel pt-tipable" data-n="{esc(j.get("name") or j.get("typeLine") or "")}" '
            f'data-b="{esc(j.get("typeLine") if j.get("name") else "")}" data-c="{col}" data-s="{esc(_mods_tip(j))}">'
            + (f'<img src="{esc(j.get("icon") or "")}" alt="" loading="lazy">' if j.get("icon") else "")
            + f'<span style="color:{col}">{esc(_item_name(j))}</span></div>')
