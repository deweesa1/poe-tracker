"""Page frame (navigation, header, filters, status) and shared state."""
from __future__ import annotations

import json
import threading
from typing import Callable

from nicegui import ui

from .. import config as config_mod, db, metrics, paths
from . import fmt
from .widgets import CSS, DEFAULT_ACCENT, EXILE_CSS, palette_css

NAV = [
    ("/", "Overview", "space_dashboard"),
    ("/maps", "Maps", "map"),
    ("/campaign", "League Start Campaign", "flag"),
    ("/mapping", "League Start Mapping", "landscape"),
    ("/character", "Characters", "person"),
    ("/atlas", "Atlas tree", "hub"),
    ("/currency", "Currency", "paid"),
    ("/trades", "Trades", "swap_horiz"),
    ("/standard", "Standard", "insights"),
    ("/settings", "Settings", "settings"),
]


class State:
    """Things every page needs: config, tracker status, remembered filters."""

    def __init__(self):
        self.cfg: config_mod.Config | None = None
        self.tracker = None
        self.updater = None
        self._prefs: dict = {}
        self._lock = threading.Lock()
        self._cache: dict = {}

    # remembered filter choices (kept in prefs.json in the data folder)
    def load_prefs(self) -> None:
        try:
            self._prefs = json.loads((paths.data_dir() / "prefs.json").read_text(encoding="utf-8"))
        except Exception:
            self._prefs = {}

    def pref(self, key: str, default=None):
        return self._prefs.get(key, default)

    def set_pref(self, key: str, value) -> None:
        self._prefs[key] = value
        try:
            (paths.data_dir() / "prefs.json").write_text(json.dumps(self._prefs), encoding="utf-8")
        except Exception:
            pass

    # database access with a small cache that is dropped whenever new data arrives
    def con(self):
        return db.connect(readonly=True)

    def version(self, league: str | None = None) -> tuple:
        """What cached results depend on. A league that has ended can't get new
        game data, so its results stay valid while you play (until a rebuild)."""
        st = self.tracker.status() if self.tracker else {}
        try:
            c = self.con()
            n = c.execute("SELECT (SELECT COUNT(*) FROM currency_snapshot), (SELECT COUNT(*) FROM map_capture)").fetchone()
            c.close()
        except Exception:
            n = (0, 0)
        if league and self.cfg and league != metrics.current_league(self.cfg):
            return ("past", st.get("data_gen"), st.get("phase"), tuple(n))
        return (st.get("last_event_utc"), st.get("data_gen"), st.get("phase"), tuple(n))

    def cached(self, key: tuple, fn: Callable, league: str | None = None):
        v = self.version(league)
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == v:
                return hit[1]
        con = self.con()
        try:
            out = fn(con)
        finally:
            con.close()
        with self._lock:
            self._cache[key] = (v, out)
            if len(self._cache) > 600:
                self._cache.clear()
        return out

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    def league_names(self) -> list[str]:
        return [l["name"] for l in self.cached(("leagues",), lambda c: metrics.leagues(c, self.cfg))]

    def league(self) -> str | None:
        names = self.league_names()
        lg = self.pref("league") or self.cfg.settings.get("current_league")
        return lg if lg in names else (names[0] if names else None)

    def characters(self, league: str | None) -> list[dict]:
        return self.cached(("chars", league), lambda c: metrics.own_characters(c, league), league=league)

    def character(self, league: str | None) -> int | None:
        cid = self.pref("character")
        ids = [c["id"] for c in self.characters(league)]
        return cid if cid in ids else None


STATE = State()


# ---- league start mode ----------------------------------------------------
# From league launch until the first character finishes Act 10 only League
# Start Campaign is open (plus Overview, Standard, Settings); then League Start
# Mapping is added until all four Voidstones; then everything.
ALWAYS = {"/", "/standard", "/settings"}
OPEN_IN = {"campaign": ALWAYS | {"/campaign"}, "mapping": ALWAYS | {"/campaign", "/mapping"}}
PHASE_PAGE = {"campaign": "/campaign", "mapping": "/mapping"}


def league_start() -> dict:
    """The current league's league start phase, honouring the off switch and
    the per-league unlock in Settings."""
    if not STATE.cfg or not STATE.cfg.settings.get("league_start_mode", True):
        return {"phase": "done", "off": True}
    try:
        st = STATE.cached(("league_start",), lambda c: metrics.league_start_status(c, STATE.cfg))
    except Exception:
        return {"phase": "done"}
    if st.get("league") and STATE.pref("ls_unlocked") == st["league"] and st["phase"] != "done":
        return {**st, "real_phase": st["phase"], "phase": "done", "unlocked": True}
    return st


def is_open(path: str) -> bool:
    st = league_start()
    return path in OPEN_IN.get(st["phase"], {path})


def locked(path: str):
    """Call first thing in a page: returns a redirect when that page is
    hidden during league start."""
    if is_open(path):
        return None
    from fastapi.responses import RedirectResponse
    return RedirectResponse(PHASE_PAGE.get(league_start()["phase"], "/"))


def status_text() -> tuple[str, str, str]:
    st = STATE.tracker.status() if STATE.tracker else {}
    if not st.get("log_found"):
        return "red", "Client.txt not found", "Set the path on the Settings page."
    if st.get("error"):
        return "red", "Problem reading the log", st["error"]
    if st.get("phase") != "live":
        p = st.get("progress")
        return "amber", f"{st.get('phase', '').capitalize()}{f' {p:.0%}' if p is not None else ''}…", ""
    return ("green", f"Tracking · last in-game activity {fmt.ago(st.get('last_event_utc'))}",
            "The tracker is reading Client.txt live. This is how long ago the game last wrote "
            "something the tracker uses (entering an area, a level-up, a death...).")


def frame(path: str, title: str, subtitle: str = "", filters: Callable | None = None):
    """Draw the shared layout. Returns the content column to fill."""
    ui.add_css(CSS)
    exile = (STATE.cfg.settings.get("theme") if STATE.cfg else "exile") != "classic"
    primary = "#d9a441"
    if exile:
        ui.add_css(EXILE_CSS)
        ui.add_css(palette_css())
        primary = DEFAULT_ACCENT
    ui.dark_mode(True)
    ui.colors(primary=primary, secondary="#4fb3a5", accent="#a68bd6", dark="#1d1916", dark_page="#14110f")

    with ui.left_drawer(value=True, fixed=True).props("width=252 bordered breakpoint=700").classes("q-pa-none"):
        with ui.row().classes("items-center gap-3 q-px-md q-pt-lg q-pb-md"):
            ui.html('<div style="width:14px;height:14px;background:var(--lg, #d9a441);transform:rotate(45deg);border-radius:2px;'
                    'box-shadow:0 0 12px var(--lg-a50, rgba(217,164,65,.5))"></div>')
            ui.label("PoE Tracker").classes("text-weight-bold")
        ls = league_start()
        with ui.list().classes("pt-nav w-full"):
            for href, label, icon in NAV:
                if not is_open(href):
                    continue
                with ui.item(on_click=lambda h=href: ui.navigate.to(h)).classes("active" if href == path else ""):
                    with ui.item_section().props("avatar").style("min-width:34px"):
                        ui.icon(icon, size="20px")
                    ui.item_section(label).style("white-space:nowrap")
        from .. import mini as mini_mod
        with ui.column().classes("q-px-md q-pt-md gap-1 w-full"):
            ui.button("Mini Tracker", icon="picture_in_picture_alt", on_click=open_mini).props(
                "outline no-caps").classes("w-full pt-mini-btn").tooltip("A small always-on-top window for live tracking")
            ui.label(f"{mini_mod.hotkey_label(STATE.cfg.settings if STATE.cfg else None)} locks / unlocks it").classes(
                "pt-note").style("font-size:11px;text-align:center;width:100%")
        if ls["phase"] in PHASE_PAGE:
            text = ("Campaign · finish Act 10 to open League Start Mapping" if ls["phase"] == "campaign" else
                    f"Mapping · {ls['voidstones']} of {ls['voidstones_total']} Voidstones. All four open the other dashboards")
            chars = [f"Campaign: {ls['campaign_name']}" if ls.get("campaign_name") else None,
                     f"Mapping: {ls['mapping_name']}" if ls.get("mapping_name") else None]
            with ui.column().classes("q-px-md q-pt-md gap-1"):
                ui.label("League start").classes("text-xs text-weight-bold").style("color:#d9a441;letter-spacing:.06em;text-transform:uppercase")
                ui.label(text).classes("pt-note").style("font-size:12px;line-height:1.35")
                for c in chars:
                    if c:
                        ui.label(c).classes("pt-note").style("font-size:12px;color:#ece4d8")

    with ui.header().classes("items-center q-px-lg q-py-sm gap-4"):
        with ui.column().classes("gap-0"):
            ui.label(title).classes("pt-title")
            if subtitle:
                ui.label(subtitle).classes("pt-sub text-sm")
        ui.space()
        if filters:
            with ui.row().classes("items-center gap-3"):
                filters()
        status = ui.row().classes("items-center gap-2 text-xs").style("color:var(--muted)")

        def draw_status():
            color, text, tip = status_text()
            status.clear()
            with status:
                ui.icon("circle", size="10px", color=color)
                lbl = ui.label(text)
                if tip:
                    lbl.tooltip(tip)
                ui.button(icon="picture_in_picture_alt", on_click=open_mini).props(
                    "flat round dense size=sm").tooltip("Open the mini tracker (always on top)")
                up = STATE.updater.state if STATE.updater else {}
                if up.get("available"):
                    ui.button(f"Update available ({up['behind']})", icon="system_update",
                              on_click=update_dialog).props("dense unelevated size=sm color=primary text-color=dark").classes(
                        "q-px-sm")
                if STATE.tracker and STATE.tracker.status().get("clipboard"):
                    ui.icon("content_paste", size="16px").tooltip(
                        "Map capture is on: Ctrl+C on a map in game saves it (see Maps → Detailed Maps).")

        draw_status()
        ui.timer(5, draw_status)

    return ui.column().classes("w-full q-pa-lg gap-4").style("max-width:1500px")


def open_mini() -> None:
    from .. import mini as mini_mod
    mini_mod.launch_mini()
    hk = mini_mod.hotkey_label(STATE.cfg.settings if STATE.cfg else None)
    ui.notify(f"Opening the mini tracker… Drag it into place, then press {hk} to lock it "
              f"(clicks pass through to the game). {hk} again unlocks it.", timeout=8000)


def update_dialog() -> None:
    """What's new on GitHub, with a button that updates and restarts."""
    from nicegui import app, run
    from .. import updater as updater_mod
    up = STATE.updater.state
    with ui.dialog() as dlg, ui.card().classes("pt-card").style("min-width:min(520px, 92vw)"):
        ui.label("Update Available").classes("pt-h2")
        ui.label(f"{up['behind']} change{'s' if up['behind'] != 1 else ''} since your version "
                 f"({up.get('version') or '?'}):").classes("pt-sub")
        with ui.column().classes("gap-1 q-my-sm"):
            for c in up.get("changes") or []:
                ui.label(f"• {c}").classes("text-sm")
        msg = ui.label("").classes("pt-note")

        async def go():
            btn.disable()
            msg.set_text("Downloading the update…")
            ok, text = await run.io_bound(STATE.updater.apply)
            if not ok:
                msg.set_text(text)
                btn.enable()
                return
            msg.set_text("Updated. Restarting the tracker…")
            updater_mod.restart_app()
            app.shutdown()
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Later", on_click=dlg.close).props("flat")
            btn = ui.button("Update and restart", icon="system_update", on_click=go).props("unelevated")
    dlg.open()


def league_select(on_change: Callable, label: str = "League") -> None:
    names = STATE.league_names()
    def changed(e):
        STATE.set_pref("league", e.value)
        on_change()
    ui.select(names, value=STATE.league(), label=label, on_change=changed).props("dense outlined dark").style("min-width:220px")


def character_select(on_change: Callable) -> None:
    lg = STATE.league()
    chars = STATE.characters(lg)
    opts = {0: "All characters", **{c["id"]: f"{c['name']} · {c['class'] or ''} {c['level'] or ''}" for c in chars}}
    def changed(e):
        STATE.set_pref("character", e.value or None)
        on_change()
    ui.select(opts, value=STATE.character(lg) or 0, label="Character", on_change=changed).props(
        "dense outlined dark").style("min-width:240px")


def busy() -> bool:
    """True while the tracker is reading the whole log or rebuilding."""
    st = STATE.tracker.status() if STATE.tracker else {}
    return st.get("phase") not in (None, "live", "no log")


def auto_refresh(refresh: Callable, every: float = 10) -> None:
    """Re-draw the page body when new game data has been read. After a
    rebuild or first read finishes, reload the whole page so the filters
    (league and character lists) are refreshed too."""
    last = {"v": STATE.version(), "busy": busy()}

    def tick():
        b = busy()
        if last["busy"] and not b:
            STATE.invalidate()
            ui.navigate.reload()
            return
        last["busy"] = b
        v = STATE.version()
        if v != last["v"] and not b:
            last["v"] = v
            refresh()
    ui.timer(3 if last["busy"] else every, tick)
