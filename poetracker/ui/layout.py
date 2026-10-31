"""Page frame (navigation, header, filters, status) and shared state."""
from __future__ import annotations

import json
import threading
import time
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
]
SETTINGS = ("/settings", "Settings", "settings")


class State:
    """Things every page needs: config, tracker status, remembered filters."""

    def __init__(self):
        self.cfg: config_mod.Config | None = None
        self.tracker = None
        self.updater = None
        self.snaps = None          # profile snapshots (profile.Snapshotter)
        self.dev = False
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
        n = self._counts()
        if league and self.cfg and league != metrics.current_league(self.cfg):
            return ("past", st.get("data_gen"), st.get("phase"), tuple(n))
        return (st.get("last_event_utc"), st.get("data_gen"), st.get("phase"), tuple(n))

    def _counts(self) -> tuple:
        """Rows you add by hand (currency, copied maps); re-read at most once a second."""
        now = time.monotonic()
        hit = getattr(self, "_counts_hit", None)
        if hit and now - hit[0] < 1.0:
            return hit[1]
        try:
            c = self.con()
            n = tuple(c.execute("SELECT (SELECT COUNT(*) FROM currency_snapshot), (SELECT COUNT(*) FROM map_capture)").fetchone())
            c.close()
        except Exception:
            n = (0, 0)
        self._counts_hit = (now, n)
        return n

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
# Start Campaign is open (plus Overview and Settings); then League Start
# Mapping is added until league start ends; then everything, Standard included.
# Closed pages stay in the menu, dimmed with a lock, saying what opens them.
ALWAYS = {"/", "/settings"}
OPEN_IN = {"campaign": ALWAYS | {"/campaign"}, "mapping": ALWAYS | {"/campaign", "/mapping"}}
PHASE_PAGE = {"campaign": "/campaign", "mapping": "/mapping"}


def league_start() -> dict:
    """The current league's league start phase, honouring the off switch and
    the per-league unlock in Settings."""
    if not STATE.cfg or not STATE.cfg.settings.get("league_start_mode", True):
        return {"phase": "done", "off": True}
    dev = dev_override()
    try:
        if dev:
            st = STATE.cached(("league_start", dev["league"]),
                              lambda c: metrics.league_start_status(c, STATE.cfg, dev["league"]), league=dev["league"])
            if dev.get("phase") in ("campaign", "mapping", "done"):
                st = {**st, "real_phase": st["phase"], "phase": dev["phase"]}
            return {**st, "dev": True}
        st = STATE.cached(("league_start",), lambda c: metrics.league_start_status(c, STATE.cfg))
    except Exception:
        return {"phase": "done"}
    if st.get("league") and STATE.pref("ls_unlocked") == st["league"] and st["phase"] != "done":
        return {**st, "real_phase": st["phase"], "phase": "done", "unlocked": True}
    return st


def dev_mode() -> bool:
    """Developer mode: dev_mode: true in settings.yaml, or --dev on a developer
    (source) copy. An installed copy ignores --dev, so people who install it
    don't stumble into it."""
    from .. import updater as updater_mod
    if STATE.cfg and STATE.cfg.settings.get("dev_mode"):
        return True
    return bool(STATE.dev and not updater_mod.installed_copy())


def dev_override() -> dict | None:
    """In developer mode: the league and phase League Start is forced to
    (Settings → Developer), or None when it's left automatic."""
    if not dev_mode():
        return None
    d = STATE.pref("dev_league_start") or {}
    if not d.get("league") or d["league"] not in STATE.league_names():
        return None
    return d


def is_open(path: str) -> bool:
    st = league_start()
    return path in OPEN_IN.get(st["phase"], {path})


def unlock_text(path: str) -> str:
    """What opens a page that's closed during league start."""
    st = league_start()
    if path == "/mapping" and st["phase"] == "campaign":
        return "Opens when your first character finishes Act 10."
    days = int((STATE.cfg.settings or {}).get("league_start_days", 14) or 14) if STATE.cfg else 14
    when = f" ({fmt.when(st['end_utc'])} at the latest)" if st.get("end_utc") else ""
    return f"Opens when league start ends: your 4th Voidstone or {days} days after launch{when}."


def locked(path: str) -> bool:
    """Call first thing in a page: when the page is closed during league start,
    say what opens it, go to the page that's open instead and return True."""
    if is_open(path):
        return False
    ui.notify(unlock_text(path), position="top", type="info", timeout=4000)
    ui.navigate.to(PHASE_PAGE.get(league_start()["phase"], "/"))
    return True


def status_text() -> tuple[str, str, str]:
    """(state, text, tooltip); state is ok / busy / problem."""
    st = STATE.tracker.status() if STATE.tracker else {}
    if not st.get("log_found"):
        return "problem", "Client.txt not found", "Set the path on the Settings page."
    if st.get("error"):
        return "problem", "Problem reading the log", st["error"]
    if st.get("phase") != "live":
        p = st.get("progress")
        return "busy", f"{st.get('phase', '').capitalize()}{f' {p:.0%}' if p is not None else ''}…", ""
    return ("ok", f"Reading Client.txt · last activity {fmt.ago(st.get('last_event_utc'))}",
            "The tracker reads the game's log file as it's written. This is how long ago the game last wrote "
            "something the tracker uses (entering an area, a level-up, a death...).")


STATUS_ICON = {"ok": ("o_menu_book", "var(--ex-gold, #c9a35a)"), "busy": ("o_hourglass_top", "#e0a050"),
               "problem": ("o_report", "#e06050")}


def version_line() -> tuple[str, str, bool]:
    """(text, tooltip, update_ready) for the version shown at the bottom of the side menu."""
    up = STATE.updater.state if STATE.updater else {}
    ver = (up.get("version") or "").split(" · ")
    short = ver[0] if ver and ver[0] else None
    when = f"Version {short}, released {ver[1]}" if len(ver) > 1 else (up.get("version") or "")
    if up.get("available"):
        n = up.get("behind") or 0
        return (f"Update ready · {n} change{'s' if n != 1 else ''}", f"You have {when or 'an older version'}", True)
    if not up.get("connected"):
        return ("Not linked to GitHub", "Settings → Updates connects it", False)
    if up.get("error"):
        return (f"Version {short or '?'} · couldn't check", up["error"], False)
    if not up.get("checked"):
        return (f"Version {short or '?'} · checking…", when, False)
    return (f"Version {short or '?'} · up to date", when, False)


def build_shell() -> None:
    """The parts every page shares (side menu, top bar), built once per window.
    Pages are swapped inside it without reloading (see frame())."""
    client = ui.context.client
    pt: dict = {}
    client.pt = pt
    ui.add_css(CSS)
    exile = (STATE.cfg.settings.get("theme") if STATE.cfg else "exile") != "classic"
    primary = "#d9a441"
    if exile:
        ui.add_css(EXILE_CSS)
        ui.add_css(palette_css())
        primary = DEFAULT_ACCENT
    ui.dark_mode(True)
    ui.colors(primary=primary, secondary="#4fb3a5", accent="#a68bd6", dark="#1d1916", dark_page="#14110f")

    mini = bool(STATE.pref("drawer_mini", False))
    drawer = ui.left_drawer(value=True, fixed=True).props(
        f"width=268 mini-width=56 bordered breakpoint=700{' mini' if mini else ''}").classes("q-pa-none column no-wrap")
    ui.query("body").classes(add="pt-mini" if mini else "", remove="" if mini else "pt-mini")

    def toggle_mini():
        now = not bool(STATE.pref("drawer_mini", False))
        STATE.set_pref("drawer_mini", now)
        drawer.props(add="mini") if now else drawer.props(remove="mini")
        ui.run_javascript(f"document.body.classList.toggle('pt-mini', {str(now).lower()})")
        toggle_icon.set_name("chevron_right" if now else "chevron_left")

    def nav_item(label, icon, on_click, active=False, trailing=None, tip=None, lock=None):
        with ui.item(on_click=on_click).classes("active" if active else "pt-locked" if lock else "") as it:
            with ui.item_section().props("avatar").style("min-width:34px"):
                ui.icon(icon, size="20px")
            ui.item_section(label).classes("q-mini-drawer-hide").style("white-space:nowrap")
            if trailing or lock:
                with ui.item_section().props("side").classes("q-mini-drawer-hide"):
                    ui.icon("o_lock" if lock else trailing, size="15px").style("color:var(--ex-dim, #6f665a)")
            # names show on hover only while the menu is collapsed to icons; a locked
            # page always says what opens it
            with ui.tooltip().props('anchor="center right" self="center left" :offset="[10, 0]"').classes(
                    "text-body2" + ("" if lock else " pt-nav-tip")):
                ui.label(tip or label).classes("text-weight-medium" if lock else "")
                if lock:
                    ui.label(lock).style("max-width:260px;opacity:.85")
        return it

    with drawer:
        with ui.row().classes("items-center gap-3 q-pt-lg q-pb-md no-wrap pt-logo"):
            ui.html('<img src="/static/icon.svg" alt="" style="width:30px;height:30px;display:block;'
                    'filter:drop-shadow(0 0 6px rgba(217,164,65,.35))">')
            ui.label("PoE Tracker").classes("text-weight-bold q-mini-drawer-hide")
        nav_list = ui.list().classes("pt-nav w-full")

        def draw_nav(path: str) -> None:
            nav_list.clear()
            with nav_list:
                items = NAV
                if league_start()["phase"] in PHASE_PAGE:      # the league start path first, then what it opens
                    first = ("/", "/campaign", "/mapping")
                    items = sorted(NAV, key=lambda n: first.index(n[0]) if n[0] in first else len(first))
                for href, label, icon in items:
                    if is_open(href):
                        nav_item(label, icon, lambda h=href: ui.navigate.to(h), active=href == path)
                    else:
                        why = unlock_text(href)
                        nav_item(label, icon, lambda w=why: ui.notify(w, position="top", type="info", timeout=4000),
                                 tip=f"{label} · locked", lock=why)
            settings_item.classes(add="active") if path == SETTINGS[0] else settings_item.classes(remove="active")
        pt["draw_nav"] = draw_nav
        ui.space()
        with ui.column().classes("w-full gap-0 q-pt-sm pt-drawer-foot"):
            with ui.list().classes("pt-nav w-full"):
                nav_item("Mini Tracker", "picture_in_picture_alt", open_mini, trailing="open_in_new",
                         tip="Mini Tracker (opens a window)")
            ui.element("div").classes("pt-sep")
            with ui.list().classes("pt-nav w-full"):
                href, label, icon = SETTINGS
                settings_item = nav_item(label, icon, lambda: ui.navigate.to(href)).classes("pt-has-toggle")
            ver_box = ui.element("div").classes("pt-ver")

            def draw_version():
                text, tip, ready = version_line()
                head, _, state = text.partition(" · ")
                ok = "up to date" in state
                ver_box.clear()
                with ver_box:
                    if ready:
                        with ui.row().classes("items-center no-wrap gap-2 w-full cursor-pointer").on("click", update_dialog):
                            ui.icon("system_update", size="18px").style("color:var(--ex-gold-hi, #e6c27a)")
                            ui.label(text).classes("q-mini-drawer-hide").style(
                                "font-size:12px;font-weight:600;color:var(--ex-gold-hi, #e6c27a)")
                            ui.tooltip(f"{text} · click to update. {tip}").classes("text-body2")
                        return
                    with ui.row().classes("items-center no-wrap gap-2 w-full"):
                        ui.icon("o_verified" if ok else "o_info", size="18px").style(
                            f"color:{'var(--ex-gold, #c9a35a)' if ok else 'var(--ex-muted, #a69b8c)'}")
                        with ui.column().classes("gap-0 q-mini-drawer-hide"):
                            ui.label(head).style("font-size:11.5px;color:var(--ex-text, #ece4d8);line-height:1.25")
                            if state:
                                ui.label(state.capitalize()).style("font-size:10.5px;color:var(--ex-muted, #a69b8c);"
                                                                   "line-height:1.25")
                        with ui.tooltip().classes("text-body2"):
                            ui.label(f"{text} · {tip}" if tip else text)
                            ui.label("Unofficial fan-made tool, not affiliated with Grinding Gear Games.").style(
                                "opacity:.75;font-size:12px")
            draw_version()
            ui.timer(10, draw_version)
        # round button on the menu's edge, level with Settings: collapse to icons / expand
        with ui.element("div").classes("pt-toggle").on("click", toggle_mini).tooltip("Collapse / expand the menu"):
            toggle_icon = ui.icon("chevron_right" if mini else "chevron_left", size="18px")
        ui.add_body_html("""<script>
(function () {
  function place() {
    const t = document.querySelector('.pt-toggle'), s = document.querySelector('.pt-has-toggle');
    const d = t && t.closest('.q-drawer');
    if (!t || !s || !d) return;
    const r = s.getBoundingClientRect(), dr = d.getBoundingClientRect();
    t.style.top = (r.top - dr.top + r.height / 2 - 13) + 'px';
  }
  window.addEventListener('resize', place);
  setInterval(place, 400);
})();
</script>""")

    with ui.header().classes("items-center no-wrap q-px-lg q-py-sm gap-4 pt-header"):
        # title and page tabs on one line, so every page's top bar is the same height
        with ui.row().classes("items-center no-wrap pt-head").style("gap:28px"):
            pt["title"] = ui.label("").classes("pt-title")
            client.pt_tabs_slot = ui.row().classes("pt-head-tabs")
        ui.space()
        pt["filters"] = ui.row().classes("items-center gap-3 no-wrap")
        status = ui.row().classes("items-center gap-2 text-xs").style("color:var(--muted)")

        def draw_status():
            if getattr(client, "pt_hidden", False):
                return                       # nobody is looking
            color, text, tip = status_text()
            status.clear()
            with status:
                if dev_mode():
                    d = dev_override()
                    ui.badge("DEV" + (f" · {d['league']} · {d.get('phase') or 'auto'}" if d else ""),
                             color="deep-orange").props("outline").tooltip(
                        "Developer mode. League Start can be forced in Settings → Developer.")
                icon, col = STATUS_ICON[color]
                with ui.element("div").classes("pt-stat"):
                    ui.icon(icon, size="18px").style(f"color:{col}")
                    with ui.tooltip().classes("text-body2"):
                        ui.label(text).classes("text-weight-medium")
                        if tip:
                            ui.label(tip).style("max-width:280px;opacity:.85")
                clip_on = bool(STATE.tracker and STATE.tracker.status().get("clipboard"))
                with ui.element("div").classes("pt-stat"):
                    ui.icon("o_content_paste", size="18px").style(
                        f"color:{'var(--ex-gold, #c9a35a)' if clip_on else 'var(--ex-dim, #6f665a)'}")
                    ui.tooltip("Map capture is on: Ctrl+C on a map in game saves it (Maps → Detailed Maps)."
                               if clip_on else "Map capture is off (Settings → General).").classes("text-body2")
                if STATE.updater:
                    STATE.updater.check_soon()          # while the window is open, at most every 90 s

        draw_status()
        ui.timer(5, draw_status)

    # one listener per window for events the pages raise from the browser
    client.pt_events = {}
    client.pt_hidden = False

    def vis(e):
        client.pt_hidden = bool(e.args)
        cb = getattr(client, "pt_on_visible", None)
        if not client.pt_hidden and cb:
            cb()
    ui.on("pt_vis", vis)
    ui.add_body_html("""<script>
document.addEventListener("click", (e) => {
  const a = e.target.closest(".pt-actbar a");
  if (a) { e.preventDefault(); emitEvent("act_jump", a.getAttribute("href").split("-").pop()); return; }
  const s = e.target.closest("a.pt-stone");
  if (s) { e.preventDefault(); emitEvent("stone_jump", s.dataset.i); return; }
  const m = e.target.closest(".pt-mapchip");
  if (m) {                       // flip at once; the server saves it
    const on = !m.classList.contains("on");
    m.classList.toggle("on", on);
    m.title = m.dataset.name + (on ? " · ticked by you just now" : " · unticked by you");
    const box = m.closest(".pt-chipbox"), c = box && box.querySelector(".pt-chipcount");
    if (c) c.textContent = box.querySelectorAll(".pt-mapchip.on").length + " of " + box.dataset.total;
    emitEvent("map_toggle", [m.dataset.name, on]);
  }
});
// ---- atlas tree: scroll to zoom, drag to move, hover card (the view survives page refreshes)
(() => {
  let saved = null, drag = null, lastTip = null;
  const svgOf = (el) => el && el.closest(".pt-atlas")?.querySelector("svg.pt-atlas-svg");
  const getVB = (svg) => svg.getAttribute("viewBox").split(" ").map(Number);
  const setVB = (svg, v) => { svg.setAttribute("viewBox", v.map(n => n.toFixed(1)).join(" ")); saved = v; };
  const zoom = (svg, f, cx, cy) => {
    const v = getVB(svg), full = svg.dataset.vb.split(" ").map(Number);
    let w = Math.min(Math.max(v[2] * f, full[2] / 40), full[2] * 1.2), k = w / v[2], h = v[3] * k;
    setVB(svg, [cx - (cx - v[0]) * k, cy - (cy - v[1]) * k, w, h]);
  };
  const toTree = (svg, e) => {
    const r = svg.getBoundingClientRect(), v = getVB(svg), s = Math.max(v[2] / r.width, v[3] / r.height);
    const ox = v[0] + v[2] / 2 - r.width * s / 2, oy = v[1] + v[3] / 2 - r.height * s / 2;
    return [ox + (e.clientX - r.left) * s, oy + (e.clientY - r.top) * s, s];
  };
  // the wheel is only taken over inside a tree (a page-wide non-passive wheel
  // listener makes every scroll in the app wait for script)
  const onWheel = (e) => {
    const svg = svgOf(e.target); if (!svg) return;
    e.preventDefault();
    const [x, y] = toTree(svg, e);
    zoom(svg, e.deltaY > 0 ? 1.18 : 1 / 1.18, x, y);
  };
  document.addEventListener("pointerdown", (e) => {
    const svg = svgOf(e.target); if (!svg || e.button !== 0 || e.target.closest(".pt-atlas-ctl")) return;
    drag = {svg, x: e.clientX, y: e.clientY, v: getVB(svg), s: toTree(svg, e)[2]};
    svg.classList.add("grab");
  });
  document.addEventListener("pointermove", (e) => {
    const tip = document.getElementById("pt-atlas-tip");
    if (drag) {                      // move the picture while dragging (cheap); redraw once on release
      drag.dx = e.clientX - drag.x; drag.dy = e.clientY - drag.y;
      drag.svg.style.transform = `translate(${drag.dx}px, ${drag.dy}px)`;
      if (tip) tip.style.display = "none";
      return;
    }
    const g = e.target.closest && e.target.closest(".pt-atlas g.nd, .pt-tipable");
    if (!g) { if (tip) tip.style.display = "none"; lastTip = null; return; }
    if (g === lastTip && tip && tip.style.display === "block") {
      const r = tip.getBoundingClientRect();
      tip.style.left = Math.min(e.clientX + 16, window.innerWidth - r.width - 8) + "px";
      tip.style.top = Math.min(e.clientY + 16, window.innerHeight - r.height - 8) + "px";
      return;
    }
    lastTip = g;
    let t = tip;
    if (!t) { t = document.createElement("div"); t.id = "pt-atlas-tip"; document.body.appendChild(t); }
    const esc = (x) => (x || "").replace(/[&<>]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]));
    t.innerHTML = `<b style="${g.dataset.c ? "color:" + g.dataset.c : ""}">${esc(g.dataset.n)}</b>` +
      (g.dataset.b ? `<div style="color:#c8c8c8">${esc(g.dataset.b)}</div>` : "") +
      (g.dataset.s ? g.dataset.s.split("\\n").map(x => `<div>${esc(x)}</div>`).join("") : "") +
      (g.dataset.a ? `<i>${esc(g.dataset.a)}</i>` : "");
    t.style.display = "block";
    const W = window.innerWidth, H = window.innerHeight, r = t.getBoundingClientRect();
    t.style.left = Math.min(e.clientX + 16, W - r.width - 8) + "px";
    t.style.top = Math.min(e.clientY + 16, H - r.height - 8) + "px";
  });
  document.addEventListener("pointerup", () => {
    if (!drag) return;
    const v = drag.v, d = drag;
    d.svg.classList.remove("grab");
    if (d.dx || d.dy) setVB(d.svg, [v[0] - (d.dx || 0) * d.s, v[1] - (d.dy || 0) * d.s, v[2], v[3]]);
    d.svg.style.transform = "";
    drag = null;
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-atlas]"); const svg = svgOf(b); if (!b || !svg) return;
    const v = getVB(svg);
    if (b.dataset.atlas === "fit") setVB(svg, svg.dataset.vb.split(" ").map(Number));
    else zoom(svg, b.dataset.atlas === "in" ? 1 / 1.4 : 1.4, v[0] + v[2] / 2, v[1] + v[3] / 2);
  });
  const seeTree = (svg) => {
    if (svg.dataset.seen) return;
    svg.dataset.seen = "1";
    const box = svg.closest(".pt-atlas");
    if (box && !box.dataset.wheel) { box.dataset.wheel = "1"; box.addEventListener("wheel", onWheel, {passive: false}); }
    if (saved && location.pathname === "/atlas") setVB(svg, saved);
  };
  const loadTree = (el) => {
    if (el.dataset.got) return;
    el.dataset.got = "1";
    fetch(el.dataset.src).then(r => r.text()).then(t => {
      el.innerHTML = t || '<div style="padding:16px;color:#a69b8c">No tree in this snapshot.</div>';
      const svg = el.querySelector("svg.pt-atlas-svg"); if (svg) seeTree(svg);
    }).catch(() => { el.innerHTML = '<div style="padding:16px;color:#e06050">Could not load the tree.</div>'; });
  };
  // look only at what was just added (not the whole page) for trees to wire up
  new MutationObserver((muts) => {
    for (const m of muts) for (const n of m.addedNodes) {
      if (n.nodeType !== 1 || n.closest?.("svg.pt-atlas-svg")) continue;
      if (n.matches(".pt-tree-load[data-src]")) loadTree(n);
      else if (n.matches("svg.pt-atlas-svg")) seeTree(n);
      else if (n.querySelector) {
        n.querySelectorAll(".pt-tree-load[data-src]").forEach(loadTree);
        n.querySelectorAll("svg.pt-atlas-svg").forEach(seeTree);
      }
    }
  }).observe(document.body, {childList: true, subtree: true});
  // tell the tracker when this window is hidden (behind the game, minimised) so it
  // doesn't redraw pages nobody is looking at
  document.addEventListener("visibilitychange", () => emitEvent("pt_vis", document.hidden));
})();
</script>""")


def frame(path: str, title: str, subtitle: str = "", filters: Callable | None = None):
    """Show a page inside the shared layout: set the title, filters and menu
    highlight, and return the column to fill. Switching pages only rebuilds
    this part, so it's quick."""
    client = ui.context.client
    pt = client.pt
    pt["title"].set_text(title)
    pt["title"].props(f'title="{subtitle}"' if subtitle else 'title=""')
    client.pt_tabs_slot.clear()
    pt["filters"].clear()
    if filters:
        with pt["filters"]:
            filters()
    pt["draw_nav"](path)
    return ui.column().classes("w-full q-pa-lg gap-4").style("max-width:1500px")


def on_event(name: str, handler: Callable) -> None:
    """Handle a browser event (emitEvent) on the current page. Registered once per
    window; each page visit just swaps the handler."""
    client = ui.context.client
    events = client.pt_events
    if name not in events:
        ui.on(name, lambda e, n=name: events[n](e) if events.get(n) else None)
    events[name] = handler


def reload_page() -> None:
    """Rebuild the current page (after a filter changes), without reloading the window."""
    sub = getattr(ui.context.client, "pt_sub", None)
    if sub is not None:
        sub.refresh()
    else:
        ui.navigate.reload()


def head_tabs(value: str, tabs: dict, on_change: Callable) -> ui.tabs:
    """Page tabs in the top bar, under the page title. Create them outside a
    page's refreshable content so they survive refreshes."""
    with ui.context.client.pt_tabs_slot:
        with ui.tabs(value=value, on_change=on_change).props("dense align=left no-caps inline-label") as t:
            for name, label in tabs.items():
                ui.tab(name, label)
    return t


def open_mini() -> None:
    from .. import mini as mini_mod
    mini_mod.launch_mini()
    ui.notify("Opening the mini tracker… Drag it into place, then lock it with its 🔒 button.", timeout=6000)


def update_dialog() -> None:
    """What's new on GitHub, with a button that updates and restarts."""
    from nicegui import app, run
    from .. import updater as updater_mod
    up = STATE.updater.state
    # The dialog lives on the page itself, not inside the status bar (which is
    # redrawn every few seconds and would delete it mid-update).
    with ui.context.client.content, ui.dialog() as dlg, ui.card().classes("pt-card").style("min-width:min(520px, 92vw)"):
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
    client = ui.context.client

    def tick():
        if getattr(client, "pt_hidden", False):
            return                      # window hidden: catch up when it's shown again
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
    t = ui.timer(3 if last["busy"] else every, tick)
    client.pt_on_visible = lambda: tick() if not t.is_deleted else None
