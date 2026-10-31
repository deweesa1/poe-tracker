"""Reusable building blocks: KPI tiles, cards, tables and charts."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable

from nicegui import ui

# Colours (shared by CSS and charts)
GOLD = "#d9a441"
TEAL = "#4fb3a5"
BLUE = "#6c9bd2"
RED = "#d8604e"
GREEN = "#7cb36b"
VIOLET = "#a68bd6"
GREY = "#6f665b"
MUTED = "#a69b8c"
LINE = "#352e28"
PALETTE = [GOLD, TEAL, BLUE, VIOLET, GREEN, RED, "#c98bb9", "#8fa3b0"]

CSS = f"""
:root {{ --gold:{GOLD}; --muted:{MUTED}; --line:{LINE}; }}
body, .q-page {{ background:#14110f; color:#ece4d8; font-family:"Segoe UI",system-ui,sans-serif; }}
.q-drawer {{ background:#1a1613 !important; border-right:1px solid {LINE}; }}
.q-header {{ background:rgba(20,17,15,.92) !important; backdrop-filter: blur(6px); border-bottom:1px solid {LINE}; }}
.pt-card {{ background:#1d1916; border:1px solid {LINE}; border-radius:10px; padding:16px 18px; box-shadow:none; min-width:0; overflow-x:auto; }}
.pt-kpi {{ background:#1d1916; border:1px solid {LINE}; border-radius:10px; padding:12px 16px; min-width:0; flex:1; }}
.pt-kpi .v, .pt-kpi .k, .pt-kpi .d {{ overflow:hidden; text-overflow:ellipsis; }}
@media (max-width: 1100px) {{ .pt-kpi {{ padding:10px 12px; }} .pt-kpi .v {{ font-size:20px; }} }}
.pt-kpi .k {{ color:{MUTED}; font-size:12px; }}
.pt-kpi .v {{ font-size:24px; font-weight:650; font-variant-numeric: tabular-nums; line-height:1.3; }}
.pt-kpi .d {{ color:{GREY}; font-size:12px; }}
.pt-title {{ font-size:22px; font-weight:650; }}
.pt-sub {{ color:{MUTED}; }}
.pt-h2 {{ font-size:15px; font-weight:600; margin-bottom:8px; }}
.pt-note {{ color:{MUTED}; font-size:12px; }}
.pt-nav .q-item {{ border-radius:8px; margin:1px 8px; min-height:38px; color:{MUTED}; }}
.pt-nav .q-item.active {{ background:rgba(217,164,65,.16); color:{GOLD}; }}
.pt-nav .q-item:hover {{ color:#ece4d8; }}
.q-table__container {{ background:transparent; box-shadow:none; }}
.q-table thead th {{ color:{MUTED}; font-weight:550; font-size:12px; }}
.q-table tbody td {{ font-variant-numeric: tabular-nums; }}
.q-table--dark .q-table__bottom, .q-table--dark thead, .q-table--dark td, .q-table--dark th, .q-table--dark tr {{ border-color:{LINE}; }}
.clickable tbody tr {{ cursor:pointer; }}
html {{ scroll-behavior: smooth; }}
/* Tables fit their card instead of scrolling sideways: headers and text cells
   wrap, numbers stay on one line, padding tightens on narrow windows. */
.q-table th {{ white-space: normal !important; line-height: 1.25; vertical-align: bottom; }}
.q-table td {{ white-space: normal !important; }}
.q-table td.text-right, .q-table td.text-center {{ white-space: nowrap !important; }}
.q-table__middle {{ overflow-x: hidden; }}
.q-table td.pt-wrapcell.text-right {{ white-space: normal !important; overflow-wrap: anywhere; }}
/* columns marked opt=True drop out when their card is narrow (half a monitor) */
.pt-card {{ container-type: inline-size; }}
@container (max-width: 760px) {{ .q-table .pt-opt {{ display: none; }} }}
@container (max-width: 640px) {{
  .q-table--dense th, .q-table--dense td {{ padding-left: 4px !important; padding-right: 4px !important; font-size: 12px !important; }}
}}
@media (max-width: 1100px) {{
  .q-table--dense th, .q-table--dense td {{ padding-left: 6px !important; padding-right: 6px !important; }}
  .q-table td, .q-table th {{ font-size: 12.5px; }}
}}
.pt-ls-head {{ font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
  color: var(--ex-gold, #d9a441); margin-bottom: 2px; }}
.pt-ver > .nicegui-row {{ align-items: flex-start !important; }}
.pt-ver .q-icon {{ margin-top: 1px; }}
.pt-drawer-foot {{ border-top: 1px solid var(--ex-line-dim, #2d2722); }}
.pt-sep {{ align-self: stretch; height: 1px; margin: 6px 14px; background: var(--ex-line-dim, #2d2722); }}
.q-drawer, .q-drawer__content {{ overflow: visible !important; }}
.pt-toggle {{ position: absolute; right: -14px; top: -100px; width: 26px; height: 26px;
  border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; z-index: 5;
  background: var(--ex-gold, #c9a35a); color: #15120b; box-shadow: 0 0 0 3px var(--ex-bg, #14110f), 0 2px 8px rgba(0,0,0,.5); }}
.pt-toggle:hover {{ background: var(--ex-gold-hi, #e6c27a); }}
.pt-ver {{ align-self: stretch; margin: 6px 14px 0; padding: 14px 0 0 5px; height: 50px; box-sizing: border-box; border-top: 1px solid var(--ex-line-dim, #2d2722); }}
.pt-logo {{ padding-left: 16px; padding-right: 16px; }}
body:not(.pt-mini) .pt-nav-tip {{ display: none !important; }}
.q-drawer--mini .q-mini-drawer-hide {{ display: none !important; }}
/* collapsed menu: 40px squares centred in the strip; the active one is tinted
   and marked by a bar on the menu's left edge */
.q-drawer--mini .pt-logo {{ padding: 24px 0 16px !important; justify-content: center; width: 100%; }}
.q-drawer--mini .pt-logo img {{ width: 26px !important; height: 26px !important; }}
.pt-nav {{ display: flex; flex-direction: column; }}   /* same row spacing open or collapsed (no margin collapsing) */
.q-drawer--mini .pt-nav {{ align-items: center; }}
.q-drawer--mini .pt-nav .q-item {{ width: 40px !important; min-height: 40px !important; height: 40px; margin: 3px 0 !important;
  padding: 0 !important; justify-content: center; border-left: 0 !important; border-radius: 8px !important;
  position: relative; overflow: visible !important; }}
.q-drawer--mini .pt-nav .q-item.active {{ background: rgba(201,163,90,.18) !important; }}
.q-drawer--mini .pt-nav .q-item.active::before {{ content: ""; position: absolute; left: -8px; top: 9px; bottom: 9px;
  width: 3px; border-radius: 0 2px 2px 0; background: var(--ex-gold, #c9a35a); }}
.q-drawer--mini .pt-nav .q-item__section--avatar {{ min-width: 0 !important; padding: 0 !important; justify-content: center; }}
.q-drawer--mini .pt-nav .q-icon {{ font-size: 19px !important; }}
.q-drawer--mini .pt-sep {{ width: 24px; margin: 6px auto; align-self: center; }}
.q-drawer--mini .pt-ver {{ margin: 6px auto 0; padding: 14px 0 0; height: 50px; box-sizing: border-box; width: 24px; display: flex; justify-content: center; }}
.q-drawer--mini .pt-ver > .nicegui-row {{ width: auto !important; justify-content: center; }}


.pt-stat {{ display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px;
  border-radius: 50%; border: 1px solid var(--ex-line-dim, #2d2722); background: rgba(0,0,0,.18); cursor: default; }}
.pt-actbar a:hover > div {{ filter: brightness(1.15); box-shadow: 0 0 0 1px #ece4d8 inset; }}
.pt-wrap {{ flex-wrap: wrap; }}
.pt-wrap > * {{ flex: 1 1 420px; min-width: 0; }}
.pt-wrap > .pt-narrow {{ flex: 2 1 300px; }}
.pt-wrap > .pt-wide {{ flex: 3 1 380px; }}
.pt-wrap > .pt-pie {{ flex: 0 1 300px; min-width: 240px; margin: 0 auto; }}
.pt-swatch {{ display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 10px; vertical-align: -1px; }}
.pt-up {{ color:{GREEN}; }} .pt-down {{ color:{RED}; }}
.pt-badge {{ display:inline-block; padding:0 8px; border-radius:99px; border:1px solid {LINE}; color:{MUTED}; font-size:12px; margin:1px 3px 1px 0; }}
.pt-compare {{ background:#1d1916; border:1px solid {LINE}; border-radius:10px; padding:12px 14px; }}
.pt-compare .k {{ color:{MUTED}; font-size:12px; }}
.pt-compare .v {{ font-size:20px; font-weight:650; }}
"""


# "Exile" theme: the look of Path of Exile's panels (dark leather-brown,
# aged gold, carved serif capitals). Layered over CSS above; the classic look
# is the CSS alone. Font: Cinzel (SIL Open Font License), bundled in static/fonts.
EXILE_CSS = """
@font-face { font-family: 'Cinzel'; font-weight: 400; src: url('/static/fonts/cinzel-latin-400-normal.woff2') format('woff2'); }
@font-face { font-family: 'Cinzel'; font-weight: 600; src: url('/static/fonts/cinzel-latin-600-normal.woff2') format('woff2'); }
@font-face { font-family: 'Cinzel'; font-weight: 700; src: url('/static/fonts/cinzel-latin-700-normal.woff2') format('woff2'); }
:root { --ex-gold: #c9a35a; --ex-gold-hi: #f0d595; --ex-text: #ddd0b4; --ex-muted: #a38d6d; --ex-dim: #7d6b54;
        --ex-line: #5c4a2c; --ex-line-dim: #3a2f1f; --ex-panel: #221b12; --ex-panel-2: #1b150e; }
body, .q-page, .q-layout { color: var(--ex-text);
  background: radial-gradient(ellipse 120% 70% at 50% -10%, var(--ex-glow) 0%, var(--ex-bg) 55%, var(--ex-bg-2) 100%) fixed !important; }
.q-header { background: linear-gradient(180deg, var(--ex-head) 0%, var(--ex-bg) 100%) !important; backdrop-filter: none;
  border-bottom: 1px solid var(--ex-line); box-shadow: 0 1px 0 var(--ex-a18), 0 6px 18px rgba(0,0,0,.55); }
.pt-title { font-family: 'Cinzel', serif; font-weight: 700; color: var(--ex-gold-hi); letter-spacing: .04em;
  text-shadow: 0 0 14px var(--ex-a28); }
.pt-sub { color: var(--ex-muted); } .pt-note { color: var(--ex-dim); }
.q-drawer { background: linear-gradient(180deg, var(--ex-drawer) 0%, var(--ex-bg-2) 100%) !important; border-right: 1px solid var(--ex-line) !important; }
.q-drawer .text-weight-bold { font-family: 'Cinzel', serif; letter-spacing: .05em; color: var(--ex-gold-hi); }
.pt-nav .q-item { font-family: 'Cinzel', serif; font-weight: 600; font-size: 12.5px; letter-spacing: .02em; color: var(--ex-muted);
  border-radius: 2px; border-left: 2px solid transparent; }
.pt-nav .q-item:hover { color: var(--ex-gold-hi); background: var(--ex-a06); }
.pt-nav .q-item.active { color: var(--ex-gold-hi); border-left-color: var(--ex-gold);
  background: linear-gradient(90deg, var(--ex-a20), transparent 85%); }
/* menu rows: the icon sits in a 40px square (the same squares as the collapsed menu); the
   page you're on gets the fading gold highlight and a bar on the menu's left edge */
.pt-nav .q-item { border-left: 0 !important; border-radius: 8px !important; min-height: 40px !important; height: 40px;
  margin: 3px 8px !important; padding: 0 10px 0 0 !important; position: relative; overflow: visible !important; }
.pt-nav .q-item__section--avatar { min-width: 40px !important; width: 40px; padding: 0 !important;
  justify-content: center; align-items: center; }
.pt-nav .q-item .q-icon { font-size: 19px !important; }
.pt-nav .q-item.active::before { content: ""; position: absolute; left: -8px; top: 9px; bottom: 9px; width: 3px;
  border-radius: 0 2px 2px 0; background: var(--ex-gold); }
.pt-logo { padding-left: 15px !important; }
.pt-logo img { width: 26px !important; height: 26px !important; }
.pt-card, .pt-kpi { background: linear-gradient(180deg, var(--ex-panel) 0%, var(--ex-panel-2) 100%);
  border: 1px solid var(--ex-line); border-radius: 3px;
  box-shadow: inset 0 0 0 1px #000, inset 0 0 0 2px var(--ex-a10), 0 3px 14px rgba(0,0,0,.55); }
.pt-h2 { font-family: 'Cinzel', serif; font-weight: 600; letter-spacing: .05em; color: var(--ex-gold-hi); }
.pt-card > .pt-h2 { font-family: 'Cinzel', serif; font-weight: 600; font-size: 15px; letter-spacing: .06em; color: var(--ex-gold-hi);
  text-align: center; margin: -16px -18px 12px; padding: 9px 18px 8px;
  background: linear-gradient(90deg, transparent 0%, var(--ex-band) 50%, transparent 100%);
  border-bottom: 1px solid var(--ex-line); }
.pt-card > .pt-h2::before, .pt-card > .pt-h2::after { content: "◆"; font-size: 8px; color: var(--ex-gold); margin: 0 10px;
  vertical-align: 3px; opacity: .8; }
.pt-kpi .k { font-family: 'Cinzel', serif; font-weight: 600; font-size: 11.5px; letter-spacing: .05em; color: var(--ex-muted); }
.pt-kpi .v { color: var(--ex-value); }
.pt-kpi .d { color: var(--ex-dim); }
.q-table thead th { font-family: 'Cinzel', serif; font-weight: 600; font-size: 11px; letter-spacing: 0; color: var(--ex-muted);
  overflow-wrap: anywhere; hyphens: auto; }
@container (max-width: 760px) { .q-table thead th { font-size: 10px !important; } }
.q-table--dark .q-table__bottom, .q-table--dark thead, .q-table--dark td, .q-table--dark th, .q-table--dark tr { border-color: var(--ex-line-dim); }
.q-table tbody tr:hover > td { background: var(--ex-a06); }
.q-tabs { border-bottom: 1px solid var(--ex-line); }
.q-tab { font-family: 'Cinzel', serif; font-weight: 600; letter-spacing: .05em; color: var(--ex-muted);
  background: linear-gradient(180deg, var(--ex-tab), var(--ex-panel-2)); border: 1px solid var(--ex-line); border-bottom: none;
  border-radius: 4px 4px 0 0; margin-right: 4px; min-height: 34px; }
.q-tab--active { color: var(--ex-gold-hi) !important; background: linear-gradient(180deg, var(--ex-tab-on), var(--ex-tab)); }
.q-tab__indicator { display: none; }
.q-btn { font-family: 'Cinzel', serif; letter-spacing: .05em; }
.q-field__label, .q-field__native, .q-select__dropdown-icon { color: var(--ex-text) !important; }
.q-field--outlined .q-field__control:before { border-color: var(--ex-line) !important; }
.pt-ls-name { font-family: 'Cinzel', serif; letter-spacing: .03em; color: var(--lg-hi, var(--ex-gold-hi));
  text-shadow: 0 0 18px var(--lg-a28, transparent); }
.q-header { border-bottom: 2px solid var(--lg, var(--ex-line)) !important; }

.q-tab--active { box-shadow: inset 0 2px 0 var(--lg, var(--ex-gold)); }
.pt-zone-head { font-family: 'Cinzel', serif; letter-spacing: .04em; }
/* page tabs in the top bar, under the title: words with a gold underline, no boxes */
.pt-head-tabs { margin-top: 0; }
.pt-head-tabs:empty { display: none; }
.pt-header { min-height: 74px; }
.pt-head-tabs .q-tab { min-height: 36px !important; }
.pt-head { min-width: 0; }
.pt-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 1150px) {
  .pt-title { font-size: 17px !important; }
  .pt-head { gap: 16px !important; }
  .pt-head-tabs .q-tab { margin-right: 10px; font-size: 11.5px; }
  .pt-header .q-select { min-width: 150px !important; }
}
.pt-head-tabs .q-tabs { border-bottom: 0; min-height: 0; }
.pt-head-tabs .q-tab { background: transparent !important; border: 0 !important; box-shadow: none !important;
  border-radius: 0; min-height: 28px; padding: 0 2px; margin-right: 18px; font-size: 12.5px; color: var(--ex-muted); }
.pt-head-tabs .q-tab:hover { color: var(--ex-gold-hi); }
.pt-head-tabs .q-tab--active { color: var(--ex-gold-hi) !important; }
.pt-head-tabs .q-tab__indicator { display: block !important; height: 2px; background: var(--ex-gold); opacity: 0; }
.pt-head-tabs .q-tab--active .q-tab__indicator { opacity: 1; }
.pt-head-tabs .q-tab .q-focus-helper { display: none; }
::-webkit-scrollbar { width: 10px; height: 10px; } ::-webkit-scrollbar-track { background: var(--ex-bg-2); }
::-webkit-scrollbar-thumb { background: var(--ex-line); border: 2px solid var(--ex-bg-2); border-radius: 6px; }
/* league start mapping: one box per voidstone */
.pt-stonegrid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 440px), 1fr)); }
.pt-stonebox { padding: 16px 18px; min-width: 0; scroll-margin-top: 90px; }
.pt-stonebox .hd { display: flex; gap: 10px; align-items: center; }
.pt-stonebox .bx { font-size: 22px; line-height: 1; color: var(--ex-muted); }
.pt-stonebox .tt { font-family: 'Cinzel', serif; font-weight: 700; font-size: 16px; color: var(--ex-text); }
.pt-stonebox.got .bx, .pt-stonebox.got .tt { color: var(--ex-gold-hi); }
.pt-stonebox .st { font-size: 15px; font-weight: 600; color: var(--ex-gold); margin: 6px 0 2px; }
.pt-stonebox .bar { height: 5px; background: #2d2722; border-radius: 3px; overflow: hidden; margin: 10px 0 8px; }
.pt-stonebox .bar i { display: block; height: 100%; background: var(--ex-gold); }
.pt-step { display: grid; grid-template-columns: 24px minmax(0, 1fr) auto; gap: 8px; align-items: baseline;
  padding: 6px 0; border-top: 1px solid var(--ex-line-dim, #2d2722); font-size: 13.5px; color: var(--ex-muted); }
.pt-step .mk { text-align: center; font-weight: 700; }
.pt-step .nm { min-width: 0; overflow-wrap: anywhere; }
.pt-step .nm small { display: block; font-size: 11.5px; color: var(--ex-dim, #6f665a); }
.pt-step .ad { font-size: 11.5px; color: var(--ex-dim, #6f665a); white-space: nowrap; }
.pt-step.done { color: var(--ex-text); } .pt-step.done .mk { color: var(--ex-gold); }
/* map checklist: one chip per map, gold when done */
.pt-chipbox { padding: 14px 16px; }
.pt-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.pt-mapchip { font: inherit; font-size: 12.5px; line-height: 1; padding: 6px 9px; border-radius: 3px; cursor: pointer;
  background: rgba(0,0,0,.2); color: var(--ex-dim, #6f665a); border: 1px dashed #4a4038; transition: background .12s, color .12s; }
.pt-mapchip:hover { border-color: var(--ex-gold); color: var(--ex-text); }
.pt-mapchip.on { background: rgba(201,163,90,.24); color: var(--ex-gold-hi); border: 1px solid rgba(201,163,90,.55); }
.pt-mapchip.on:hover { background: rgba(201,163,90,.34); }
/* side menu: pages closed during league start */
.pt-nav .q-item.pt-locked { opacity: .42; }
.pt-nav .q-item .q-item__section--main { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.pt-nav .q-item .q-item__section--side { padding-left: 6px; }
.pt-nav .q-item.pt-locked:hover { opacity: .7; background: transparent; color: var(--ex-muted); }
/* overview: league start strip */
.pt-ls-strip { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px 32px;
  padding: 18px 24px 16px; }
.pt-ls-strip .ph { font-family: 'Cinzel', serif; font-weight: 700; font-size: 13px; letter-spacing: .08em;
  color: var(--ex-gold); text-transform: uppercase; }
.pt-ls-strip .clk { font-size: 30px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.1; color: var(--ex-text); }
.pt-ls-strip .k { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--ex-muted); }
.pt-ls-strip .v { font-size: 16px; font-weight: 600; color: var(--ex-text); }
.pt-ls-strip .nx { flex: 0 1 300px; min-width: 0; }
.pt-ls-strip .nx .v { color: var(--ex-gold-hi); }
.pt-ls-strip .bar { flex-basis: 100%; height: 5px; margin-top: 2px; background: #2d2722; border-radius: 3px; overflow: hidden; }
.pt-ls-strip .bar i { display: block; height: 100%; background: var(--ex-gold); }
/* settings: folding sections */
.pt-set > .q-expansion-item__container > .q-item { min-height: 54px; padding: 6px 18px; }
.pt-set > .q-expansion-item__container > .q-item .q-item__label { font-family: 'Cinzel', serif; font-size: 15px;
  letter-spacing: .06em; color: var(--ex-gold-hi); }
.pt-set > .q-expansion-item__container > .q-item .q-icon { color: var(--ex-gold); }
.pt-set-body { padding: 4px 18px 18px; }
/* profile snapshots */
.pt-gear { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); margin-top: 10px; }
.pt-item { background: rgba(0,0,0,.25); border: 1px solid var(--ex-line); border-radius: 3px; padding: 8px 10px; min-width: 0; cursor: help; }
.pt-item .sl { font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--ex-muted); }
.pt-item .nm { font-size: 13.5px; font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }
.pt-item .gm { font-size: 11.5px; color: #4fb3a5; margin-top: 3px; line-height: 1.3; }
.pt-snapdiff { margin-top: 10px; padding: 10px 12px; border-left: 3px solid var(--ex-gold); background: rgba(201,163,90,.07);
  font-size: 13px; line-height: 1.5; color: var(--ex-text); }
.pt-snapdiff .k { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--ex-gold); margin-bottom: 2px; }
.pt-snapdiff b { color: var(--ex-gold-hi); font-weight: 600; }
.pt-snaplist { font-size: 13px; line-height: 1.45; color: var(--ex-text); }
.pt-snaplist .k { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--ex-muted); margin-right: 6px; }
/* Characters: one scrolling row of characters */
.pt-charpick { position: relative; }
.pt-cp-row { display: flex; gap: 8px; overflow-x: auto; scroll-behavior: smooth; scroll-snap-type: x proximity;
  padding: 2px 34px 6px; scroll-padding: 0 34px; scrollbar-width: thin; }
.pt-cp { flex: 0 0 auto; scroll-snap-align: start; min-width: 168px; padding: 9px 14px; cursor: pointer; border-radius: 3px;
  border: 1px solid var(--ex-line); background: linear-gradient(180deg, var(--ex-panel), var(--ex-panel-2));
  transition: border-color .12s, background .12s; }
.pt-cp:hover { border-color: #6b5a3e; }
.pt-cp.on { border-color: var(--ex-gold); background: linear-gradient(180deg, rgba(201,163,90,.16), rgba(201,163,90,.05)); }
.pt-cp .n { font-weight: 700; font-size: 14px; color: var(--ex-text); white-space: nowrap; }
.pt-cp.on .n { color: var(--ex-gold-hi); }
.pt-cp .c, .pt-cp .m { font-size: 12px; color: var(--ex-muted); white-space: nowrap; line-height: 1.35; }
.pt-cp-arrow { position: absolute; top: 2px; bottom: 6px; z-index: 2; width: 28px; cursor: pointer; font-size: 22px;
  color: var(--ex-gold-hi); background: var(--ex-bg-2, #14110f); border: 1px solid var(--ex-line); border-radius: 3px; }
.pt-cp-arrow.l { left: 0; } .pt-cp-arrow.r { right: 0; }
.pt-charpick:not(.over) .pt-cp-arrow { display: none; }
.pt-charpick:not(.over) .pt-cp-row { padding-left: 0; padding-right: 0; }
.pt-cp-arrow:hover { border-color: var(--ex-gold); }
/* Characters: the selected character's header */
.pt-charhead { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px 32px; padding: 18px 24px; }
.pt-charhead .nm { font-family: 'Cinzel', serif; font-weight: 700; font-size: 26px; letter-spacing: .03em; color: var(--ex-gold-hi); line-height: 1.15; }
.pt-charhead .cl { font-size: 15px; color: var(--ex-text); margin-top: 2px; }
.pt-charhead .dt { font-size: 12.5px; color: var(--ex-muted); margin-top: 2px; }
.pt-charhead .tiles { display: grid; grid-template-columns: repeat(4, minmax(110px, auto)); gap: 0 28px; }
.pt-charhead .tiles div { display: flex; flex-direction: column; padding-left: 14px; border-left: 1px solid var(--ex-line); }
.pt-charhead .tiles small { font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--ex-muted); }
.pt-charhead .tiles b { font-size: 26px; font-weight: 700; color: var(--ex-text); line-height: 1.15; font-variant-numeric: tabular-nums; }
.pt-charhead .tiles i { font-style: normal; font-size: 12px; color: var(--ex-muted); white-space: nowrap; }
@media (max-width: 900px) { .pt-charhead .tiles { grid-template-columns: repeat(2, minmax(110px, auto)); gap: 10px 20px; } }
/* snapshot: the inventory as the game draws it, jewels, skills */
.pt-snaphead { font-family: 'Cinzel', serif; font-weight: 700; font-size: 14px; letter-spacing: .05em; color: var(--ex-gold-hi); }
.pt-paperdoll { position: relative; flex: none; padding: 34px 18px 18px; border-radius: 4px;
  background: radial-gradient(ellipse at 50% 30%, #2a2a2e 0%, #141416 70%); border: 1px solid #4a4134;
  box-shadow: inset 0 0 0 1px #000, inset 0 0 30px rgba(0,0,0,.6); }
.pt-paperdoll .grid { display: grid; grid-template-columns: repeat(8, 58px); grid-template-rows: repeat(8, 58px); gap: 6px; }
.pt-inv { position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden; cursor: help;
  background: linear-gradient(180deg, #0e1230 0%, #080a1c 100%); border: 1px solid #6b5a3e;
  box-shadow: inset 0 0 0 1px #000, inset 0 0 12px rgba(0,0,0,.8); }
.pt-inv:hover { border-color: #e2c27a; }
.pt-inv.empty { background: rgba(10,10,14,.6); border-color: #3a3328; cursor: default; }
.pt-inv img { max-width: 92%; max-height: 92%; object-fit: contain; }
.pt-inv > span { font-size: 10px; text-align: center; padding: 2px; color: var(--ex-muted); }
/* sockets in the game's spirit: a bronze ring with a rim in the socket's colour and a hollow middle,
   on the cell grid (50px apart), joined by plain gold links */
.pt-inv .sk { position: absolute; inset: 0; pointer-events: none; --p: 64px; --s: 38px;
  --bw: calc((var(--cols) - 1) * var(--p) + var(--s)); --bh: calc((var(--rows) - 1) * var(--p) + var(--s)); }
.pt-inv .sk b, .pt-inv .sk i { position: absolute; }
.pt-inv .sk b { width: var(--s); height: var(--s); border-radius: 50%; z-index: 2; box-sizing: border-box;
  left: calc(50% - var(--bw) / 2 + var(--c) * var(--p)); top: calc(50% - var(--bh) / 2 + var(--r) * var(--p));
  border: 2px solid color-mix(in srgb, var(--sc) 85%, #000);
  background:
    radial-gradient(circle at 36% 30%, rgba(255,235,190,.22) 0 4%, transparent 10%),
    radial-gradient(circle, #0a0807 0 40%, #17110b 47%, #2e2216 51%, #8c7046 56%, #6a5232 63%, #3e2f1c 72%, #7a6040 80%, #3a2c1a 90%, #1a130b 100%);
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.7), 0 0 0 1px rgba(0,0,0,.85), 0 2px 4px rgba(0,0,0,.8),
    inset 0 0 5px color-mix(in srgb, var(--sc) 30%, transparent); opacity: .92; }
.pt-inv .sk b.on { opacity: 1; }
.pt-inv .sk i { z-index: 1; border-radius: 2px;
  background: linear-gradient(180deg, #3e2f1c, #9a7c4c 50%, #5a4426); box-shadow: 0 0 0 1px rgba(0,0,0,.7); }
.pt-inv .sk i.h { height: 5px; width: var(--p);
  left: calc(50% - var(--bw) / 2 + var(--c) * var(--p) + var(--s) / 2);
  top: calc(50% - var(--bh) / 2 + var(--r) * var(--p) + var(--s) / 2 - 2.5px); }
.pt-inv .sk i.v { width: 5px; height: var(--p); background: linear-gradient(90deg, #3e2f1c, #9a7c4c 50%, #5a4426);
  left: calc(50% - var(--bw) / 2 + var(--c) * var(--p) + var(--s) / 2 - 2.5px);
  top: calc(50% - var(--bh) / 2 + var(--r) * var(--p) + var(--s) / 2); }
.pt-paperdoll .set2 { display: none; }
.pt-paperdoll.alt .set1 { display: none; } .pt-paperdoll.alt .set2 { display: flex; }
.pt-swap { position: absolute; top: 8px; left: 18px; display: flex; gap: 3px; }
.pt-swap button { font: 700 11px 'Cinzel', serif; width: 22px; height: 18px; padding: 0; cursor: pointer; color: #a69b8c;
  background: #1a1612; border: 1px solid #4a4134; border-radius: 2px; }
.pt-swap button.on { color: #14110f; background: #c9a35a; border-color: #e2c27a; }
.pt-jewelgrp { margin-bottom: 8px; }
.pt-jewelgrp .k { font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; color: var(--ex-muted); margin-bottom: 4px; }
.pt-jewels { display: grid; grid-template-columns: repeat(auto-fill, 52px); gap: 6px; width: 542px; max-width: 100%; }
.pt-jewel { width: 52px; height: 52px; display: flex; align-items: center; justify-content: center; cursor: help; border-radius: 2px;
  border: 1px solid var(--rc, #4a4134); background: radial-gradient(circle at 50% 40%, #2a2a33 0%, #121218 75%);
  box-shadow: inset 0 0 8px rgba(0,0,0,.7); }
.pt-jewel:hover { box-shadow: inset 0 0 8px rgba(0,0,0,.7), 0 0 0 1px var(--rc, #c9a35a); }
.pt-jewel img { width: 44px; height: 44px; object-fit: contain; }
/* skills: one card per link group, gems as a chain of linked sockets */
.pt-skills { display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 10px; width: 100%; }
.pt-skill { margin: 0; padding: 10px 14px 12px; border: 1px solid var(--ex-line); border-radius: 3px;
  background: linear-gradient(180deg, rgba(20,18,24,.9), rgba(10,9,12,.9)); }
.pt-skill .hd { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; min-width: 0; }
.pt-skill .hd img { width: 26px; height: 26px; object-fit: contain; }
.pt-skill .sl { font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--ex-muted); }
.pt-skill .ln { font-size: 10.5px; font-weight: 700; color: #14110f; background: #c9a35a; border-radius: 2px; padding: 0 5px; }
.pt-skill .wh { font-size: 13px; color: #6fd3c6; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pt-skill .chain { display: flex; align-items: flex-start; flex-wrap: nowrap; column-gap: 2px; }
.pt-skill .chain > i.lk { width: 9px; height: 4px; margin-top: 21px; flex: none; border-radius: 2px;
  background: linear-gradient(180deg, #3e2f1c, #9a7c4c 50%, #5a4426); box-shadow: 0 0 0 1px rgba(0,0,0,.7); }
.pt-skill .gs { display: flex; flex-direction: column; align-items: center; flex: 1 1 0; min-width: 62px; max-width: 92px; cursor: help; }
.pt-skill .gs b { width: 46px; height: 46px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  box-sizing: border-box; border: 2px solid color-mix(in srgb, var(--sc) 85%, #000);
  background:
    radial-gradient(circle at 36% 30%, rgba(255,235,190,.2) 0 4%, transparent 9%),
    radial-gradient(circle, #0a0807 0 47%, #17110b 53%, #2e2216 57%, #8c7046 62%, #6a5232 69%, #3e2f1c 77%, #7a6040 85%, #3a2c1a 92%, #1a130b 100%);
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.7), 0 0 0 1px rgba(0,0,0,.85), inset 0 0 6px color-mix(in srgb, var(--sc) 25%, transparent); }
.pt-skill .gs b img { width: 26px; height: 26px; object-fit: contain; }
.pt-skill .gs.sup b { box-shadow: none; }
.pt-skill .gs.empty b { opacity: .5; box-shadow: none; }
.pt-skill .gs em { font-style: normal; font-size: 10px; font-weight: 700; color: #e8e2d4; background: rgba(0,0,0,.8);
  border: 1px solid #3a3328; border-radius: 6px; padding: 0 4px; margin-top: -7px; z-index: 1; }
.pt-skill .gs small { font-size: 11px; line-height: 1.15; text-align: center; margin-top: 3px; color: #6fd3c6; font-weight: 600; }
.pt-skill .gs.sup small { color: #8fa8c8; font-weight: 400; }
.pt-skill .gs.empty small { color: var(--ex-dim, #6f665a); }
.pt-skill .gs small { overflow-wrap: normal; word-break: normal; font-size: 10.5px; }
.pt-skill .chain > i.lk.ext { background: repeating-linear-gradient(90deg, #9a7c4c 0 3px, transparent 3px 6px); box-shadow: none; }
.pt-skill .gs.granted b { border-style: dashed; border-color: #8a7046; }
.pt-skill .gs.granted .gi { color: #c9a35a; font-size: 18px; line-height: 1; }
.pt-skill .gs.granted small { color: #c9a35a; }
.pt-tree-credit { position: absolute; left: 10px; bottom: 8px; z-index: 2; font-size: 11px; color: rgba(200,190,170,.55); pointer-events: none; }
.pt-atlas.pt-tree { height: max(560px, calc(100vh - 240px)); }
/* atlas passive tree */
.pt-atlas { contain: strict; position: relative; height: max(520px, calc(100vh - 300px)); background: #07080b; border: 1px solid var(--ex-line);
  border-radius: 3px; overflow: hidden; touch-action: none; user-select: none; }
.pt-atlas canvas.pt-cv { position: absolute; inset: 0; display: block; cursor: grab; touch-action: none; }
.pt-atlas canvas.pt-cv.grab { cursor: grabbing; }
.pt-tree-msg { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--ex-muted); }
.pt-atlas-ctl { z-index: 2; position: absolute; right: 10px; top: 10px; display: flex; flex-direction: column; gap: 4px;
  background: rgba(10,9,8,.75); border: 1px solid var(--ex-line); border-radius: 18px; padding: 4px; }
.pt-atlas-ctl .q-btn { color: var(--ex-gold-hi); }
#pt-atlas-tip { position: fixed; z-index: 9999; display: none; max-width: 340px; pointer-events: none; padding: 10px 12px;
  background: rgba(12,10,8,.96); border: 1px solid var(--ex-gold, #c9a35a); border-radius: 3px; font-size: 13px;
  line-height: 1.4; color: #b9b2c9; box-shadow: 0 6px 24px rgba(0,0,0,.6); }
/* item card: centred like the game's, header tinted by rarity */
#pt-atlas-tip.card { padding: 0; max-width: 430px; min-width: 260px; border-color: #5a4a30; background: #0b0907; }
#pt-atlas-tip .ic-head { text-align: center; padding: 6px 14px; font-family: 'Cinzel', serif; font-size: 15px; line-height: 1.3;
  border-bottom: 1px solid #3a3020; }
#pt-atlas-tip .ic-head.normal { color: #d8d3c6; background: linear-gradient(180deg, #2a2724, #1a1816); }
#pt-atlas-tip .ic-head.magic { color: #9a9aff; background: linear-gradient(180deg, #1c1e38, #121326); }
#pt-atlas-tip .ic-head.rare { color: #ece27a; background: linear-gradient(180deg, #2e2914, #1c190c); }
#pt-atlas-tip .ic-head.unique { color: #d0874a; background: linear-gradient(180deg, #33200f, #1f1409); }
#pt-atlas-tip .ic-head.gem { color: #3cb8ac; background: linear-gradient(180deg, #102a28, #0a1a19); }
#pt-atlas-tip .ic-head.relic { color: #82ad6a; background: linear-gradient(180deg, #1c2a14, #12190c); }
#pt-atlas-tip .ic-head { position: relative; padding-left: 40px; padding-right: 40px; }
#pt-atlas-tip .ic-sym { position: absolute; top: 50%; width: 30px; height: 30px; transform: translateY(-50%); }
#pt-atlas-tip .ic-sym.l { left: 6px; } #pt-atlas-tip .ic-sym.r { right: 6px; }
#pt-atlas-tip .ic-tags { font-family: Inter, sans-serif; font-size: 11px; letter-spacing: .04em; color: #c9a35a; opacity: .9; }
#pt-atlas-tip .ic-body { padding: 8px 14px 10px; text-align: center; font-size: 13px; line-height: 1.45; }
#pt-atlas-tip .ic-body hr { border: 0; height: 1px; margin: 6px 20px;
  background: linear-gradient(90deg, transparent, #6b5a3e, transparent); }
#pt-atlas-tip .ic-head div, #pt-atlas-tip .ic-flav div { color: inherit; }
#pt-atlas-tip .ic-prop, #pt-atlas-tip .ic-req { color: #8f8a80; }
#pt-atlas-tip .ic-req b { color: #e8e2d4; font-weight: 600; display: inline; font-family: inherit; font-size: inherit; margin: 0; }
#pt-atlas-tip .ic-mod.impl, #pt-atlas-tip .ic-mod.expl { color: #8f8fe8; }
#pt-atlas-tip .ic-mod.ench { color: #b8c8f0; }
#pt-atlas-tip .ic-mod.craft { color: #b4b4ff; font-style: italic; }
#pt-atlas-tip .ic-mod.frac { color: #b09a6a; }
#pt-atlas-tip .ic-mod.foul { color: #c07ad8; }
#pt-atlas-tip .ic-flav { color: #a8683a; font-style: italic; }
#pt-atlas-tip .ic-corrupt { color: #c8423a; }
#pt-atlas-tip .ic-gems { color: #3cb8ac; }
/* quality badge on an inventory item, and the defence totals under the inventory */
.pt-inv u.q { position: absolute; right: 2px; bottom: 1px; z-index: 3; text-decoration: none; font-size: 10px; font-weight: 700;
  color: #b9b3e8; background: rgba(0,0,0,.65); border-radius: 3px; padding: 0 3px; }
.pt-def { display: grid; gap: 6px; width: 542px; max-width: 100%; margin-bottom: 6px; }
.pt-def span { display: flex; flex-direction: column; padding: 4px 10px; border: 1px solid var(--ex-line); border-radius: 3px;
  background: rgba(0,0,0,.25); font-size: 15px; font-weight: 700; color: var(--ex-text); line-height: 1.2; }
.pt-def small { font-size: 10px; font-weight: 400; letter-spacing: .06em; text-transform: uppercase; color: var(--ex-muted); }
.pt-def .armour { border-left: 3px solid #a04034; } .pt-def .evasion { border-left: 3px solid #4f8a48; }
.pt-def .energy { border-left: 3px solid #4a68a6; } .pt-def .ward { border-left: 3px solid #b9b3a6; }
.pt-def .fire { border-left: 3px solid #b5502e; } .pt-def .cold { border-left: 3px solid #5a8fc0; }
.pt-def .lightning { border-left: 3px solid #c9a83a; } .pt-def .chaos { border-left: 3px solid #9a4a8a; }
#pt-atlas-tip b { display: block; font-family: 'Cinzel', serif; color: var(--ex-gold-hi, #e6c27a); font-size: 14px; margin-bottom: 4px; }
#pt-atlas-tip div { color: #8f8fe0; }
#pt-atlas-tip i { display: block; margin-top: 6px; color: var(--ex-muted, #a69b8c); font-style: normal; font-size: 12px; }
"""


# ---- Exile palette ----------------------------------------------------------
# Every Exile-theme colour is worked out from this one gold.
DEFAULT_ACCENT = "#c9a35a"


def _hls(hex_: str):
    import colorsys
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)


def _hex(h: float, l: float, s: float) -> str:
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h % 1, max(0, min(1, l)), max(0, min(1, s)))
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _rgba(hex_: str, a: float) -> str:
    return f"rgba({int(hex_[1:3], 16)},{int(hex_[3:5], 16)},{int(hex_[5:7], 16)},{a})"


def league_palette(accent: str | None) -> dict:
    """Every Exile-theme colour, derived from one accent colour."""
    accent = accent or DEFAULT_ACCENT
    h, l, s = _hls(accent)
    k = lambda m: min(1.0, s * m)
    return {
        "gold": accent,
        "gold-hi": _hex(h, 0.78, k(1.55)),
        "text": _hex(h, 0.87, k(0.55)),
        "value": _hex(h, 0.90, k(1.20)),
        "muted": _hex(h, 0.66, k(0.42)),
        "dim": _hex(h, 0.56, k(0.30)),
        "line": _hex(h, 0.30, k(0.60)),
        "line-dim": _hex(h, 0.20, k(0.45)),
        "panel": _hex(h, 0.115, k(0.45)),
        "panel-2": _hex(h, 0.090, k(0.45)),
        "bg": _hex(h, 0.075, k(0.40)),
        "bg-2": _hex(h, 0.055, k(0.35)),
        "glow": _hex(h, 0.16, k(0.75)),
        "head": _hex(h, 0.115, k(0.55)),
        "drawer": _hex(h, 0.095, k(0.45)),
        "tab": _hex(h, 0.13, k(0.55)),
        "tab-on": _hex(h, 0.24, k(0.75)),
        "band": _rgba(_hex(h, 0.36, k(1.10)), .42),
        "cur": _hex(h + 0.5, 0.58, max(0.35, min(0.6, s))),   # the act in progress: the accent's opposite
        "a06": _rgba(accent, .06), "a10": _rgba(accent, .10), "a18": _rgba(accent, .18),
        "a20": _rgba(accent, .20), "a28": _rgba(accent, .28),
    }


def palette_css() -> str:
    """CSS variables for the Exile look."""
    pal = league_palette(None)
    vars_ = {f"--ex-{k}": v for k, v in pal.items()}
    vars_.update({"--lg": pal["gold"], "--lg-hi": pal["gold-hi"], "--lg-cur": pal["cur"],
                  "--lg-a28": pal["a28"], "--lg-a50": _rgba(pal["gold"], .5)})
    return ":root { " + " ".join(f"{k}: {v};" for k, v in vars_.items()) + " }"


def kpi(label: str, value: str, detail: str = "", tooltip: str | None = None) -> None:
    with ui.element("div").classes("pt-kpi") as el:
        ui.html(f'<div class="k">{_esc(label)}</div><div class="v">{_esc(value)}</div>'
                + (f'<div class="d">{_esc(detail)}</div>' if detail else ""))
    if tooltip:
        el.tooltip(tooltip)


def kpis(items: list[tuple], min_width: int = 170, columns: int | None = None) -> None:
    """A grid of KPI tiles that wraps evenly instead of stretching the last one.
    columns=N keeps exactly N per row (tiles shrink to fit)."""
    # columns=N: N per row when there's room; on narrow windows they wrap instead of squashing
    floor = 150 if min_width == 170 else min_width
    cols = (f"repeat(auto-fill, minmax(max({floor}px, calc((100% - {columns - 1} * 12px) / {columns})), 1fr))"
            if columns else f"repeat(auto-fill, minmax({min_width}px, 1fr))")
    with ui.element("div").classes("w-full pt-kpis").style(f"display:grid; gap:12px; grid-template-columns:{cols}"):
        for it in items:
            kpi(*it)


SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "nor", "of", "on", "or",
               "per", "the", "to", "vs", "via", "with"}


def title_case(text: str) -> str:
    """'league progression so far' -> 'League Progression So Far'. Small words
    (of, the, per...) stay lowercase unless first or last; words that already
    have capitals or digits inside (NPCs, T16, PoE) are kept as they are."""
    words = text.split(" ")

    def cap(w: str) -> str:
        lead = len(w) - len(w.lstrip("(\"'"))
        return "-".join(p[:1].upper() + p[1:] for p in (w[:lead] + w[lead:][:1].upper() + w[lead + 1:]).split("-"))

    out = []
    for i, w in enumerate(words):
        core = w.strip("()&·:\"',")
        if not core:
            out.append(w)
        elif any(c.isupper() for c in core[1:]) or any(c.isdigit() for c in core):
            out.append(w)
        elif core.lower() in SMALL_WORDS and 0 < i < len(words) - 1 and not w.startswith("("):
            out.append(w.lower())
        else:
            out.append(cap(w))
    return " ".join(out)


def heading(text: str, extra: str = "") -> None:
    ui.label(title_case(text)).classes(f"pt-h2 {extra}")


@contextmanager
def card(title: str | None = None, classes: str = "w-full"):
    with ui.element("div").classes(f"pt-card {classes}") as c:
        if title:
            ui.label(title_case(title)).classes("pt-h2")
        yield c


def note(text: str) -> None:
    ui.label(text).classes("pt-note")


def empty(text: str) -> None:
    ui.label(text).classes("pt-note q-pa-md")


def _esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------ tables

def _keep_short(text):
    """Short labels ("Act 1", "Jul 25, 22:43") stay on one line when a table
    wraps to fit; longer text may wrap."""
    if isinstance(text, str) and " " in text and len(text) <= 16:
        return text.replace(" ", "\u00a0")
    return text


def table(columns: list[dict], rows: list[dict], *, page_size: int = 12, on_click: Callable | None = None,
          empty_text: str = "Nothing yet.", row_key: str = "_k", badges: str | None = None,
          swatch: str | None = None) -> ui.table | None:
    """columns: dicts with name, label, and optional fmt (python fn of value,row), align, sortable.

    The raw value stays in the row for sorting; the formatted text goes to
    a hidden "<name>__t" field that the cell shows.
    """
    if not rows:
        empty(empty_text)
        return None
    out_rows = []
    for i, r in enumerate(rows):
        o = {"_k": i}
        for c in columns:
            v = r.get(c["name"])
            if c.get("fmt"):
                o[c["name"] + "__t"] = _keep_short(c["fmt"](v, r))
            elif not c.get("num") and c["name"] not in (badges, swatch) and isinstance(v, str) and _keep_short(v) != v:
                o[c["name"] + "__t"] = _keep_short(v)
            o[c["name"]] = v if not isinstance(v, (list, dict)) else str(v)
        if badges:
            o[badges] = ", ".join(r.get(badges) or [])
        if "_id" in r:
            o["_id"] = r["_id"]
        if "_color" in r:
            o["_color"] = r["_color"]
        out_rows.append(o)
    cols = []
    for c in columns:
        col = {"name": c["name"], "label": c["label"], "field": c["name"], "sortable": c.get("sortable", True),
               "align": c.get("align", "right" if c.get("num") else "left")}
        if c.get("fmt") or (not c.get("num") and c["name"] not in (badges, swatch)):
            col[":format"] = f"(v, row) => row['{c['name']}__t'] ?? v"
        extra = " ".join(x for x in ("pt-opt" if c.get("opt") else "", "pt-wrapcell" if c.get("wrap") else "") if x)
        if extra:
            col["classes"] = extra
            col["headerClasses"] = extra
        cols.append(col)
    pagination = {"rowsPerPage": page_size} if len(out_rows) > page_size else {"rowsPerPage": 0}
    t = ui.table(columns=cols, rows=out_rows, row_key=row_key, pagination=pagination).classes("w-full")
    t.props("dark flat dense separator=horizontal" + (" hide-bottom" if len(out_rows) <= page_size else ""))
    if badges:
        t.add_slot(f"body-cell-{badges}", f"""
            <q-td :props="props">
              <span v-for="m in (props.value ? props.value.split(', ') : [])" :key="m" class="pt-badge">{{{{ m }}}}</span>
            </q-td>""")
    if swatch:
        # a small colour box before the value, matching the chart beside the table
        t.add_slot(f"body-cell-{swatch}", """
            <q-td :props="props">
              <span class="pt-swatch" :style="{background: props.row._color}"></span>{{ props.value }}
            </q-td>""")
    if on_click:
        t.on("rowClick", lambda e: on_click(e.args[1]))
        t.classes("clickable")
    return t


# ------------------------------------------------------------------ charts

def _axis_label(kind: str) -> str:
    return {
        "h": "v => v > 0 && v < 1 ? Math.round(v * 60) + 'm' : (Math.round(v * 10) / 10) + 'h'",
        "m": "v => Math.round(v) + 'm'",
        "n": "v => v.toLocaleString()",
        "tier": "v => v >= 17 ? 'Nightmare' : 'T' + v",
    }.get(kind, "v => v")


def chart(categories: list, series: list[dict], *, kind: str = "bar", y: str = "n", height: int = 240,
          stacked: bool = False, y_min=None, y_max=None, legend: bool | None = None, smooth: bool = False,
          tooltip_fmt: str | None = None, x_name: str | None = None, all_labels: bool = False,
          zoom: bool = False, zoom_last: int = 60, day_labels: bool = False) -> ui.echart:
    """series: dicts with name, data, color (+ optional type/lineStyle)."""
    legend = (len(series) > 1) if legend is None else legend
    opts = {
        "backgroundColor": "transparent",
        "animation": False,
        "grid": {"left": 48, "right": 16, "top": 16 if not legend else 36, "bottom": 28},
        "legend": {"show": legend, "top": 0, "textStyle": {"color": MUTED}, "itemWidth": 12, "itemHeight": 10},
        "tooltip": {"trigger": "axis", "backgroundColor": "#241f1b", "borderColor": LINE,
                    "textStyle": {"color": "#ece4d8"}, "axisPointer": {"type": "shadow" if kind == "bar" else "line"}},
        "xAxis": {"type": "category" if categories is not None else "value", "data": categories, "name": x_name, "nameLocation": "middle", "nameGap": 24,
                  "nameTextStyle": {"color": GREY},
                  "axisLabel": {"color": GREY}, "axisLine": {"lineStyle": {"color": LINE}}, "axisTick": {"show": False},
                  "splitLine": {"show": False}},
        "yAxis": {"type": "value", "min": y_min, "max": y_max, "splitLine": {"lineStyle": {"color": LINE}},
                  "axisLabel": {"color": GREY, ":formatter": _axis_label(y)}},
        "series": [],
    }
    y2 = next((s for s in series if s.get("y2")), None)
    if y2:
        opts["yAxis"] = [opts["yAxis"], {"type": "value", "name": y2.get("y2_name"), "nameTextStyle": {"color": GREY},
                                         "splitLine": {"show": False}, "axisLabel": {"color": GREY}}]
        opts["grid"]["right"] = 48
    if zoom and categories:
        start = 0 if len(categories) <= 100 else len(categories) - zoom_last
        opts["dataZoom"] = [
            {"type": "inside", "startValue": start, "endValue": len(categories) - 1},
            {"type": "slider", "startValue": start, "endValue": len(categories) - 1, "height": 18, "bottom": 6,
             "borderColor": LINE, "fillerColor": "rgba(217,164,65,.15)", "handleStyle": {"color": GOLD},
             "textStyle": {"color": GREY}, "dataBackground": {"lineStyle": {"color": GREY}, "areaStyle": {"color": "#2a2420"}}},
        ]
        opts["grid"]["bottom"] = 64
    if day_labels and categories:
        # Day numbers on the first axis, and a second axis underneath with a
        # bracket per month: ticks at the month boundaries and the month name
        # in the middle of its days.
        n = len(categories)
        opts["xAxis"]["axisLabel"][":formatter"] = "v => v.slice(4)"
        opts["xAxis"]["axisLabel"]["hideOverlap"] = True   # ECharts thins the day numbers to fit the width
        months: list[tuple[int, int]] = []
        for i, c in enumerate(categories):
            if not months or categories[months[-1][0]][:3] != c[:3]:
                months.append((i, i))
            else:
                months[-1] = (months[-1][0], i)
        mids = [(a_ + b_) // 2 for a_, b_ in months]
        starts = [a_ for a_, _ in months] + [n - 1]
        month_axis = {
            "type": "category", "data": categories, "position": "bottom", "offset": 22,
            "axisLine": {"show": True, "lineStyle": {"color": "#6f665b", "width": 1.5}},
            "axisTick": {"show": True, "inside": True, "length": 14, "lineStyle": {"color": "#6f665b", "width": 1.5},
                         ":interval": f"(i) => {starts}.includes(i)"},
            "axisLabel": {"color": MUTED, "fontSize": 12, ":formatter": "v => v.slice(0, 3)",
                          ":interval": f"(i) => {mids}.includes(i)"},
            "splitLine": {"show": False},
        }
        opts["xAxis"] = [opts["xAxis"], month_axis]
        opts["grid"]["bottom"] = opts["grid"]["bottom"] + 24
        for dz in opts.get("dataZoom", []):
            dz["xAxisIndex"] = [0, 1]
    if all_labels:
        opts["xAxis"]["axisLabel"].update({"interval": 0, "width": 78, "overflow": "break", "fontSize": 10})
        opts["grid"]["bottom"] = 40
    if y == "tier":
        opts["yAxis"]["interval"] = 2
    if tooltip_fmt:
        opts["tooltip"][":valueFormatter"] = tooltip_fmt
    for s in series:
        ser = {"name": s["name"], "type": s.get("type", kind), "data": s["data"],
               "itemStyle": {"color": s.get("color", GOLD), "borderRadius": 2 if kind == "bar" else 0},
               "emphasis": {"focus": "series"} if len(series) > 3 else {}}
        if stacked and ser["type"] == "bar":
            ser["stack"] = "total"
        if s.get("y2"):
            ser["yAxisIndex"] = 1
        if s.get("tip"):
            ser["tooltip"] = {":valueFormatter": s["tip"]}
        if ser["type"] == "line":
            ser.update({"showSymbol": s.get("symbols", len(s["data"]) < 50), "symbolSize": 5, "smooth": smooth,
                        "lineStyle": {"width": s.get("width", 2), "color": s.get("color", GOLD), **s.get("lineStyle", {})},
                        "connectNulls": s.get("connect", True)})
            if s.get("z"):
                ser["z"] = s["z"]
        if kind == "bar":
            ser["barMaxWidth"] = 34
        opts["series"].append(ser)
    return ui.echart(opts).style(f"height:{height}px; width:100%")


HOURS_TIP = "v => v == null ? '–' : (Math.round(v*10)/10) + ' h'"
