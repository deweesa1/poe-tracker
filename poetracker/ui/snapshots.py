"""Profile snapshots on the Characters page: the timeline, gear, jewels,
passives, and what changed since the snapshot before."""
from __future__ import annotations

import html

from nicegui import ui

from .. import icons, passive_tree, profile
from . import fmt
from .layout import STATE, league_start
from .widgets import card, empty, note

RARITY = {0: "#c8c8c8", 1: "#8888ff", 2: "#ffff77", 3: "#af6025", 4: "#1ba29b", 5: "#aa9e82", 6: "#aa9e82",
          9: "#82ad6a", 10: "#82ad6a"}
SLOTS = [("Weapon", "Weapon"), ("Offhand", "Off hand"), ("Helm", "Helmet"), ("BodyArmour", "Body armour"),
         ("Gloves", "Gloves"), ("Boots", "Boots"), ("Amulet", "Amulet"), ("Ring", "Ring"), ("Ring2", "Ring"),
         ("Belt", "Belt"), ("Weapon2", "Swap weapon"), ("Offhand2", "Swap off hand")]
esc = html.escape
WORN = {"Weapon", "Offhand", "Weapon2", "Offhand2", "Helm", "BodyArmour", "Gloves", "Boots", "Amulet", "Ring", "Ring2",
        "Belt", "Flask", "Trinket"}       # equipped slots (the profile also lists the main inventory)


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


# ---- the item card, laid out like the game's ------------------------------
_VAL = {0: "#e8e2d4", 1: "#8888ff", 2: "#8888ff", 3: "#8888ff", 4: "#d04c2c", 5: "#4f8fd8", 6: "#e6c84a", 7: "#c74fa8"}
_FRAME = {0: "normal", 1: "magic", 2: "rare", 3: "unique", 4: "gem", 5: "currency", 6: "divination", 9: "relic", 10: "relic"}
_INFLUENCE = {"shaper": "Shaper", "elder": "Elder", "crusader": "Crusader", "redeemer": "Redeemer", "hunter": "Hunter",
              "warlord": "Warlord", "searing": "Searing Exarch", "tangled": "Eater of Worlds"}


def _prop_line(p: dict) -> str:
    """One property line ("Armour: 324", "Quality: +20%"), values coloured like the game."""
    name = str(p.get("name") or "")
    vals = p.get("values") or []
    cv = [f'<span style="color:{_VAL.get(v[1] if len(v) > 1 else 0, "#e8e2d4")}">{esc(str(v[0]))}</span>' for v in vals]
    if "{0}" in name:
        out = esc(name)
        for i, v in enumerate(cv):
            out = out.replace("{" + str(i) + "}", v)
        return out
    if not vals:
        return esc(name)
    return f"{esc(name)}: " + ", ".join(cv)


def item_card(it: dict, gems_line: str = "") -> str:
    """The hover card for an item: header in its rarity colour, properties, requirements,
    then enchant / implicit / fractured / explicit / crafted / foulborn mods, flavour and flags."""
    frame = _FRAME.get(it.get("frameType"), "normal")
    name, base = it.get("name") or "", it.get("typeLine") or it.get("baseType") or ""
    marks = [(k, label) for k, label in _INFLUENCE.items() if (it.get("influences") or {}).get(k) or it.get(k) is True]
    marks += [(k, label) for k, label in (("fractured", "Fractured"), ("synthesised", "Synthesised"), ("mutated", "Foulborn"),
                                          ("split", "Split"), ("mirrored", "Mirrored"), ("veiled", "Veiled")) if it.get(k)]
    # round symbols in the header corners like the game (influences first); the rest as text
    syms = [k for k, _ in marks if icons.have(k)][:2]
    left = syms[0] if syms else None
    right = syms[1] if len(syms) > 1 else left
    text_tags = [label for k, label in marks if k not in syms]
    sym = (lambda k, side: f'<img class="ic-sym {side}" src="/icons/{icons.name(k)}" alt="">' if k else "")
    head = (f'<div class="ic-head {frame}">{sym(left, "l")}{sym(right, "r")}'
            + (f'<div>{esc(name)}</div>' if name else "") + f'<div>{esc(base)}</div>'
            + (f'<div class="ic-tags">{" · ".join(esc(t) for t in text_tags)}</div>' if text_tags else "") + "</div>")
    blocks = []
    props = [_prop_line(p) for p in it.get("properties") or []]
    if props:
        blocks.append("".join(f'<div class="ic-prop">{x}</div>' for x in props))
    req, extra = it.get("requirements") or [], ""
    if req:
        parts = []
        for r in req:
            v = (r.get("values") or [[""]])[0][0]
            parts.append(f'{esc(r.get("name"))} <b>{esc(str(v))}</b>' if r.get("name") == "Level" else
                         f'<b>{esc(str(v))}</b> {esc(r.get("name"))}')
        extra += f'<div class="ic-req">Requires {", ".join(parts)}</div>'
    if it.get("ilvl") and it.get("frameType") != 4:
        extra += f'<div class="ic-req">Item Level: <b>{it["ilvl"]}</b></div>'
    if it.get("secDescrText"):
        extra += f'<div class="ic-req" style="color:#1ba29b">{esc(it["secDescrText"])}</div>'
    if extra:
        blocks.append(extra)

    def mods(key, cls):
        return "".join(f'<div class="ic-mod {cls}">{esc(_mod_text(m))}</div>' for m in it.get(key) or [] if m)
    for group in (mods("enchantMods", "ench"), mods("scourgeMods", "ench"), mods("utilityMods", "ench"),
                  mods("implicitMods", "impl"),
                  mods("fracturedMods", "frac") + mods("explicitMods", "expl") + mods("veiledMods", "expl")
                  + mods("craftedMods", "craft") + mods("crucibleMods", "craft") + mods("runeMods", "craft")
                  + mods("desecratedMods", "craft") + mods("mutatedMods", "foul")):
        if group:
            blocks.append(group)
    if it.get("flavourText"):
        blocks.append('<div class="ic-flav">' + "".join(f"<div>{esc(str(x))}</div>" for x in it["flavourText"]) + "</div>")
    if it.get("corrupted"):
        blocks.append('<div class="ic-corrupt">Corrupted</div>')
    if gems_line:
        blocks.append(f'<div class="ic-gems">{esc(gems_line)}</div>')
    return f'<div class="ic">{head}<div class="ic-body">{"<hr>".join(blocks)}</div></div>'


def _quality(it: dict) -> str:
    for p in it.get("properties") or []:
        if str(p.get("name", "")).startswith("Quality") and p.get("values"):
            return str(p["values"][0][0])
    return ""


def defences(items: list[dict]) -> dict:
    """Armour / evasion / energy shield / ward listed on your equipped gear (each item's own
    numbers, with its quality and local mods; not your character's totals)."""
    out = {"Armour": 0, "Evasion Rating": 0, "Energy Shield": 0, "Ward": 0}
    for it in items:
        if it.get("inventoryId") in ("Weapon2", "Offhand2", "Flask", "Trinket"):
            continue
        for p in it.get("properties") or []:
            if p.get("name") in out and p.get("values"):
                try:
                    out[p["name"]] += int(str(p["values"][0][0]).replace(",", ""))
                except ValueError:
                    pass
    return out


_RES = ("Fire", "Cold", "Lightning", "Chaos")


def resistances(items: list[dict]) -> dict:
    """Fire / cold / lightning / chaos resistance added up from your equipped gear's mods
    (before the act penalty, the passive tree and other bonuses)."""
    import re
    out = dict.fromkeys(_RES, 0)
    one = re.compile(r"([+-]?\d+)% to (Fire|Cold|Lightning|Chaos) Resistance\b")
    two = re.compile(r"([+-]?\d+)% to (Fire|Cold|Lightning|Chaos) and (Fire|Cold|Lightning|Chaos) Resistances")
    alle = re.compile(r"([+-]?\d+)% to all Elemental Resistances")
    for it in items:
        if it.get("inventoryId") in ("Weapon2", "Offhand2", "Flask", "Trinket"):
            continue
        for key in ("implicitMods", "explicitMods", "craftedMods", "fracturedMods", "enchantMods", "mutatedMods",
                    "crucibleMods", "runeMods", "desecratedMods"):
            for m in it.get(key) or []:
                t = _mod_text(m)
                if (x := two.search(t)):
                    out[x.group(2)] += int(x.group(1))
                    out[x.group(3)] += int(x.group(1))
                elif (x := alle.search(t)):
                    for r in ("Fire", "Cold", "Lightning"):
                        out[r] += int(x.group(1))
                elif (x := one.search(t)):
                    out[x.group(2)] += int(x.group(1))
    return out


def resistance_sources(items: list[dict]) -> dict:
    """{res: [(item name, value, mod line), ...]}: which worn item gives which resistance."""
    out: dict = {}
    for it in items:
        if it.get("inventoryId") in ("Weapon2", "Offhand2", "Flask", "Trinket"):
            continue
        r = resistances([it])
        for k, v in r.items():
            if v:
                out.setdefault(k, []).append((_item_name(it), v))
    return out


_MOD_KEYS = ("implicitMods", "explicitMods", "craftedMods", "fracturedMods", "enchantMods", "mutatedMods",
             "crucibleMods", "runeMods", "desecratedMods")
_ATTR = ("Strength", "Dexterity", "Intelligence")


def _stat_hits(text: str, it: dict | None = None):
    """(stat, value) pairs one mod line adds to the extra gear stats."""
    import re
    t = text.strip()
    rules = (
        (r"([+-]?\d+) to maximum Life", lambda m: [("Life", int(m[1]))]),
        (r"(\d+)% (increased|reduced) maximum Life", lambda m: [("Life%", int(m[1]) * (1 if m[2] == "increased" else -1))]),
        (r"([+-]?\d+) to maximum Mana", lambda m: [("Mana", int(m[1]))]),
        (r"([+-]?\d+) to all Attributes", lambda m: [(a, int(m[1])) for a in _ATTR]),
        (r"([+-]?\d+) to (Strength|Dexterity|Intelligence) and (Strength|Dexterity|Intelligence)",
         lambda m: [(m[2], int(m[1])), (m[3], int(m[1]))]),
        (r"([+-]?\d+) to (Strength|Dexterity|Intelligence)", lambda m: [(m[2], int(m[1]))]),
        (r"(\d+)% (increased|reduced) Movement Speed", lambda m: [("Movement", int(m[1]) * (1 if m[2] == "increased" else -1))]),
        (r"\+?(\d+)% chance to Suppress Spell Damage", lambda m: [("Suppression", int(m[1]))]),
        (r"\+?(\d+)% Chance to Block Attack Damage", lambda m: [("Block", int(m[1]))]),
        (r"\+?(\d+)% Chance to Block Spell Damage", lambda m: [("Spell block", int(m[1]))]),
        (r"(\d+)% increased Rarity of Items found", lambda m: [("Rarity", int(m[1]))]),
    )
    for pat, fn in rules:
        m = re.fullmatch(pat, t, re.I)
        if m:
            g = [m.group(0)] + [x.capitalize() if x and x.lower() in ("strength", "dexterity", "intelligence") else x
                                for x in m.groups()]
            return fn(g)
    return []


GEAR_STATS = ("Life", "Mana", "Strength", "Dexterity", "Intelligence",
              "Movement", "Suppression", "Block", "Spell block", "Rarity")


def gear_stats(items: list[dict]) -> tuple[dict, dict]:
    """Life, mana, attributes, movement speed, suppression, block and rarity added up from
    the worn gear's mods (a shield's own block chance counts too). Returns (totals, sources)."""
    tot: dict = dict.fromkeys(GEAR_STATS + ("Life%",), 0)
    src: dict = {}
    for it in items:
        if it.get("inventoryId") in ("Weapon2", "Offhand2", "Flask", "Trinket"):
            continue
        mine: dict = {}
        for key in _MOD_KEYS:
            for m in it.get(key) or []:
                for k, v in _stat_hits(_mod_text(m), it):
                    mine[k] = mine.get(k, 0) + v
        for p in it.get("properties") or []:
            if p.get("name") == "Chance to Block" and p.get("values"):
                try:
                    mine["Block"] = mine.get("Block", 0) + int(str(p["values"][0][0]).rstrip("%"))
                except ValueError:
                    pass
        for k, v in mine.items():
            if v:
                tot[k] += v
                src.setdefault(k, []).append((_item_name(it), v))
    return tot, src


def _src_tip(title: str, rows: list, unit: str = "%") -> str:
    if not rows:
        return ""
    lines = "".join(f'<div class="ic-mod expl">{esc(n)}: <b style="color:#e8e2d4">{v:+d}{unit}</b></div>' for n, v in rows)
    return (f'<div class="ic"><div class="ic-head normal"><div>{esc(title)}</div></div>'
            f'<div class="ic-body">{lines}</div></div>')


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
    icons.ensure()
    sn = STATE.snaps
    acct = (STATE.cfg.settings or {}).get("poe_account") if STATE.cfg else ""
    ls = league_start()
    in_ls = ls["phase"] in ("campaign", "mapping") and ls.get("league") == league
    sel = {"id": None}
    ui_state: dict = {}
    pref_key = f"snap:{league}:{character}"

    @ui.refreshable
    def body():
        con = STATE.con()
        try:
            rows = profile.snapshots(con, character, league)
        finally:
            con.close()
        ok_rows = [r for r in rows if r["status"] in ("ok", "same")]
        snap = prev = None
        problem = None
        with card("Profile Snapshots"):
            ui_state["status"] = ui.label(ui_state.get("text", "")).classes("pt-note").style(
                "color:var(--ex-gold-hi, #e6c27a)")
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
                _show(snap, prev)
            except Exception as e:
                problem = e
        with card("Character Build"):
            try:
                if problem:
                    raise problem
                if not snap or not snap.get("items"):
                    empty("This snapshot has no data.")
                else:
                    _build(snap)
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
        ui_state["text"] = "Reading your profile on pathofexile.com…"
        ui_state["status"].set_text(ui_state["text"])

    def check():                       # lives outside body() so refreshing it can't stop it
        if watch["since"] is None or not sn:
            return
        if sn.state.get("done", 0) == watch["since"]:
            return
        watch["since"] = None
        ui_state["text"] = ""
        last = sn.state.get("last") or {}
        if last.get("status") == "error":
            ui.notify(last.get("error"), type="warning", position="top", timeout=8000, multi_line=True)
        elif last.get("status") == "same":
            ui.notify("Nothing changed since the last snapshot.", position="top", timeout=3000)
        else:
            ui.notify("Snapshot saved.", type="positive", position="top", timeout=2500)
        STATE.set_pref(pref_key, None)
        body.refresh()

    with ui.column().classes("w-full gap-4"):
        body()
        ui.timer(1.0, check)


def _show(snap: dict | None, prev: dict | None) -> None:
    """What changed since the snapshot before (shown in the Profile Snapshots card)."""
    if not snap or not snap.get("items"):
        return
    items = [i for i in snap["items"].get("items") or [] if i.get("inventoryId") in WORN]
    by = {_item_key(i): i for i in items}
    pv = {_item_key(i): i for i in (prev or {}).get("items", {}).get("items") or [] if i.get("inventoryId") in WORN} if prev and prev.get("items") else {}
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



def _build(snap: dict) -> None:
    """Gear, gear stats, jewels, skills and the passive tree of one snapshot."""
    items = [i for i in snap["items"].get("items") or [] if i.get("inventoryId") in WORN]
    jewels = (snap.get("passives") or {}).get("items") or []
    abyss = [g for it in items for g in it.get("socketedItems") or [] if g.get("abyssJewel")]
    # ---- gear and its stats on the left, skills on the right; the jewels go under whichever side is
    # shorter (tree.js picks; rendered in both places, one shown, so nothing moves between parents)
    jb = (f'<div class="pt-snaphead">Jewels · {len(jewels) + len(abyss)}</div>'
          f'<div class="pt-jewelrow">{_jewels_html(jewels, abyss)}</div>') if (jewels or abyss) else ""
    with ui.element("div").classes("pt-buildgrid w-full q-mt-sm"):
        with ui.column().classes("gap-3"):
            ui.html(_paperdoll(items), sanitize=False)
            dv, rv, src = defences(items), resistances(items), resistance_sources(items)
            dcells = [(k.replace(" Rating", ""), f"{v:,}" if v else "–", k.split()[0].lower(), "")
                      for k, v in dv.items() if k != "Ward" or v]
            rcells = [(f"{k} res", f"{v:+d}%" if v else "–", k.lower(), _src_tip(f"{k} resistance", src.get(k) or []))
                      for k, v in rv.items()]
            row = (lambda cs: f'<div class="pt-def" style="grid-template-columns:repeat({len(cs)}, 1fr)">' + "".join(
                f'<span class="{c}{" pt-tipable" if t else ""}"{f" data-tip={chr(34)}{esc(t)}{chr(34)}" if t else ""}>'
                f'<small>{esc(k)}</small>{esc(v)}</span>' for k, v, c, t in cs) + "</div>")
            gs, gsrc = gear_stats(items)

            def cell(k, label, cls, unit="", pct=False):
                v = gs[k]
                txt = (f"{v:+d}%" if pct else f"{v:+,}") if v else "–"
                if k == "Life" and gs["Life%"]:
                    txt = (txt if v else "–") + f" · {gs['Life%']:+d}%"
                tip = _src_tip(label, gsrc.get(k, []), "%" if pct else "")
                if k == "Life" and gsrc.get("Life%"):
                    tip = _src_tip("Life", gsrc.get("Life", []), "") + _src_tip("Increased maximum Life", gsrc["Life%"])
                return (label, txt, cls, tip)
            acells = [cell("Life", "Life", "life"), cell("Mana", "Mana", "mana"),
                      cell("Strength", "Str", "str"), cell("Dexterity", "Dex", "dex"), cell("Intelligence", "Int", "int")]
            ucells = [cell("Movement", "Move speed", "util", pct=True), cell("Suppression", "Suppress", "util", pct=True),
                      cell("Block", "Block", "util", pct=True), cell("Spell block", "Spell block", "util", pct=True),
                      cell("Rarity", "Rarity", "util", pct=True)]
            ui.label("Gear Determined Stats").classes("pt-snaphead").tooltip(
                "Added up from what you're wearing: each item's own defences and mods, before the passive tree, "
                "the act penalty and other bonuses. Hover a stat to see which items give it.")
            ui.html(row(dcells) + row(rcells) + row(acells) + row(ucells))
            if jb:
                ui.html(jb, sanitize=False).classes("w-full pt-jb pt-jb-l")
        with ui.column().classes("gap-3 pt-skillcol"):
            ui.label("Skills").classes("pt-snaphead")
            sk = _skills(items)
            ui.html(f'<div class="pt-skills">{sk}</div>' if sk else '<div class="pt-note">No gems.</div>').classes(
                "w-full pt-skillscroll")
            if jb:
                ui.html(jb, sanitize=False).classes("w-full pt-jb pt-jb-r")
    if jb:                                   # narrow windows: full width under both columns
        ui.html(jb, sanitize=False).classes("w-full pt-jb pt-jb-w")

    # ---- the passive tree, with the ascendancy over it like in game
    if not passive_tree.status()["ready"]:
        ui.label("Getting the passive tree from GGG's official export (once, a few MB)… reopen this in a moment.").classes("pt-note")
    elif snap.get("passives"):
        with ui.element("div").classes("pt-atlas pt-canvas pt-tree w-full q-mt-md").props(
                f'data-scene="/scene/snap/{snap["id"]}?v=3" data-key="snap{snap["id"]}"'):
            with ui.element("div").classes("pt-atlas-ctl"):
                for icon, act in (("add", "in"), ("remove", "out"), ("fit_screen", "fit")):
                    ui.button(icon=icon).props(f'flat round dense size=sm data-atlas="{act}"')
            ui.html('<div class="pt-tree-credit">Art © Grinding Gear Games</div>')



# ---- inventory, the way the game lays it out (8 x 8 cells) -----------------
_AREAS = {"Weapon": "1 / 1 / 5 / 3", "Offhand": "1 / 7 / 5 / 9", "Weapon2": "1 / 1 / 5 / 3", "Offhand2": "1 / 7 / 5 / 9",
          "Helm": "1 / 4 / 3 / 6", "Amulet": "3 / 6 / 4 / 7", "BodyArmour": "3 / 4 / 6 / 6", "Ring": "4 / 3 / 5 / 4",
          "Ring2": "4 / 6 / 5 / 7", "Gloves": "5 / 1 / 7 / 3", "Belt": "6 / 4 / 7 / 6", "Boots": "5 / 7 / 7 / 9",
          "Trinket": "8 / 1 / 9 / 2"}
_SOCKET = {"R": "#a04034", "G": "#4f8a48", "B": "#4a68a6", "W": "#b9b3a6", "A": "#3a3a3a", "DV": "#7a7a7a"}


def _socket_colour(sk: dict) -> str:
    """sColour is R/G/B/W/A/DV; older answers only have attr (S=red, D=green, I=blue, G=white, A=abyss)."""
    if sk.get("sColour"):
        return _SOCKET.get(sk["sColour"], "#777")
    return _SOCKET.get({"S": "R", "D": "G", "I": "B", "G": "W", "A": "A", "DV": "DV"}.get(sk.get("attr") or "", ""), "#777")


def _socket_layout(n: int, w: int) -> list[tuple[int, int]]:
    """Where the game puts socket i: two columns snake left-right-right-left; one column goes down."""
    if w == 1:
        return [(i, 0) for i in range(n)]
    return [(i // 2, (i % 2) if (i // 2) % 2 == 0 else 1 - i % 2) for i in range(n)]


def _sockets(it: dict) -> str:
    socks = it.get("sockets") or []
    if not socks:
        return ""
    w = 2 if (it.get("w") or 1) >= 2 and len(socks) > 1 else 1
    filled = {g.get("socket") for g in it.get("socketedItems") or []}
    pos = _socket_layout(len(socks), w)
    rows = max(r for r, _ in pos) + 1
    out = ""
    for i in range(1, len(socks)):           # links between neighbours in the same group
        if socks[i].get("group") == socks[i - 1].get("group"):
            (r1, c1), (r2, c2) = pos[i - 1], pos[i]
            out += f'<i class="lk {"h" if r1 == r2 else "v"}" style="--r:{min(r1, r2)};--c:{min(c1, c2)}"></i>'
    for i, sk in enumerate(socks):
        r, c = pos[i]
        col = _socket_colour(sk)
        out += f'<b class="{"on" if i in filled else ""}" style="--r:{r};--c:{c};--sc:{col}"></b>'
    return f'<span class="sk" style="--cols:{w};--rows:{rows}">{out}</span>'


def _paperdoll(items: list[dict]) -> str:
    by = {}
    for it in items:
        by.setdefault(it.get("inventoryId") or "", []).append(it)

    def cell(it, area, extra=""):
        name = it.get("name") or ""
        base = it.get("typeLine") or it.get("baseType") or ""
        gems = ", ".join(_gem_label(g) for g in it.get("socketedItems") or [] if not g.get("abyssJewel"))
        icon = it.get("icon") or ""
        inf = it.get("influences") or {}
        bgk = "Shaper" if (inf.get("shaper") or it.get("shaper")) else "Elder" if (inf.get("elder") or it.get("elder")) else ""
        bg = (f";background:url(https://web.poecdn.com/image/inventory/{bgk}Background.png?w={it.get('w') or 1}&h={it.get('h') or 1})"
              f" center / 100% 100% no-repeat, linear-gradient(180deg, #0e1230 0%, #080a1c 100%)" if bgk else "")
        return (f'<div class="pt-inv pt-tipable {extra}" style="grid-area:{area}{bg}" data-n="{esc(name or base)}" '
                f'data-b="{esc(base if name else "")}" data-c="{RARITY.get(it.get("frameType"), "#c8c8c8")}" '
                f'data-tip="{esc(item_card(it, gems))}">'
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
                      ("Ring2", "4 / 6 / 5 / 7"), ("Trinket", "8 / 1 / 9 / 2")):
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
    tog = '<label class="pt-socktog"><input type="checkbox" checked> Sockets</label>'
    return (f'<div class="pt-geardoll"><div class="pt-gearhead"><span class="pt-snaphead">Gear</span>{swap}{tog}</div>'
            f'<div class="pt-paperdoll"><div class="grid">{html_}</div></div></div>')


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
    """One card per linked group, the gems drawn as the chain of sockets they sit in,
    so you can see which supports are linked to which skills."""
    order = [k for k, _ in SLOTS]
    cards = ""
    for it in sorted(items, key=lambda i: order.index(i.get("inventoryId")) if i.get("inventoryId") in order else 99):
        if it.get("inventoryId") in ("Weapon2", "Offhand2"):
            continue
        socks = it.get("sockets") or []
        gems = {g.get("socket"): g for g in it.get("socketedItems") or [] if not g.get("abyssJewel")}
        if not gems:
            continue
        groups: dict = {}
        for i, sk in enumerate(socks):
            groups.setdefault(sk.get("group", 0), []).append(i)
        if not socks:                        # no socket info: one group
            groups = {0: sorted(gems)}
        label = dict(SLOTS).get(it.get("inventoryId"), it.get("inventoryId") or "")
        granted = _item_supports(it)
        for grp in sorted(groups):
            idxs = groups[grp]
            gl = [gems[i] for i in idxs if i in gems]
            if not gl:
                continue
            actives = [g for g in gl if not g.get("support")]
            chain = ""
            for n, i in enumerate(idxs):
                g = gems.get(i)
                col = _socket_colour(socks[i]) if i < len(socks) else "#777"
                if n:
                    chain += '<i class="lk"></i>'
                if not g:
                    chain += f'<span class="gs empty" style="--sc:{col}"><b></b><small>empty</small></span>'
                    continue
                lvl, qual = _gem_props(g)
                sup = bool(g.get("support"))
                name = g.get("typeLine") or g.get("baseType") or "?"
                short = name.replace(" Support", "")
                img = f'<img src="{esc(g["icon"])}" alt="" loading="lazy">' if g.get("icon") else ""
                chain += (f'<span class="gs pt-tipable{" sup" if sup else ""}" style="--sc:{col}" '
                          f'data-tip="{esc(item_card(g))}">'
                          f'<b>{img}</b>'
                          f'<em>{esc(lvl or "?")}{("/" + esc(qual) + "%") if qual else ""}</em>'
                          f'<small>{esc(short)}</small></span>')
            for lvl_, nm in granted:          # supports the item itself gives every gem in it
                chain += ('<i class="lk ext"></i>'
                          f'<span class="gs sup granted pt-tipable" data-n="{esc(nm)}" data-c="#c9a35a" '
                          f'data-s="{esc("Supports every gem socketed in this item")}" data-a="From the item\'s mods">'
                          f'<b><span class="gi">✦</span></b><em>{esc(lvl_)}</em><small>{esc(nm.replace(" Support", ""))}</small></span>')
            linked = len(idxs) + len(granted)     # item-granted supports count as extra links
            why = (f' title="{len(idxs)} linked sockets + {len(granted)} from the item\'s mods"' if granted else "")
            what = (", ".join(g.get("typeLine") or "?" for g in actives) or "Supports only")
            cards += (f'<div class="pt-skill"><div class="hd">'
                      + (f'<img src="{esc(it.get("icon") or "")}" alt="" loading="lazy">' if it.get("icon") else "")
                      + f'<span class="sl">{esc(label)}</span><span class="ln"{why}>{linked}-Link</span>'
                      f'<span class="wh">{esc(what)}</span></div><div class="chain">{chain}</div></div>')
    return cards


def _item_supports(it: dict) -> list[tuple[str, str]]:
    """Supports an item gives its socketed gems: "Socketed Gems are Supported by Level 20 Added Fire Damage"."""
    import re
    out = []
    pat = re.compile(r"Socketed (?:Gems|Skill Gems|Spells|Attacks|\w+ Gems) are Supported by Level (\d+) (.+)", re.I)
    for key in ("implicitMods", "explicitMods", "craftedMods", "fracturedMods", "enchantMods", "mutatedMods"):
        for m in it.get(key) or []:
            x = pat.search(_mod_text(m))
            if x:
                out.append((x.group(1), x.group(2).strip()))
    return out


_JEWEL_EDGE = {0: "#6b6862", 1: "#5a5ab0", 2: "#a69a3e", 3: "#9a5a2a", 9: "#5a8a48"}


def _jewels_html(tree_jewels: list[dict], abyss: list[dict]) -> str:
    """Jewels as icon tiles (hover for the card), grouped: cluster, regular, abyss; any number fit."""
    cluster = [j for j in tree_jewels if "Cluster Jewel" in (j.get("typeLine") or j.get("baseType") or "")]
    regular = [j for j in tree_jewels if j not in cluster]
    out = ""
    for title, js in (("Cluster jewels", cluster), ("Jewels", regular), ("Abyss jewels (in gear)", abyss)):
        if js:
            out += (f'<div class="pt-jewelgrp"><div class="k">{title} · {len(js)}</div><div class="pt-jewels">'
                    + "".join(_jewel_row(j) for j in js) + "</div></div>")
    return out


def _jewel_row(j: dict) -> str:
    col = _JEWEL_EDGE.get(j.get("frameType"), "#4a4134")
    return (f'<div class="pt-jewel pt-tipable" style="--rc:{col}" data-tip="{esc(item_card(j))}">'
            + (f'<img src="{esc(j.get("icon") or "")}" alt="" loading="lazy">' if j.get("icon")
               else f'<span>{esc(_item_name(j)[:2])}</span>') + "</div>")
