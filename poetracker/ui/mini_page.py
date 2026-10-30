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
.mini { box-sizing: border-box; width: 100vw; height: 100vh; padding: 10px 12px 24px; overflow: hidden;
  font-family: "Segoe UI", system-ui, sans-serif; color: var(--ex-text);
  background: linear-gradient(180deg, var(--ex-panel) 0%, var(--ex-panel-2) 100%);
  border: 1px solid var(--ex-line); box-shadow: inset 0 0 0 1px #000, inset 0 0 0 2px var(--ex-a10); }
.mini.unlocked { border-color: var(--ex-gold); }
.m-top { display: flex; align-items: center; gap: 6px; font-family: 'Cinzel', serif; font-weight: 600; font-size: 11px;
  letter-spacing: .05em; color: var(--ex-muted); white-space: nowrap; overflow: hidden; }
.m-top .m-lg { color: var(--ex-gold-hi); overflow: hidden; text-overflow: ellipsis; flex: 0 1 auto; min-width: 0; }
.m-top .ch { flex: 0 10 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.m-top .sp { flex: 1 1 0; min-width: 0; }
.m-btn { cursor: pointer; color: var(--ex-muted); font-size: 13px; padding: 0 3px; display: none; }
.m-btn:hover { color: var(--ex-gold-hi); }
.mini.unlocked .m-btn { display: inline; }
.m-lock { color: var(--ex-dim); font-size: 11px; }
.m-clock { font-size: 34px; font-weight: 700; line-height: 1.1; margin-top: 4px; color: var(--ex-value);
  font-variant-numeric: tabular-nums; letter-spacing: .01em; }
.m-clock .pct { font-size: 15px; color: var(--ex-gold); margin-left: 8px; font-weight: 600; }
.m-where { font-size: 13px; color: var(--ex-gold-hi); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.m-row { display: flex; gap: 12px; font-size: 12px; color: var(--ex-muted); margin-top: 3px; font-variant-numeric: tabular-nums; }
.m-row b { color: var(--ex-text); font-weight: 600; }
.m-h { font-family: 'Cinzel', serif; font-weight: 600; font-size: 10.5px; letter-spacing: .08em; color: var(--ex-gold);
  margin: 9px 0 3px; border-bottom: 1px solid var(--ex-line-dim); padding-bottom: 2px; }
.m-split { display: flex; font-size: 12.5px; font-variant-numeric: tabular-nums; line-height: 1.55; }
.m-split .a { width: 52px; color: var(--ex-muted); } .m-split .t { flex: 1; } .m-split .d { color: var(--ex-dim); }
.m-next { font-size: 12.5px; line-height: 1.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.m-next .k { color: var(--ex-muted); display: inline-block; width: 44px; }
.m-bar { display: flex; gap: 2px; height: 5px; margin-top: 7px; }
.m-bar div { flex: 1; background: var(--ex-line-dim); border-radius: 1px; position: relative; overflow: hidden; }
.m-bar div i { position: absolute; inset: 0; background: var(--ex-gold); }
.m-bar div i.cur { background: var(--ex-cur); }
.m-bar div i.skip { background: var(--ex-line); }
.m-dim { color: var(--ex-dim); font-size: 12px; margin-top: 8px; }
.m-foot { position: fixed; left: 12px; right: 12px; bottom: 6px; font-size: 10.5px; color: var(--ex-dim);
  display: flex; justify-content: space-between; gap: 6px; white-space: nowrap; overflow: hidden; }
.m-foot .when-unlocked { display: none; color: var(--ex-gold); }
.mini.unlocked .m-foot .when-unlocked { display: inline; } .mini.unlocked .m-foot .when-locked { display: none; }
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
  };
  window.ptApi = function (name) { try { window.pywebview.api[name](); } catch (e) {} };
})();
</script>
"""


def _esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ticker(base, anchor, on, cls="") -> str:
    a = f' data-anchor="{anchor}"' if anchor else ""
    return f'<span class="{cls}" data-base="{base or 0:.0f}"{a} data-on="{1 if on else 0}">{fmt.clock(base)}</span>'


def render(d: dict, live: bool) -> str:
    top_buttons = ('<span class="m-btn" title="Lock: clicks pass through to the game" '
                   'onclick="ptApi(\'toggle_lock\')">🔒</span>'
                   '<span class="m-btn" title="Close the mini tracker" onclick="ptApi(\'close\')">✕</span>')
    if not d.get("league"):
        return f'<div class="m-top"><span class="m-lg">PoE Tracker</span><span class="sp"></span>{top_buttons}</div>' \
               f'<div class="m-dim">No league has started yet.</div>'
    if d.get("view") == "campaign":
        c = d.get("campaign")
        head = (f'<div class="m-top"><span class="m-lg">{_esc(d["league"])}</span>'
                f'<span class="ch">· {_esc(c["character"]) if c else "campaign"}</span><span class="sp"></span>{top_buttons}</div>')
        if not c:
            return head + '<div class="m-dim">Waiting for your first character. The timer starts in The Twilight Strand.</div>'
        on = live and bool(c["anchor_utc"]) and not c["afk"]
        clock = _ticker(c["play_s"], c["anchor_utc"], on)
        pct = f'<span class="pct">{c["progress"] * 100:.0f}%</span>'
        where = "Campaign complete" if c["completed"] else f'Act {c["act"]} · {_esc(c["zone"] or "")}'
        act_t = (_ticker(c["act_s"], c["anchor_utc"], on) if c["act_s"] is not None else "–")
        bar = "".join(
            f'<div><i style="width:{100 if c["completed"] or a < (c["act"] or 0) else 0}%"></i></div>' for a in range(1, 11))
        if not c["completed"] and c["act"]:
            done = {s["act"] for s in c["splits"]}
            bar = "".join(f'<div><i style="width:{100 if a in done or a < c["act"] else (c["progress"] * 10 - (a - 1)) * 100 if a == c["act"] else 0:.0f}%" '
                          f'class="{"cur" if a == c["act"] else ""}"></i></div>' for a in range(1, 11))
        splits = "".join(
            f'<div class="m-split"><span class="a">Act {s["act"]}</span><span class="t">{fmt.clock(s["split"])}</span>'
            f'<span class="d">{fmt.dur(s["time_s"], True)}</span></div>' for s in reversed(c["splits"][-3:]))
        nb, nt = c.get("next_boss"), c.get("next_trial")
        nxt = ""
        if nb:
            nxt += f'<div class="m-next"><span class="k">Boss</span>{_esc(nb["boss"])}' + \
                   (f' <span style="color:var(--ex-dim)">· {_esc(nb["zone"])}</span>' if nb.get("zone") else "") + '</div>'
        if nt:
            nxt += f'<div class="m-next"><span class="k">Trial</span>{_esc(nt["lab"])} · {_esc(nt["zone"])}</div>'
        return (head
                + f'<div class="m-clock">{clock}{pct}</div>'
                + f'<div class="m-where">{where}</div>'
                + f'<div class="m-row"><span>Act <b>{act_t}</b></span><span>Lv <b>{c["level"]}</b></span>'
                  f'<span>Deaths <b>{c["deaths"]}</b></span></div>'
                + f'<div class="m-bar">{bar}</div>'
                + (f'<div class="m-h">SPLITS</div>{splits}' if splits else "")
                + (f'<div class="m-h">NEXT</div>{nxt}' if nxt else "")
                + f'<div class="m-row" style="margin-top:6px"><span>Quest points <b>{c["quest_points"]}/{c["quest_total"]}</b></span>'
                  f'<span>Trials <b>{c["trials"]}/12</b></span></div>')
    m = d.get("mapping") or {}
    nxt = "".join(f'<div class="m-next"><span class="k" style="width:auto;margin-right:6px">'
                  f'{_esc(x["group"].replace(" Voidstone", ""))}</span>{_esc(x["name"])}</div>' for x in m.get("next", []))
    phase = "Mapping" if d.get("phase") == "mapping" else "Endgame"
    top = m.get("top_tier") or 0
    on = live and bool(m.get("anchor_utc")) and not m.get("afk")
    clock = _ticker(m.get("mapping_s") or 0, m.get("anchor_utc"), on) if m.get("mapping_s") is not None else "–"
    states = m.get("bar") or ["pending"] * 16
    bar = "".join(f'<div><i style="width:{0 if st == "pending" else 100}%" class="{"cur" if st == "current" else ("skip" if st == "skipped" else "")}"></i></div>'
                  for st in states)
    stones = "".join(f'<span title="{_esc(x["name"])} Voidstone" style="color:{"var(--ex-gold)" if x["done"] else "var(--ex-dim)"}">'
                     f'{"☑" if x["done"] else "☐"} {_esc(x["name"][:4])}</span>' for x in m.get("stones", []))

    def rate(v):
        return "–" if v is None else fmt.num(v, 1)
    return (f'<div class="m-top"><span class="m-lg">{_esc(d["league"])}</span><span class="ch">· {_esc(m.get("character") or "")}</span>'
            f'<span class="sp"></span>{top_buttons}</div>'
            f'<div class="m-clock">{clock}<span class="pct">{fmt.tier(min(top, 16)) if top else "–"}</span></div>'
            + (f'<div class="m-where">League start finished {fmt.when(m["ended"])}</div>' if m.get("ended") else
               f'<div class="m-where">{phase} · {_esc(m.get("zone") or "")}</div>') +
            f'<div class="m-row"><span>Maps <b>{m.get("maps", 0)}</b></span><span>/h <b>{rate(m.get("maps_per_h"))}</b></span>'
            f'<span>Lv <b>{m.get("level") or "–"}</b></span><span>Deaths <b>{m.get("deaths", 0)}</b></span></div>'
            f'<div class="m-bar">{bar}</div>'
            f'<div class="m-row" style="margin-top:7px">{stones}</div>'
            + (f'<div class="m-h">NEXT UP</div>{nxt}' if nxt and not m.get("ended") else ""))


@ui.page("/mini")
def mini_page():
    ui.add_css(palette_css())
    ui.add_css(MINI_CSS)
    ui.add_body_html(TICK_JS)
    ui.query("body").style("background: transparent")
    box = ui.html("", sanitize=False).classes("mini")
    from .. import mini as mini_mod
    hk = mini_mod.hotkey_label(STATE.cfg.settings if STATE.cfg else None)
    foot = (f'<div class="m-foot"><span class="when-locked">🔒 {hk} to unlock</span>'
            f'<span class="when-unlocked">Drag to move · {hk} to lock</span></div>')
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
            box.set_content(html + foot)
            ui.run_javascript("window.ptMiniTick && ptMiniTick(); window.ptSetLocked && ptSetLocked(window.ptLocked !== false)")
    refresh()
    ui.timer(3, refresh)
