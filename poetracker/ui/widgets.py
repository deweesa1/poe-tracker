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
.pt-drawer-foot {{ border-top: 1px solid var(--ex-line-dim, #2d2722); }}
.pt-ver {{ align-self: stretch; margin: 6px 14px 0; padding: 10px 6px 8px; border-top: 1px solid var(--ex-line-dim, #2d2722); }}
.pt-logo {{ padding-left: 16px; padding-right: 16px; }}
.pt-collapse {{ color: var(--ex-dim, #6f665a); padding: 4px; border-radius: 4px; }}
.pt-collapse:hover {{ color: var(--ex-gold-hi, #e6c27a); background: rgba(255,255,255,.04); }}
body:not(.pt-mini) .pt-nav-tip {{ display: none !important; }}
.q-drawer--mini .q-mini-drawer-hide {{ display: none !important; }}
.q-drawer--mini .pt-logo {{ padding: 24px 0 16px !important; justify-content: center; width: 100%; }}
.q-drawer--mini .pt-nav .q-item {{ justify-content: center; padding-left: 0 !important; padding-right: 0 !important; margin: 1px 8px; }}
.q-drawer--mini .pt-nav .q-item__section--avatar {{ min-width: 0 !important; padding-right: 0 !important; }}
.q-drawer--mini .pt-ver {{ margin: 6px 10px 0; padding: 10px 0 8px; display: flex; justify-content: center; }}
.q-drawer--mini .pt-ver > .nicegui-row {{ width: auto !important; justify-content: center; }}
.q-drawer--mini .pt-collapse-row {{ justify-content: center; padding-left: 0 !important; padding-right: 0 !important; }}
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
.pt-nav .q-item { font-family: 'Cinzel', serif; font-weight: 600; font-size: 13px; letter-spacing: .03em; color: var(--ex-muted);
  border-radius: 2px; border-left: 2px solid transparent; }
.pt-nav .q-item:hover { color: var(--ex-gold-hi); background: var(--ex-a06); }
.pt-nav .q-item.active { color: var(--ex-gold-hi); border-left-color: var(--ex-gold);
  background: linear-gradient(90deg, var(--ex-a20), transparent 85%); }
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
.pt-nav .q-item.active { border-left-color: var(--lg, var(--ex-gold)) !important; }
.q-tab--active { box-shadow: inset 0 2px 0 var(--lg, var(--ex-gold)); }
.pt-zone-head { font-family: 'Cinzel', serif; letter-spacing: .04em; }
::-webkit-scrollbar { width: 10px; height: 10px; } ::-webkit-scrollbar-track { background: var(--ex-bg-2); }
::-webkit-scrollbar-thumb { background: var(--ex-line); border: 2px solid var(--ex-bg-2); border-radius: 6px; }
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
