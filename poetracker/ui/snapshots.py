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

    # ---- gear
    cells = ""
    for key, label in SLOTS:
        it = by.get(key)
        if not it:
            continue
        gems = _gems(it)
        cells += (f'<div class="pt-item" title="{esc(_mods_tip(it))}">'
                  f'<div class="sl">{label}</div>'
                  f'<div class="nm" style="color:{RARITY.get(it.get("frameType"), "#c8c8c8")}">{esc(_item_name(it))}</div>'
                  + (f'<div class="gm">{esc(" · ".join(gems))}</div>' if gems else "") + "</div>")
    flasks = sorted((i for i in items if i.get("inventoryId") == "Flask"), key=lambda i: i.get("x", 0))
    for it in flasks:
        cells += (f'<div class="pt-item" title="{esc(_mods_tip(it))}"><div class="sl">Flask</div>'
                  f'<div class="nm" style="color:{RARITY.get(it.get("frameType"), "#c8c8c8")}">{esc(_item_name(it))}</div></div>')
    ui.html(f'<div class="pt-gear">{cells}</div>').classes("w-full")

    # ---- passives and jewels
    jewels = (snap.get("passives") or {}).get("items") or []
    asc = (snap["items"].get("character") or {}).get("class") or snap.get("class") or ""
    with ui.row().classes("w-full gap-4 items-start pt-wrap q-mt-sm"):
        with ui.column().classes("gap-1").style("flex:2 1 380px;min-width:0"):
            ui.label(f"Passive tree · {ps['points']} points" + (f" · {ps['asc']} ascendancy ({asc})" if ps["asc"] else "")).classes(
                "text-weight-bold")
            if not ps["known"]:
                ui.label("Getting passive names from GGG's tree export…").classes("pt-note")
            for title, names in (("Keystones", ps["keystones"]), ("Ascendancy", ps["asc_notables"]),
                                 ("Notables", ps["notables"]), ("Masteries", ps["masteries"])):
                if names:
                    ui.html(f'<div class="pt-snaplist"><span class="k">{title}</span> {esc(" · ".join(names))}</div>')
        with ui.column().classes("gap-1").style("flex:1 1 260px;min-width:0"):
            ui.label(f"Jewels · {len(jewels)}").classes("text-weight-bold")
            for j in jewels:
                ui.html(f'<div class="pt-snaplist" title="{esc(_mods_tip(j))}" style="color:'
                        f'{RARITY.get(j.get("frameType"), "#c8c8c8")}">{esc(_item_name(j))}</div>')
    ui.label(f"Read from your profile {fmt.when(snap['ts_utc'])}"
             + (" (nothing had changed, so this shows the snapshot before)" if snap.get("status") == "same" else "")).classes(
        "pt-note q-mt-sm")
