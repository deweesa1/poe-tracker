"""The always-on-top mini window's page (/mini): live campaign or mapping
progress at a glance. The window itself is opened by poetracker.mini."""
from __future__ import annotations

import json

from nicegui import ui

from .. import metrics
from . import fmt
from .layout import STATE, busy
from .widgets import palette_css

MINI_CSS = """
@font-face { font-family: 'Cinzel'; font-weight: 600; src: url('/static/fonts/cinzel-latin-600-normal.woff2') format('woff2'); }
@font-face { font-family: 'Cinzel'; font-weight: 700; src: url('/static/fonts/cinzel-latin-700-normal.woff2') format('woff2'); }
html, body { margin: 0; background: transparent; overflow: hidden; user-select: none; }
.nicegui-content { padding: 0 !important; }
.q-page, .q-layout, .q-page-container { background: transparent !important; min-height: 0 !important; }
.mini { box-sizing: border-box; width: 100vw; height: 100vh; padding: 10px 12px 6px; overflow: hidden;
  display: flex; flex-direction: column;
  font-family: "Segoe UI", system-ui, sans-serif; color: var(--ex-text);
  background: linear-gradient(180deg, var(--ex-panel) 0%, var(--ex-panel-2) 100%);
  border: 1px solid var(--ex-line); box-shadow: inset 0 0 0 1px #000, inset 0 0 0 2px var(--ex-a10); }
.mini.unlocked { border-color: var(--ex-gold); }
.m-top { display: flex; align-items: center; gap: 6px; font-family: 'Cinzel', serif; font-weight: 600; font-size: 11px;
  letter-spacing: .05em; color: var(--ex-muted); white-space: nowrap; overflow: hidden; }
.m-top .m-lg { color: var(--ex-gold-hi); overflow: hidden; text-overflow: ellipsis; flex: 0 0 auto; max-width: 70%; }
.m-top .ch { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; color: var(--ex-dim); }
.m-top .sp { flex: 1 1 0; min-width: 0; }
.m-lock { color: var(--ex-dim); font-size: 11px; }
.m-clock { font-size: 34px; font-weight: 700; line-height: 1.1; margin-top: 4px; color: var(--ex-value);
  font-variant-numeric: tabular-nums; letter-spacing: .01em; }
.m-clock .pct { font-size: 15px; color: var(--ex-gold); margin-left: 8px; font-weight: 600; }
.m-where { font-size: 13px; color: var(--ex-gold-hi); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.m-row { display: flex; gap: 12px; font-size: 12px; color: var(--ex-muted); margin-top: 3px; font-variant-numeric: tabular-nums; }
.m-row b { color: var(--ex-text); font-weight: 600; }
.m-h { font-family: 'Cinzel', serif; font-weight: 600; font-size: 10.5px; letter-spacing: .08em; color: var(--ex-gold);
  margin: 9px 0 3px; border-bottom: 1px solid var(--ex-line-dim); padding-bottom: 2px; }
.m-splits { display: grid; grid-template-columns: 1fr 1fr; column-gap: 12px; }
.m-split { display: flex; gap: 6px; font-size: 12px; font-variant-numeric: tabular-nums; line-height: 1.55; white-space: nowrap; }
.m-split .a { width: 24px; color: var(--ex-muted); } .m-split .t { flex: 1; } .m-split .d { color: var(--ex-dim); font-size: 11px; }
.m-split.cur .a, .m-split.cur .t { color: var(--ex-gold-hi); } .m-split.todo { color: var(--ex-dim); }
.m-labs { display: flex; gap: 10px; font-size: 12px; margin-top: 3px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.m-labs span { color: var(--ex-muted); } .m-labs b { color: var(--ex-text); font-weight: 600; }
.m-where .pct { color: var(--ex-gold); font-weight: 600; margin-left: 6px; }
.m-btns { position: fixed; top: 7px; right: 8px; display: flex; gap: 2px; z-index: 5; }
.m-btns span { cursor: pointer; color: var(--ex-muted); font-size: 13px; padding: 1px 4px; border-radius: 3px; }
.m-btns span:hover { color: var(--ex-gold-hi); background: var(--ex-a10); }
.m-btns .x { display: none; } .mini.unlocked .m-btns .x { display: inline; }
.m-top { padding-right: 64px; }
.mini.collapsed .m-hide, .mini.collapsed .m-foot, .mini.collapsed .m-grip { display: none !important; }
.mini.collapsed .m-clock { margin-top: 0; padding-right: 64px; }
.m-next { font-size: 12.5px; line-height: 1.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.m-next .k { color: var(--ex-muted); display: inline-block; width: 44px; }
.m-bar { display: flex; gap: 2px; height: 16px; margin-top: 7px; }
.m-bar div { flex: 1; background: var(--ex-line-dim); border-radius: 2px; position: relative; overflow: hidden; min-width: 0; }
.m-bar div i { position: absolute; inset: 0; background: var(--ex-gold); }
.m-bar div b { position: relative; display: block; text-align: center; font-size: 9.5px; line-height: 16px; font-weight: 700;
  color: var(--ex-muted); white-space: nowrap; overflow: hidden; }
.m-bar div.full b { color: #15120b; }
.m-bar div i.cur { background: var(--ex-cur); }
.m-bar div i.skip { background: var(--ex-line); }
.m-dim { color: var(--ex-dim); font-size: 12px; margin-top: 8px; }
.m-body { flex: 1 1 auto; min-height: 0; overflow: hidden; }
.m-foot { flex: 0 0 auto; padding-top: 4px; font-size: 10.5px; color: var(--ex-dim);
  display: flex; justify-content: space-between; gap: 6px; white-space: nowrap; overflow: hidden; }
.m-cut { display: none !important; }
.m-foot .when-unlocked { display: none; color: var(--ex-gold); }
.mini.unlocked .m-foot .when-unlocked { display: inline; }
.m-grip { display: none; position: fixed; right: 0; bottom: 0; width: 18px; height: 18px; cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 0 50%, var(--ex-gold) 50% 58%, transparent 58% 70%,
  var(--ex-gold) 70% 78%, transparent 78%); opacity: .8; }
.mini.unlocked .m-grip { display: block; } .mini.unlocked .m-foot .when-locked { display: none; }
"""

TICK_JS = """
<script>
(function () {
  function hms(s) { s = Math.max(0, Math.floor(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
    return h + ':' + String(m).padStart(2, '0') + ':' + String(x).padStart(2, '0'); }
  function tick() {
    const now = Date.now();
    document.querySelectorAll('[data-base]').forEach(el => {
      let s = parseFloat(el.dataset.base);
      const a = el.dataset.anchor;
      if (a && el.dataset.on === '1') s += Math.min((now - Date.parse(a)) / 1000, 600);
      el.firstChild ? (el.firstChild.nodeValue = hms(s)) : (el.textContent = hms(s));
    });
  }
  setInterval(tick, 1000);
  window.ptMiniTick = tick;
  window.ptSetLocked = function (locked) {
    document.querySelectorAll('.mini').forEach(el => el.classList.toggle('unlocked', !locked));
    window.ptLocked = locked;
    const b = document.querySelector('.m-btns .l');
    if (b) { b.textContent = locked ? '🔒' : '🔓'; b.title = locked ? 'Unlock to move or resize' : 'Lock in place'; }
  };
  window.ptSetCollapsed = function (c) {
    window.ptCollapsed = c;
    document.querySelectorAll('.mini').forEach(el => el.classList.toggle('collapsed', c));
    const b = document.querySelector('.m-btns .c');
    if (b) { b.textContent = c ? '▸' : '▾'; b.title = c ? 'Show splits' : 'Only the timer and bar'; }
    if (!c) window.ptFit && window.ptFit();
  };
  window.ptToggleCollapse = function () {
    const c = !window.ptCollapsed;
    window.ptSetCollapsed(c);
    // tell the window how tall the collapsed view is, so it can shrink to it
    const body = document.querySelector('.m-body');
    const need = body ? Math.ceil(body.scrollHeight + 18) : 0;
    ptApi('set_collapsed', c, need);
  };
  window.ptToggleLock = function () { ptApi('set_lock', !(window.ptLocked !== false)); };
  // locked: it stays where it is (no dragging), buttons still work
  document.addEventListener('mousedown', (e) => {
    if (window.ptLocked !== false && !e.target.closest('.m-btns')) e.stopPropagation();
  }, true);
  // Small window: drop whole sections from the bottom (highest data-p first)
  // instead of cutting text in half.
  window.ptFit = function () {
    const body = document.querySelector('.m-body');
    if (!body) return;
    const opts = Array.from(body.querySelectorAll('[data-p]'));
    opts.forEach(el => el.classList.remove('m-cut'));
    opts.sort((a, b) => b.dataset.p - a.dataset.p);
    for (const el of opts) {
      if (window.ptCollapsed || body.scrollHeight <= body.clientHeight + 1) break;
      el.classList.add('m-cut');
    }
  };
  window.addEventListener('resize', () => window.ptFit());
  window.ptApi = function (name, ...args) { try { window.pywebview.api[name](...args); } catch (e) {} };
  // corner grip: frameless windows have no border to resize from
  let rs = null, rsT = 0;
  document.addEventListener('pointerdown', (e) => {
    const g = e.target.closest('.m-grip');
    if (!g || window.ptLocked !== false) return;
    e.preventDefault(); e.stopPropagation();
    g.setPointerCapture(e.pointerId);
    rs = {x: e.screenX, y: e.screenY, w: window.innerWidth, h: window.innerHeight, g: g};
  }, true);
  document.addEventListener('pointermove', (e) => {
    if (!rs) return;
    const now = Date.now();
    if (now - rsT < 30) return;
    rsT = now;
    ptApi('resize', rs.w + e.screenX - rs.x, rs.h + e.screenY - rs.y);
  }, true);
  const rsEnd = (e) => { if (rs) { ptApi('resize', rs.w + e.screenX - rs.x, rs.h + e.screenY - rs.y); rs = null; } };
  document.addEventListener('pointerup', rsEnd, true);
  document.addEventListener('pointercancel', () => { rs = null; }, true);
})();
</script>
"""


def _esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ticker(base, anchor, on, cls="") -> str:
    a = f' data-anchor="{anchor}"' if anchor else ""
    return f'<span class="{cls}" data-base="{base or 0:.0f}"{a} data-on="{1 if on else 0}">{fmt.clock(base)}</span>'


BUTTONS = ('<div class="m-btns"><span class="l" onclick="ptToggleLock()" title="Lock in place">🔒</span>'
           '<span class="c" onclick="ptToggleCollapse()" title="Only the timer and bar">▾</span>'
           '<span class="x" onclick="ptApi(\'close\')" title="Close the mini tracker">✕</span></div>')


def _bar(labels: list[str], fills: list[float], cur: int | None) -> str:
    cells = ""
    for i, (lab, f) in enumerate(zip(labels, fills)):
        cls = "cur" if i == cur else ""
        full = " full" if f >= 0.5 else ""
        cells += (f'<div class="{full.strip()}"><i class="{cls}" style="width:{max(0.0, min(f, 1.0)) * 100:.0f}%"></i>'
                  f'<b>{lab}</b></div>')
    return f'<div class="m-bar">{cells}</div>'


def render(d: dict, live: bool) -> str:
    if not d.get("league"):
        return '<div class="m-top"><span class="m-lg">PoE Tracker</span></div><div class="m-dim">No league has started yet.</div>'
    if d.get("view") == "campaign":
        c = d.get("campaign")
        head = (f'<div class="m-top m-hide"><span class="m-lg">{_esc(c["character"]) if c else "Campaign"}</span>'
                f'<span class="ch">{_esc(d["league"])}</span></div>')
        if not c:
            return head + '<div class="m-dim">Waiting for your first character. The timer starts in The Twilight Strand.</div>'
        on = live and bool(c["anchor_utc"]) and not c["afk"]
        cur_act = None if c["completed"] else c["act"]
        pct = f'<span class="pct">{c["progress"] * 100:.0f}%</span>'
        where = (f"Campaign complete{pct}" if c["completed"] else
                 f'Act {c["act"]} · {_esc(c["zone"] or "")}{pct}')
        # progress bar: A1-A10, the act you're in fills as you enter its zones
        done = {x["act"] for x in c["splits"]}
        fills = [1.0 if (c["completed"] or a in done) else (c.get("act_progress") or 0) if a == cur_act else 0.0
                 for a in range(1, 11)]
        bar = _bar([f"A{a}" for a in range(1, 11)], fills, (cur_act - 1) if cur_act else None)
        # splits: every act, timer at the finish and how long the act took
        by_act = {x["act"]: x for x in c["splits"]}

        def cell(a):
            x = by_act.get(a)
            if x:
                return (f'<div class="m-split"><span class="a">A{a}</span><span class="t">{fmt.clock(x["split"])}</span>'
                        f'<span class="d">{fmt.dur(x["time_s"], True)}</span></div>')
            if a == cur_act:
                return (f'<div class="m-split cur"><span class="a">A{a}</span>'
                        f'<span class="t">{_ticker(c["play_s"], c["anchor_utc"], on)}</span>'
                        f'<span class="d">{_ticker(c["act_s"], c["anchor_utc"], on) if c["act_s"] is not None else ""}</span></div>')
            return f'<div class="m-split todo"><span class="a">A{a}</span><span class="t">–</span></div>'
        splits = ('<div class="m-splits">' + "".join(cell(a) + cell(a + 5) for a in range(1, 6)) + '</div>')
        labs = "".join(f'<span>{_esc(l["lab"])} <b>{fmt.clock(l["split"]) if l["done"] else "–"}</b></span>'
                       for l in c.get("labs") or [])
        nb, nt = c.get("next_boss"), c.get("next_trial")
        nxt = ""
        if nb:
            nxt += f'<div class="m-next"><span class="k">Boss</span>{_esc(nb["boss"])}' + \
                   (f' <span style="color:var(--ex-dim)">· {_esc(nb["zone"])}</span>' if nb.get("zone") else "") + '</div>'
        if nt:
            nxt += f'<div class="m-next"><span class="k">Trial</span>{_esc(nt["lab"])} · {_esc(nt["zone"])}</div>'
        return (head
                + f'<div class="m-clock">{_ticker(c["play_s"], c["anchor_utc"], on)}</div>'
                + f'<div class="m-where m-hide">{where}</div>'
                + f'<div class="m-row m-hide" data-p="4"><span>Lv <b>{c["level"]}</b></span><span>Deaths <b>{c["deaths"]}</b></span>'
                  f'<span>Quest pts <b>{c["quest_points"]}/{c["quest_total"]}</b></span></div>'
                + bar
                + f'<div class="m-hide" data-p="2"><div class="m-h">SPLITS</div>{splits}'
                + (f'<div class="m-labs"><span style="color:var(--ex-gold)">LABS</span>{labs}</div>' if labs else "")
                + '</div>'
                + (f'<div class="m-hide" data-p="3"><div class="m-h">NEXT</div>{nxt}</div>' if nxt else ""))
    m = d.get("mapping") or {}
    nxt = "".join(f'<div class="m-next"><span class="k" style="width:auto;margin-right:6px">'
                  f'{_esc(x["group"].replace(" Voidstone", ""))}</span>{_esc(x["name"])}</div>' for x in m.get("next", []))
    phase = "Mapping" if d.get("phase") == "mapping" else "Endgame"
    top = m.get("top_tier") or 0
    on = live and bool(m.get("anchor_utc")) and not m.get("afk")
    clock = _ticker(m.get("mapping_s") or 0, m.get("anchor_utc"), on) if m.get("mapping_s") is not None else "–"
    states = m.get("bar") or ["pending"] * 16
    cur = next((i for i, st in enumerate(states) if st == "current"), None)
    bar = _bar([str(i) for i in range(1, 17)], [0.0 if st == "pending" else 1.0 for st in states], cur)
    stones = "".join(f'<span title="{_esc(x["name"])} Voidstone" style="color:{"var(--ex-gold)" if x["done"] else "var(--ex-dim)"}">'
                     f'{"☑" if x["done"] else "☐"} {_esc(x["name"][:4])}</span>' for x in m.get("stones", []))
    tier = f'<span class="pct">{fmt.tier(min(top, 16)) if top else "–"}</span>'

    def rate(v):
        return "–" if v is None else fmt.num(v, 1)
    return (f'<div class="m-top m-hide"><span class="m-lg">{_esc(m.get("character") or "Mapping")}</span>'
            f'<span class="ch">{_esc(d["league"])}</span></div>'
            f'<div class="m-clock">{clock}</div>'
            + (f'<div class="m-where m-hide">League start finished {fmt.when(m["ended"])}{tier}</div>' if m.get("ended") else
               f'<div class="m-where m-hide">{phase} · {_esc(m.get("zone") or "")}{tier}</div>') +
            f'<div class="m-row m-hide"><span>Maps <b>{m.get("maps", 0)}</b></span><span>/h <b>{rate(m.get("maps_per_h"))}</b></span>'
            f'<span>Lv <b>{m.get("level") or "–"}</b></span><span>Deaths <b>{m.get("deaths", 0)}</b></span></div>'
            + bar +
            f'<div class="m-row m-hide" data-p="3" style="margin-top:7px">{stones}</div>'
            + (f'<div class="m-hide" data-p="4"><div class="m-h">NEXT UP</div>{nxt}</div>' if nxt and not m.get("ended") else ""))


CLIENTS: set = set()     # open mini windows, so the main window can lock/unlock them


def set_lock(locked: bool) -> int:
    """Lock or unlock every open mini tracker (from the main window). Returns how many."""
    n = 0
    for c in list(CLIENTS):
        try:
            with c:
                ui.run_javascript(f"ptApi('set_lock', {str(bool(locked)).lower()})")
            n += 1
        except Exception:
            CLIENTS.discard(c)
    return n


@ui.page("/mini")
def mini_page():
    ui.add_css(palette_css())
    ui.add_css(MINI_CSS)
    ui.add_body_html(TICK_JS)
    ui.query("body").style("background: transparent")
    box = ui.html("", sanitize=False).classes("mini")
    from .. import mini as mini_mod
    hk = mini_mod.hotkey_label(STATE.cfg.settings if STATE.cfg else None)
    foot = (f'<div class="m-foot"><span class="when-locked">🔒 locked · {hk} or 🔒 to unlock</span>'
            f'<span class="when-unlocked">Drag to move · corner to resize · 🔓 to lock</span></div>'
            '<div class="m-grip" title="Drag to resize"></div>')
    client = ui.context.client
    CLIENTS.add(client)
    client.on_disconnect(lambda: CLIENTS.discard(client))
    last = {"json": None}

    def refresh():
        if busy():
            data = {"busy": True}
            html = '<div class="m-top"><span class="m-lg">PoE Tracker</span></div><div class="m-dim">Reading your log…</div>'
        else:
            from .layout import dev_override
            dev = dev_override() or {}
            data = STATE.cached(("mini", dev.get("league"), dev.get("phase")),
                                lambda c: metrics.mini_status(c, STATE.cfg, dev.get("league"), dev.get("phase")),
                                league=dev.get("league"))
            st = STATE.tracker.status() if STATE.tracker else {}
            from datetime import datetime, timezone
            age = None
            if st.get("last_event_utc"):
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(st["last_event_utc"].replace("Z", "+00:00"))).total_seconds()
            live = age is not None and age < 600
            html = render(data, live)
        j = json.dumps([html])
        if j != last["json"]:
            last["json"] = j
            box.set_content(BUTTONS + f'<div class="m-body">{html}</div>' + foot)
            ui.run_javascript("window.ptMiniTick && ptMiniTick(); window.ptSetLocked && ptSetLocked(window.ptLocked !== false);"
                              " window.ptSetCollapsed && ptSetCollapsed(!!window.ptCollapsed); window.ptFit && ptFit()")
    refresh()
    ui.timer(3, refresh)
