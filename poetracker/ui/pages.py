"""All dashboard pages."""
from __future__ import annotations

from nicegui import ui

from .. import captures, config as config_mod, db, metrics
from . import fmt
from .layout import STATE, auto_refresh, character_select, frame, is_open, league_select, league_start, locked
from .widgets import LINE as LINE_C
from .widgets import (BLUE, DUR_TIP, GOLD, GREEN, GREY, HOURS_TIP, PALETTE, RED, TEAL, VIOLET, card, chart, empty,
                      heading, kpis, note, table)


def _reload():
    STATE.invalidate()
    ui.navigate.reload()


def _filters_league_char():
    league_select(_reload)
    character_select(_reload)


def _scope() -> str:
    lg = STATE.league()
    cid = STATE.character(lg)
    name = next((c["name"] for c in STATE.characters(lg) if c["id"] == cid), None)
    return f"{lg or 'No league yet'} · {name or 'all characters'}"


def _no_data():
    from .layout import busy
    if busy():
        st = STATE.tracker.status()
        p = st.get("progress")
        with ui.row().classes("items-center gap-3 q-pa-md"):
            ui.spinner(size="md", color="primary")
            verb = {"rebuilding": "Rebuilding", "reading log": "Reading"}.get(st.get("phase"), "Loading")
            ui.label(f"{verb} your log history{f' ({p:.0%})' if p is not None else ''}… "
                     "This page fills in by itself when it's done.").classes("pt-sub")
        return
    empty("No games found in the log yet. Play a bit with the tracker running, or check the Client.txt path in Settings.")


KIND = {"side": "Side area", "map": "Map", "campaign": "Campaign", "activity": "Activity", "boss": "Boss", "town": "Town", "other": "Other area"}

RUN_COLS = [
    {"name": "start_utc", "label": "Started", "fmt": lambda v, r: fmt.when(v)},
    {"name": "area_name", "label": "Map", "fmt": lambda v, r: v or r.get("area_id")},
    {"name": "tier", "label": "Tier", "num": True, "fmt": lambda v, r: fmt.tier(v)},
    {"name": "active_s", "label": "Time in Map", "num": True, "fmt": lambda v, r: fmt.dur(v)},
    {"name": "deaths", "label": "Deaths", "num": True},
    {"name": "quantity", "label": "Quant", "num": True, "fmt": lambda v, r: "–" if v is None else f"{v}%"},
    {"name": "pack_size", "label": "Pack Size", "num": True, "fmt": lambda v, r: "–" if v is None else f"{v}%"},
    {"name": "mechanics", "label": "Mechanics", "sortable": False},
    {"name": "character", "label": "Character"},
]


# ====================================================================== Overview
def _fill_days(daily: list[dict], keys: list[str]) -> list[dict]:
    """Add the days you didn't play (as zeros) so the chart reads 01 02 03..."""
    from datetime import date, timedelta
    if not daily:
        return []
    have = {d["day"]: d for d in daily}
    d0 = date.fromisoformat(daily[0]["day"])
    d1 = date.fromisoformat(daily[-1]["day"])
    out = []
    while d0 <= d1:
        k = d0.isoformat()
        out.append(have.get(k) or {"day": k, **{x: 0 for x in keys}})
        d0 += timedelta(days=1)
    return out


@ui.page("/")
def overview_page():
    lg = STATE.league()
    cid = STATE.character(lg)
    body = frame("/", "Overview", _scope(), _filters_league_char)

    @ui.refreshable
    def content():
        if not lg:
            return _no_data()
        d = STATE.cached(("overview", lg, cid), lambda c: metrics.overview(c, STATE.cfg, lg, cid, days=0))
        last = STATE.cached(("last_session", lg, cid), lambda c: metrics.last_session(c, lg, cid))
        t = d["totals"]

        with card("Last session"):
            if not last:
                empty("No sessions yet.")
            else:
                vs = ""
                if last["avg_session_s"]:
                    diff = (last["active_s"] - last["avg_session_s"]) / last["avg_session_s"]
                    vs = f"{fmt.signed_pct(diff)} vs your average session"
                n_chars = len(last["characters"])
                ui.label(f"{fmt.when(last['start'])} – {fmt.when(last['end'], with_date=False)} · "
                         f"{n_chars} character{'s' if n_chars != 1 else ''} played").classes("pt-sub text-sm q-mb-sm")
                hrs = last["active_s"] / 3600 if last["active_s"] else 0
                per_h = (lambda n: fmt.num(n / hrs, 1) if hrs >= 0.1 else "–")
                kpis([
                    ("Time Played", fmt.dur(last["active_s"], True), vs),
                    ("Total Maps Ran", fmt.num(last["maps"]), f"{fmt.dur(last['map_s'], True)} inside maps" if last["maps"] else ""),
                    ("Levels Gained", fmt.num(last["levels_gained"])),
                    ("Deaths", fmt.num(last["deaths"])),
                    ("Time Spent AFK", fmt.dur(last["afk_s"], True) if last["afk_s"] else "0m", "not counted as played"),
                    ("Maps per Hour", per_h(last["maps"]), "per hour played"),
                    ("Levels per Hour", per_h(last["levels_gained"]), "per hour played"),
                    ("Deaths per Hour", per_h(last["deaths"]), "per hour played"),
                ], columns=4)
                if n_chars:
                    ui.label("Characters this session").classes("pt-note q-mt-md q-mb-xs")
                    table([
                        {"name": "name", "label": "Character"},
                        {"name": "class", "label": "Class"},
                        {"name": "level", "label": "Level Now", "num": True},
                        {"name": "start", "label": "First Played", "fmt": lambda v, r: fmt.when(v, with_date=False)},
                        {"name": "active_s", "label": "Time Played", "num": True, "fmt": lambda v, r: fmt.dur(v, True)},
                        {"name": "maps", "label": "Maps Ran", "num": True},
                        {"name": "deaths", "label": "Deaths", "num": True},
                        {"name": "levels_gained", "label": "Levels Gained", "num": True},
                        {"name": "areas", "label": "Areas Entered", "num": True},
                    ], [{**c, "_id": c["id"]} for c in last["characters"]], on_click=_open_character if is_open("/character") else None)

        heading("League progression so far", "q-mt-sm")
        kpis([
            ("Time Played", fmt.hours(t["active_s"]), f"over {t['days_played']} days"),
            ("Time in Campaign", fmt.hours(t["campaign_s"]), f"{fmt.pct(t['campaign_s'] / t['active_s'])} of play" if t["active_s"] else ""),
            ("Time Mapping", fmt.hours(t["mapping_s"]), f"{fmt.pct(t['mapping_s'] / t['active_s'])} of play · {fmt.num(t['maps'])} maps" if t["active_s"] else ""),
            ("Average Time Played per Day", fmt.dur(t["active_s"] / t["days_played"], True) if t["days_played"] else "–", "on days you played"),
            ("Deaths", fmt.num(t["deaths"]), f"{fmt.num(t['deaths'] / t['maps'], 2)} per map" if t["maps"] else ""),
        ], columns=5)

        voidstone_section(lg)

        daily = _fill_days(d["all_daily"], ["active_s", "mapping_s", "campaign_s", "maps", "deaths"])
        with card("Playtime per day"):
            if not daily:
                empty("No playtime yet.")
            else:
                cats = [fmt.day_label(x["day"]) for x in daily]
                other = [max(0, (x["active_s"] or 0) - (x["mapping_s"] or 0) - (x["campaign_s"] or 0)) / 3600 for x in daily]
                chart(cats, [
                    {"name": "Campaign", "data": [round((x["campaign_s"] or 0) / 3600, 2) for x in daily], "color": BLUE, "tip": HOURS_TIP},
                    {"name": "Maps & endgame", "data": [round((x["mapping_s"] or 0) / 3600, 2) for x in daily], "color": GOLD, "tip": HOURS_TIP},
                    {"name": "Towns & hideout", "data": [round(v, 2) for v in other], "color": GREY, "tip": HOURS_TIP},
                    {"name": "Maps Ran", "type": "line", "data": [x.get("maps") or 0 for x in daily], "color": TEAL,
                     "y2": True, "y2_name": "maps", "symbols": False, "z": 10},
                ], stacked=True, y="h", height=320, zoom=True, day_labels=True)
                note("Bars: hours played each day (left axis). Line: maps ran that day (right axis). "
                     "Scroll on the chart or drag the slider to zoom.")

        with card("Characters"):
            rows = [{**c, "_id": c["id"]} for c in d["characters"]]
            table([
                {"name": "name", "label": "Character"},
                {"name": "class", "label": "Class"},
                {"name": "level", "label": "Level", "num": True},
                {"name": "active_s", "label": "Time Played", "num": True, "fmt": lambda v, r: fmt.dur(v, True)},
                {"name": "maps", "label": "Maps Ran", "num": True},
                {"name": "deaths", "label": "Deaths", "num": True},
                {"name": "first_seen", "label": "Created", "opt": True, "fmt": lambda v, r: fmt.date(v)},
                {"name": "last_seen", "label": "Last Played", "fmt": lambda v, r: fmt.when(v)},
            ], rows, on_click=_open_character if is_open("/character") else None, page_size=10)
            note("Click a character to open it.")

        with card("Recent ran maps"):
            table(RUN_COLS[:5] + [RUN_COLS[7], RUN_COLS[8]], d["recent_runs"], badges="mechanics", page_size=10,
                  empty_text="No maps in this league yet.")

    with body:
        content()
    auto_refresh(content.refresh)


def voidstone_section(lg: str) -> None:
    v = STATE.cached(("voidstones", lg), lambda c: metrics.voidstones(c, STATE.cfg, lg))
    with card(f"Voidstones · {v['obtained']} of {v['total']}"):
        with ui.element("div").classes("w-full").style(
                "display:grid; gap:12px; grid-template-columns:repeat(auto-fill, minmax(max(220px, calc((100% - 36px) / 4)), 1fr))"):
            for s in v["voidstones"]:
                got = s["obtained"]
                border = "#7cb36b" if got else LINE_C
                with ui.element("div").classes("pt-kpi").style(f"border-color:{border}"):
                    if got:
                        status = (f'<span class="pt-up">{"Likely obtained" if s["likely"] else "Obtained"}</span> · '
                                  f'{fmt.when(s["when"])}'
                                  + (f' · day {s["days_into_league"] + 1:.0f}' if s["days_into_league"] is not None else ""))
                    else:
                        status = f'<span class="pt-note">{s["steps_done"]} of {s["steps_total"]} bosses down</span>'
                    steps_html = ""
                    for st in s["steps"]:
                        fk = st.get("first_kill")
                        if st.get("count_only"):
                            mark, detail = "•", f'{st["attempts"]} run{"s" if st["attempts"] != 1 else ""}'
                        elif fk:
                            mark = "✓" if st.get("detected") == "dialogue" else "✓?"
                            detail = (f'{fmt.when(fk["ts_utc"])} · {fk["character"] or ""}'
                                      + (f' · {st["attempts_to_kill"]} attempt{"s" if st["attempts_to_kill"] != 1 else ""}'
                                         if st.get("attempts_to_kill") else ""))
                        else:
                            mark = "○"
                            detail = f'{st["attempts"]} attempt{"s" if st["attempts"] != 1 else ""}' if st["attempts"] else "not attempted"
                        color = "#7cb36b" if fk else "#a69b8c"
                        steps_html += (f'<div style="display:flex;gap:8px;margin-top:4px;font-size:12px">'
                                       f'<span style="color:{color};width:18px">{mark}</span>'
                                       f'<span style="flex:1"><span style="color:#ece4d8">{st["boss"]}</span><br>'
                                       f'<span class="pt-note">{detail}</span></span></div>')
                    ui.html(f'<div class="k">{s["name"]}</div>'
                            f'<div style="font-size:13px;margin:2px 0 6px">{status}</div>'
                            f'<div class="pt-note" style="margin-bottom:4px">from {s["from"]}</div>{steps_html}')
        note("✓ = boss defeat line seen in the log. ✓? = no defeat line exists for this fight, so it counts when you "
             "leave the arena alive after a while. Voidstones reset every league. The bosses and lines are in milestones.yaml.")


def _open_character(row):
    STATE.set_pref("character_page", row["_id"])
    ui.navigate.to("/character")


# ====================================================================== Maps
@ui.page("/maps")
def maps_page():
    if (r := locked("/maps")):
        return r
    lg = STATE.league()
    cid = STATE.character(lg)
    body = frame("/maps", "Maps", _scope(), _filters_league_char)
    tab = STATE.pref("maps_tab", "runs")

    with body:
        with ui.tabs(value=tab, on_change=lambda e: STATE.set_pref("maps_tab", e.value)).props(
                "dense align=left active-color=primary indicator-color=primary").classes("text-grey-5") as tabs:
            ui.tab("runs", "Maps Ran")
            ui.tab("copied", "Detailed Maps")
        with ui.tab_panels(tabs, value=tab).classes("w-full bg-transparent").props("animated=false"):
            with ui.tab_panel("runs").classes("q-pa-none"):
                runs_tab(lg, cid)
            with ui.tab_panel("copied").classes("q-pa-none"):
                copied_tab(lg, cid)


PIE_COLORS = PALETTE + ["#8a7f72", "#b5884a", "#5f8f88", "#7d6aa3", "#a85c4d"]


def _pie(data: list[dict], height: int = 300, legend: bool = True) -> None:
    """data: [{name, value}] -> a donut chart."""
    ui.echart({
        "backgroundColor": "transparent", "animation": False,
        "tooltip": {"trigger": "item", "backgroundColor": "#241f1b", "borderColor": LINE_C,
                    "textStyle": {"color": "#ece4d8"}, "formatter": "{b}: {c} ({d}%)"},
        "title": {"show": False},
        # "plain" legends wrap onto extra lines instead of paging with arrows
        "legend": {"show": legend, "type": "plain", "orient": "horizontal", "bottom": 0, "left": "center", "width": "96%",
                   "textStyle": {"color": "#a69b8c", "fontSize": 13}, "itemWidth": 11, "itemHeight": 11, "itemGap": 16},
        "color": PIE_COLORS,
        "series": [{"type": "pie", "radius": ["40%", "70%"] if not legend else ["36%", "62%"],
                    "center": ["50%", "42%" if legend else "50%"], "data": data,
                    "itemStyle": {"borderColor": "#1d1916", "borderWidth": 2}, "label": {"show": False},
                    "emphasis": {"label": {"show": True, "color": "#ece4d8", "formatter": "{d}%", "fontSize": 14}}}],
    }).style(f"height:{height}px; width:100%")


def runs_tab(lg, cid):
    @ui.refreshable
    def content():
        if not lg:
            return _no_data()
        d = STATE.cached(("maps", lg, cid), lambda c: {
            **metrics.maps_summary(c, STATE.cfg, lg, cid), "other": metrics.other_runs(c, STATE.cfg, lg, cid)})
        t = d["totals"]
        with ui.column().classes("w-full gap-4"):
            kpis([
                ("Maps Ran", fmt.num(t["runs"])),
                ("Time Mapping", fmt.hours(t["active_s"]), "inside maps, no hideout or AFK"),
                ("Average Map Time", fmt.dur(t["avg_active_s"])),
                ("Maps per Hour", fmt.num(t["maps_per_hour"], 1), "of time inside maps"),
                ("Deaths", fmt.num(t["deaths"]), "inside maps"),
                ("Deaths per Map", fmt.num(t["deaths_per_map"], 2)),
            ], columns=6)

            days = _fill_days(d["days"], ["runs", "deaths", "active_s"])
            cats = [fmt.day_label(x["day"]) for x in days]
            with card("Maps Ran per Day"):
                if days:
                    chart(cats, [{"name": "Maps Ran", "data": [x["runs"] for x in days], "color": GOLD},
                                 {"name": "Maps per Hour", "type": "line", "color": TEAL, "symbols": False, "connect": False,
                                  "data": [round(x["maps_per_hour"], 1) if x.get("maps_per_hour") else None for x in days]},
                                 {"name": "Deaths", "type": "line", "color": RED, "symbols": False, "y2": True,
                                  "y2_name": "deaths", "data": [x.get("deaths") or 0 for x in days]}],
                          height=280, zoom=True, day_labels=True)
                    note("Bars: maps ran that day. Lines: maps per hour inside maps (left axis) and deaths in maps (right axis). "
                         "Scroll on the chart or drag the slider to zoom.")
                else:
                    empty("No maps ran yet.")
            with card("Tier Progression"):
                if days:
                    chart(cats, [{"name": "Highest Tier", "type": "line", "data": [x.get("max_tier") or None for x in days], "color": GOLD, "connect": False},
                                 {"name": "Average Tier", "type": "line", "color": TEAL, "connect": False,
                                  "data": [round(x["avg_tier"], 1) if x.get("avg_tier") else None for x in days]}],
                          kind="line", y="tier", y_min=1, y_max=17, height=240, zoom=True, day_labels=True)
                    note("Tier 17 maps are shown as Nightmare.")

            with card("Mechanics Seen in Maps"):
                mech = d["mechanics"]
                if not mech:
                    empty("No mechanics detected. Turn on Options > UI > Output Dialogue To Chat in game.")
                else:
                    mech = [{**m, "_color": PIE_COLORS[i % len(PIE_COLORS)]} for i, m in enumerate(mech)]
                    with ui.row().classes("w-full gap-6 items-center pt-wrap"):
                        with ui.element("div").classes("pt-pie"):
                            _pie([{"name": m["mechanic"], "value": m["runs"]} for m in mech], height=280, legend=False)
                        with ui.element("div").classes("pt-wide"):
                            table([
                                {"name": "mechanic", "label": "Mechanic"},
                                {"name": "runs", "label": "Maps Ran", "num": True},
                                {"name": "share", "label": "Share of Maps", "num": True, "fmt": lambda v, r: fmt.pct(v)},
                            ], mech, page_size=len(mech), swatch="mechanic")
                    note("Detected from NPC dialogue and side areas inside each map. A map can have several mechanics, "
                         "so shares add up to more than 100%.")

            with card("Map Information by Tier"):
                tiers = d["tiers"]
                table([
                    {"name": "tier", "label": "Tier", "fmt": lambda v, r: fmt.tier(v) if v else "?"},
                    {"name": "runs", "label": "Maps Ran", "num": True},
                    {"name": "share", "label": "Share", "num": True, "opt": True, "fmt": lambda v, r: fmt.pct(v)},
                    {"name": "active_s", "label": "Time Mapping", "num": True, "fmt": lambda v, r: fmt.dur(v, True)},
                    {"name": "avg_active_s", "label": "Average Map Time", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                    {"name": "fastest_s", "label": "Fastest", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                    {"name": "maps_per_hour", "label": "Maps per Hour", "num": True, "fmt": lambda v, r: fmt.num(v, 1)},
                    {"name": "deaths", "label": "Deaths", "num": True},
                    {"name": "deaths_per_map", "label": "Deaths per Map", "num": True, "fmt": lambda v, r: fmt.num(v, 2)},
                    {"name": "deathless_share", "label": "Deathless Maps", "num": True, "fmt": lambda v, r: fmt.pct(v)},
                    {"name": "avg_quantity", "label": "Avg Quant", "num": True, "fmt": lambda v, r: "–" if v is None else f"{v:.0f}%"},
                    {"name": "first", "label": "First Ran", "opt": True, "fmt": lambda v, r: fmt.when(v)},
                ], list(reversed(tiers)), page_size=17)

            with card("Most-Run Maps"):
                top = d["top_maps"][:15]
                if top:
                    chart([x["map"] for x in top], [
                        {"name": "Maps Ran", "data": [x["runs"] for x in top], "color": GOLD},
                        {"name": "Average Map Time (min)", "type": "line", "color": TEAL, "y2": True, "y2_name": "min",
                         "data": [round(x["avg_active_s"] / 60, 1) for x in top]},
                        {"name": "Deaths per Map", "type": "line", "color": RED, "y2": True,
                         "data": [round(x["deaths_per_map"], 2) if x["deaths_per_map"] is not None else None for x in top]},
                    ], height=260, all_labels=True)
                table([
                    {"name": "map", "label": "Map"},
                    {"name": "runs", "label": "Maps Ran", "num": True},
                    {"name": "share", "label": "Share", "num": True, "fmt": lambda v, r: fmt.pct(v)},
                    {"name": "avg_tier", "label": "Average Tier", "num": True, "fmt": lambda v, r: fmt.num(v, 1)},
                    {"name": "active_s", "label": "Time Mapping", "num": True, "fmt": lambda v, r: fmt.dur(v, True)},
                    {"name": "avg_active_s", "label": "Average Map Time", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                    {"name": "fastest_s", "label": "Fastest", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                    {"name": "deaths", "label": "Deaths", "num": True},
                    {"name": "deaths_per_map", "label": "Deaths per Map", "num": True, "fmt": lambda v, r: fmt.num(v, 2)},
                    {"name": "last", "label": "Last Ran", "fmt": lambda v, r: fmt.when(v)},
                ], d["top_maps"], page_size=10)

            other = d["other"]
            with card("Other Endgame Content"):
                if not other["items"]:
                    empty("No other endgame content in this league yet.")
                else:
                    with ui.row().classes("w-full gap-4 items-start pt-wrap"):
                        with ui.element("div").classes("pt-narrow"):
                            ui.label("Time spent by type").classes("pt-note")
                            _pie([{"name": g["group"], "value": round(g["active_s"] / 3600, 1)} for g in other["groups"]], height=320)
                        with ui.element("div").classes("pt-wide"):
                            items = other["items"][:15][::-1]
                            ui.label("Time spent (hours)").classes("pt-note")
                            ch = chart([x["name"] for x in items], [
                                {"name": "Hours", "data": [round(x["active_s"] / 3600, 2) for x in items], "color": GOLD}],
                                height=max(240, 24 * len(items) + 40), legend=False, tooltip_fmt=HOURS_TIP)
                            o = ch.options
                            o["xAxis"], o["yAxis"] = {**o["yAxis"], "axisLabel": {"color": "#6f665b"}}, {**o["xAxis"], "axisLabel": {"color": "#a69b8c", "width": 150, "overflow": "break", "lineHeight": 13}}
                            o["grid"]["left"] = 160
                    table([
                        {"name": "group", "label": "Type"},
                        {"name": "name", "label": "Content"},
                        {"name": "runs", "label": "Runs", "num": True},
                        {"name": "active_s", "label": "Time Spent", "num": True, "fmt": lambda v, r: fmt.dur(v, True)},
                        {"name": "avg_s", "label": "Average Run", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                        {"name": "deaths", "label": "Deaths", "num": True},
                        {"name": "last", "label": "Last Run", "fmt": lambda v, r: fmt.when(v)},
                    ], other["items"], page_size=12)
                    note("Pinnacle bosses give Voidstones or are the hardest fights; Atlas bosses lead up to them. "
                         "League mechanic areas are entered from maps or the map device (Simulacrum, Timeless Conflict, Sacred Grove…). "
                         "Edit the list under 'content' in areas.yaml.")

            with card("All Maps Ran"):
                table(RUN_COLS, d["runs"], badges="mechanics", page_size=15)

    content()
    auto_refresh(content.refresh)


def copied_tab(lg, cid):
    sel_key = "mod_filter"

    @ui.refreshable
    def content():
        rows = STATE.cached(("mod_runs", lg, cid), lambda c: metrics.map_mod_runs(c, STATE.cfg, lg, cid))
        selected = [m for m in (STATE.pref(sel_key) or [])]
        stats = metrics.map_mod_stats(rows, selected)
        with ui.column().classes("w-full gap-4"):
            with card("How It Works"):
                ui.markdown(
                    "With the tracker running, hover a map in game and press **Ctrl+C** (the game's own copy key; "
                    "**Ctrl+Alt+C** works too). The tracker saves the map's modifiers, quantity and pack size, and links it "
                    f"to the next map you open within {STATE.cfg.settings.get('capture_link_minutes', 10)} minutes. "
                    "Copy several and run them one by one: each map you open takes the latest saved one that fits. "
                    "Numbers in modifiers become # so the same modifier groups together, and the lines of one modifier "
                    "are joined with /.").classes("pt-sub")
            if not rows:
                empty("No detailed maps linked to a map run yet in this selection. Ctrl+C a map in game, then run it.")
            else:
                with card("Map Modifiers"):
                    @ui.refreshable
                    def compare_view():
                        sel = [m for m in (STATE.pref(sel_key) or [])]
                        cmp_ = metrics.map_mod_stats(rows, sel)["compare"]
                        if not cmp_:
                            return
                        w, wo = cmp_["with"], cmp_["without"]

                        def vs(a, b):
                            if a is None or not b:
                                return ""
                            diff = (a - b) / b
                            return f"{fmt.signed_pct(diff)} vs maps without" if abs(diff) >= 0.005 else "same as maps without"
                        ui.label(f"Maps with {'this modifier' if len(sel) == 1 else 'all ' + str(len(sel)) + ' modifiers'}"
                                 f" vs your other detailed maps").classes("pt-note q-mt-md")
                        kpis([
                            ("Maps Ran", fmt.num(w["maps"]), f"of {stats['maps']} detailed maps"),
                            ("Deaths", fmt.num(w["deaths"]), f"{fmt.num(wo['deaths'])} on the other maps"),
                            ("Deaths per Map", fmt.num(w["deaths_per_map"], 2), vs(w["deaths_per_map"], wo["deaths_per_map"])),
                            ("Deathless Maps", fmt.pct(w["deathless_share"]), f"{fmt.pct(wo['deathless_share'])} without"),
                            ("Average Map Time", fmt.dur(w["avg_active_s"]), vs(w["avg_active_s"], wo["avg_active_s"])),
                            ("Average Quant", f"{fmt.num(w['avg_quantity'])}%" if w["avg_quantity"] is not None else "–",
                             f"{fmt.num(wo['avg_quantity'])}% without" if wo["avg_quantity"] is not None else ""),
                        ], columns=6)

                    def changed(e):
                        STATE.set_pref(sel_key, e.value or [])
                        compare_view.refresh()
                    ui.select({m["mod"]: f'{m["mod"]} ({m["maps"]})' for m in stats["mods"]}, value=selected, multiple=True,
                              label="Pick one or more modifiers to compare maps that have all of them against maps that don't",
                              on_change=changed).props("outlined dense dark use-chips clearable").classes("w-full")
                    compare_view()
                    ui.label("Every modifier on your detailed maps").classes("pt-note q-mt-md")
                    table([
                        {"name": "mod", "label": "Modifier"},
                        {"name": "maps", "label": "Maps Ran", "num": True},
                        {"name": "deaths", "label": "Deaths", "num": True},
                        {"name": "deaths_per_map", "label": "Deaths per Map", "num": True, "fmt": lambda v, r: fmt.num(v, 2)},
                        {"name": "deathless_share", "label": "Deathless Maps", "num": True, "fmt": lambda v, r: fmt.pct(v)},
                        {"name": "avg_active_s", "label": "Average Map Time", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                        {"name": "avg_quantity", "label": "Avg Quant", "num": True, "fmt": lambda v, r: "–" if v is None else f"{v:.0f}%"},
                        {"name": "avg_pack_size", "label": "Avg Pack Size", "num": True, "fmt": lambda v, r: "–" if v is None else f"{v:.0f}%"},
                    ], stats["mods"], page_size=15)
                    a = stats["all"]
                    note(f"All {stats['maps']} detailed maps: {fmt.num(a['deaths_per_map'], 2)} deaths per map, "
                         f"{fmt.pct(a['deathless_share'])} deathless, {fmt.dur(a['avg_active_s'])} average.")
            caps = STATE.cached(("captures",), lambda c: metrics.captures(c, 500))
            with card("Detailed Maps"):
                rows_ = [{**c, "_id": c["id"],
                          "other": ", ".join(f"{k} {v}%" for k, v in (c["properties"] or {}).items()
                                             if k not in ("Item Quantity", "Monster Pack Size", "Item Rarity", "Item Level", "Monster Level", "Area Level"))}
                         for c in caps]
                table([
                    {"name": "ts_utc", "label": "Saved", "fmt": lambda v, r: fmt.when(v)},
                    {"name": "name", "label": "Map", "fmt": lambda v, r: v if not r.get("base") or r["base"] == v else f"{v} ({r['base']})"},
                    {"name": "tier", "label": "Tier", "num": True, "fmt": lambda v, r: fmt.tier(v)},
                    {"name": "quantity", "label": "Quant", "num": True, "fmt": lambda v, r: "–" if v is None else f"{v}%"},
                    {"name": "pack_size", "label": "Pack Size", "num": True, "fmt": lambda v, r: "–" if v is None else f"{v}%"},
                    {"name": "item_rarity", "label": "Rarity", "num": True, "fmt": lambda v, r: "–" if v is None else f"{v}%"},
                    {"name": "other", "label": "Other Properties"},
                    {"name": "mods", "label": "Modifiers", "num": True, "opt": True, "fmt": lambda v, r: str(len(r["mods"] or []))},
                    {"name": "run_start", "label": "Linked Run",
                     "fmt": lambda v, r: f"{r.get('area_name') or ''} {fmt.when(v, False)}" if v else "waiting"},
                ], rows_, page_size=15, empty_text="No detailed maps yet. Hover a map in game and press Ctrl+C.")
            with card("Paste a Map by Hand"):
                text = ui.textarea(placeholder="Paste map text here (Ctrl+C on a map in game)").props("outlined dark autogrow").classes("w-full")

                def save():
                    con = db.connect()
                    try:
                        if not captures.save_capture(con, text.value or ""):
                            ui.notify("That text isn't a map (copy it in game with Ctrl+C).", type="warning")
                            return
                        captures.link_pending(con, STATE.cfg)
                    finally:
                        con.close()
                    STATE.invalidate()
                    ui.notify("Map saved.", type="positive")
                    content.refresh()
                ui.button("Save", on_click=save).props("unelevated")

    content()


# ====================================================================== Campaign
@ui.page("/campaign")
def campaign_page():
    if (r := locked("/campaign")):
        return r
    ls = league_start()
    live = ls["phase"] == "campaign"
    lg = ls["league"] if live else STATE.league()
    lock = STATE.cached(("campaign_lock", lg), lambda c: metrics.campaign_lock(c, lg))
    sel = {"id": lock["id"]}
    who = (f"{lock['name']} · first to finish the campaign" if lock["completed"] else
           f"{lock['name']} · furthest along (first to finish Act 10 takes this)") if lock["id"] else ""
    body = frame("/campaign", "League Start Campaign", " · ".join(x for x in (lg, who) if x),
                 None if live else (lambda: league_select(_reload)))

    @ui.refreshable
    def content():
        if not sel["id"]:
            if live:
                return empty(f"Waiting for your first character in {lg}. Splits start in The Twilight Strand.")
            return empty("No campaign runs in this league. A run starts in The Twilight Strand.")
        cid = sel["id"]
        sp = STATE.cached(("splits", cid), lambda c: metrics.campaign_splits(c, cid))
        if not sp:
            return empty("No campaign for this character.")
        acts = {a["act"]: a for a in sp["acts"]}
        cur = sp["current_act"]
        rt = sp["rates"]

        def rate(v):
            return "–" if v is None else fmt.num(v, 1)
        tab = STATE.pref("campaign_tab", "splits")

        def tab_changed(e):
            STATE.set_pref("campaign_tab", e.value)
        with ui.tabs(value=tab, on_change=tab_changed).props(
                "dense align=left active-color=primary indicator-color=primary").classes("text-grey-5") as tabs:
            ui.tab("splits", "Progress")
            ui.tab("zones", "Acts")
            ui.tab("checklist", "Checklist")
        holder["tabs"] = tabs
        with ui.tab_panels(tabs, value=tab).classes("w-full bg-transparent").props("animated=false"):
            with ui.tab_panel("splits").classes("q-pa-none"):
                with ui.column().classes("w-full gap-4"):
                    lgo = next((l for l in STATE.cfg.leagues if l.name == lg), None)
                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc)
                    if lgo:
                        lg_start = lgo.start.strftime("%Y-%m-%dT%H:%M:%SZ")
                        ended = lgo.end and lgo.end <= now
                        age = ((lgo.end if ended else now) - lgo.start).total_seconds()
                        age_txt = (f"Ran {age / 86400:.0f} days" if ended else
                                   f"Running for {int(age // 86400)}d {int(age % 86400 // 3600)}h")
                    else:
                        lg_start, age_txt = None, ""
                    after = sp["after_league_start_s"]
                    with ui.element("div").classes("pt-kpi w-full"):
                        with ui.row().classes("w-full items-center gap-6").style("row-gap:12px"):
                            with ui.column().classes("gap-0").style("flex:1 1 280px"):
                                ui.label("League").classes("k")
                                ui.label(lg or "–").classes("pt-ls-name").style("font-size:30px;font-weight:700;line-height:1.15")
                                ui.label(f"Launched {fmt.when(lg_start)}" + (f" · {age_txt}" if age_txt else "")).classes("pt-note").style("font-size:14px")
                            with ui.column().classes("gap-0").style("flex:0 1 auto"):
                                ui.label("You Started").classes("k")
                                ui.label(fmt.when(sp["start"])).style("font-size:24px;font-weight:700;line-height:1.2")
                                ui.label(f"+{fmt.dur(after, True)} after launch · {sp['character']}" if after is not None
                                         else sp["character"] or "").classes("pt-note").style("font-size:14px")
                    kpis([
                        ("Zones per Hour", rate(rt["zones_per_h"]), f"{rt['zones']} zones entered"),
                        ("Acts per Hour", rate(rt["acts_per_h"]), f"{rt['acts_done']} of 10 acts done"),
                        ("Levels per Hour", rate(rt["levels_per_h"]), f"level {sp['level_end']}"),
                        ("Deaths per Hour", rate(rt["deaths_per_h"]), f"{sp['deaths']} deaths"),
                    ], columns=4)

                    # ---- progress: one equal block per act, filled by how far into it you are
                    with card("Campaign Progress"):
                        pct = sp["progress"]
                        status = ("Campaign complete" if sp["completed"] else
                                  f"Act {cur} · {sp['current_zone'] or ''}")
                        ui.html(
                            f'<div style="display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:10px">'
                            f'<span style="font-size:34px;font-weight:700;font-variant-numeric:tabular-nums">{fmt.clock(sp["play_s"])}</span>'
                            f'<span style="font-size:20px;color:var(--ex-gold, #d9a441);font-weight:600">{pct * 100:.0f}%</span>'
                            f'<span class="pt-note" style="font-size:14px">{status}</span></div>').classes("w-full")
                        # One bar for both: acts you haven't finished share the width equally;
                        # each finished act resizes to the time it took (relative to your
                        # average act), so a finished campaign shows time per act.
                        done_t = [a["time_s"] for a in sp["acts"] if a["finished"] and a["time_s"]]
                        ref = (sum(done_t) / len(done_t)) if done_t else 1.0
                        segs = ""
                        for n in range(1, 11):
                            a = acts.get(n)
                            if a and a["finished"]:
                                grow, fill, bg = max(a["time_s"] / ref, 0.45), 1.0, "var(--ex-gold, #d9a441)"
                                sub, tip = fmt.dur(a["time_s"], True), f"Act {n}: {fmt.clock(a['time_s'])}"
                            elif a:
                                grow, fill, bg = max((a["time_s"] or 0) / ref, 1.0) if done_t else 1.0, a["progress"], "var(--ex-cur, #4fb3a5)"
                                sub, tip = f"{a['progress'] * 100:.0f}%", f"Act {n}: in progress, {a['progress'] * 100:.0f}% of zones"
                            else:
                                grow, fill, bg = 1.0, 0.0, "#4fb3a5"
                                sub, tip = "", f"Act {n}: not started"
                            text_c = "#14110f" if fill >= 0.5 else "#a69b8c"
                            clip = "white-space:nowrap;overflow:hidden;text-overflow:clip;"
                            segs += (f'<a href="#act-zones-{n}" title="{tip} · click for its zones" style="text-decoration:none;'
                                     f'flex:{grow:.4f} 1 0;min-width:0;display:block;cursor:pointer"><div style="position:relative;height:44px;'
                                     f'background:#2d2722;border-radius:5px;overflow:hidden;'
                                     f'{"" if fill else "outline:1px dashed #4a4038;outline-offset:-1px;"}">'
                                     f'<div style="position:absolute;inset:0;width:{fill * 100:.1f}%;background:{bg}"></div>'
                                     f'<div style="position:relative;display:flex;flex-direction:column;justify-content:center;'
                                     f'align-items:center;height:100%;padding:0 3px;color:{text_c}">'
                                     f'<span style="font-size:13px;font-weight:700;line-height:1.1;{clip}">{n}</span>'
                                     f'<span style="font-size:10.5px;font-weight:600;line-height:1.2;opacity:.85;{clip}">{sub}</span>'
                                     f'</div></div></a>')
                        ui.html(f'<div class="pt-actbar" style="display:flex;gap:4px;width:100%;margin-bottom:6px">{segs}</div>').classes("w-full")
                        note("Acts you haven't finished share the bar equally. As you finish one, it fills in and takes the width "
                             "of the time it took, so the finished bar shows where your time went. The act you're in fills up "
                             "as you enter its zones. Click an act to open its zones.")

                    # ---- act splits
                    with card("Act Splits"):
                        rows = []
                        for n in range(1, 11):
                            a = acts.get(n)
                            if not a:
                                rows.append({"act": n, "start_split": None, "split": None, "time_s": None, "levels": "–", "deaths": None,
                                             "zone_count": None, "town_s": None, "end_utc": None, "_state": "pending"})
                                continue
                            rows.append({**a, "levels": f"{a['level_start']} → {a['level_end']}",
                                         "_state": "done" if a["finished"] else "running"})
                        table([
                            {"name": "act", "label": "Act", "fmt": lambda v, r: f"Act {v}"},
                            {"name": "start_split", "label": "Timer at Start", "num": True,
                             "fmt": lambda v, r: fmt.clock(v) if v is not None else "–"},
                            {"name": "split", "label": "Timer at Finish", "num": True,
                             "fmt": lambda v, r: fmt.clock(v) if r["_state"] == "done" else ("running" if r["_state"] == "running" else "–")},
                            {"name": "time_s", "label": "Time in Act", "num": True, "fmt": lambda v, r: fmt.clock(v) if v is not None else "–"},
                            {"name": "levels", "label": "Level", "num": True, "sortable": False},
                            {"name": "deaths", "label": "Deaths", "num": True, "fmt": lambda v, r: "–" if v is None else str(v)},
                            {"name": "zone_count", "label": "Zones", "num": True, "fmt": lambda v, r: "–" if v is None else str(v)},
                            {"name": "town_s", "label": "Town Time", "num": True, "fmt": lambda v, r: fmt.dur(v) if v is not None else "–"},
                            {"name": "end_utc", "label": "Finished On", "fmt": lambda v, r: fmt.when(v) if v else
                             ("In progress" if r["_state"] == "running" else "–")},
                        ], rows, page_size=10)
                        note("The timer is your campaign play time: it starts when you enter The Twilight Strand and leaves out AFK. "
                             "Timer at Start/Finish is where it stood when the act began and ended; Time in Act is the difference.")


            with ui.tab_panel("checklist").classes("q-pa-none"):
                with ui.column().classes("w-full gap-4"):
                    # ---- passive points from quests
                    qp = sp["passives"]
                    with card(f"Quest Passive Points · {qp['got']} of {qp['total']}"):
                        mark = {"done": "✓", "missed": "Missed", "maybe": "?", "pending": "–", "helped": "–"}
                        qrows = [{**q, "act_n": q["act"]} for q in qp["quests"]]
                        table([
                            {"name": "act_n", "label": "Act", "fmt": lambda v, r: f"Act {v}"},
                            {"name": "quest", "label": "Quest", "sortable": False},
                            {"name": "how", "label": "What to Do", "sortable": False},
                            {"name": "town", "label": "Reward In", "sortable": False, "opt": True},
                            {"name": "points", "label": "Points", "num": True},
                            {"name": "status", "label": "Got", "sortable": False, "align": "center",
                             "fmt": lambda v, r: r.get("helped") if v == "helped" else mark[v]},
                        ], qrows, page_size=len(qrows))
                        missed = [q for q in qp["quests"] if q["status"] == "missed"]
                        unsure = [q for q in qp["quests"] if q["status"] == "maybe"]
                        parts = [f"{qp['in_campaign']} of these points came during the campaign."]
                        if qp.get("helped"):
                            parts.append(f"You helped {qp['helped']['bandit']} ({qp['helped']['reward']}) instead of taking the "
                                         f"bandit point, so {qp['total']} points were available.")
                        if missed:
                            parts.append("Missed: " + ", ".join(q["quest"] for q in missed) + ".")
                        if unsure:
                            parts.append("? = that town gave fewer points than it has quests, so one of these is missing: "
                                         + " / ".join(q["quest"] for q in unsure) + ". Type /passives in game and the tracker will "
                                         "read exactly which.")
                        parts.append(f"Confirmed with /passives on {fmt.when(qp['report_utc'])}." if qp["report_utc"] else
                                     "Worked out from the points each town's quest givers handed you; type /passives in game to confirm.")
                        note(" ".join(parts))

                    # ---- bosses
                    with card("Campaign Bosses"):
                        brows = [{**b, "zone": b["zone"] or "–"} for b in sp["bosses"]]
                        table([
                            {"name": "act", "label": "Act", "fmt": lambda v, r: f"Act {v}"},
                            {"name": "boss", "label": "Boss", "sortable": False},
                            {"name": "zone", "label": "Zone", "sortable": False},
                            {"name": "done", "label": "Defeated", "sortable": False, "align": "center",
                             "fmt": lambda v, r: "✓" if v else ("not yet" if r["entered"] else "–")},
                            {"name": "split", "label": "Timer at Kill", "num": True, "fmt": lambda v, r: fmt.clock(v) if v is not None else "–"},
                            {"name": "level", "label": "Level", "num": True, "fmt": lambda v, r: "–" if v is None else str(v)},
                            {"name": "deaths", "label": "Deaths", "num": True, "fmt": lambda v, r: "–" if v is None else str(v)},
                        ], brows, page_size=len(brows))
                        note("Bosses you must kill to move on. One counts as defeated when you reach the zone it blocks; the timer is "
                             "when you got there. Optional bosses (Fairgraves, the Weaver, Abberath…) leave no trace in the log.")

                    # ---- trials
                    with card("Trials of Ascendancy"):
                        labs = {l["lab"].split()[0]: l for l in sp["labs"]}
                        trows = []
                        for t in sp["trials"]:
                            trows.append({**t, "lab_done": labs.get(t["lab"], {}).get("done")})
                        table([
                            {"name": "lab", "label": "Labyrinth", "sortable": False},
                            {"name": "act", "label": "Act", "fmt": lambda v, r: f"Act {v}"},
                            {"name": "zone", "label": "Zone", "sortable": False},
                            {"name": "done", "label": "Status", "sortable": False,
                             "fmt": lambda v, r: "✓ Completed" if v else ("Not completed" if r["entered"] else "–")},
                            {"name": "split", "label": "Timer at Completion", "num": True,
                             "fmt": lambda v, r: fmt.clock(v) if v is not None else ("after the campaign" if r["after_campaign"] else "–")},
                            {"name": "level", "label": "Level", "num": True, "fmt": lambda v, r: "–" if v is None else str(v)},
                        ], trows, page_size=len(trows))
                        note("A trial counts as completed when Izaro speaks after you finish it (needs Output Dialogue To Chat).")


            with ui.tab_panel("zones").classes("q-pa-none"):
                with ui.column().classes("w-full gap-4"):
                    # ---- zones, always open
                    with card("Zones"):
                        for a in sp["acts"]:
                            title = (f"Act {a['act']} · {fmt.clock(a['time_s'])} · level {a['level_start']} → {a['level_end']} · "
                                     f"{a['deaths']} death{'s' if a['deaths'] != 1 else ''}" + ("" if a["finished"] else " · in progress"))
                            ui.label(title).classes("text-weight-bold q-mt-md pt-zone-head").style("color:var(--ex-gold, #d9a441);scroll-margin-top:90px").props(
                                f'id=act-zones-{a["act"]}')
                            rows = [{**z, "levels": f"{z['level_in']} → {z['level_out']}",
                                     "zone": z["zone"] + (f"  (Act {z['zone_act']})" if z["zone_act"] and z["zone_act"] != a["act"] else "")}
                                    for z in a["zones"]]
                            table([
                                {"name": "zone", "label": "Zone", "sortable": False},
                                {"name": "entered", "label": "Timer at Entry", "num": True, "sortable": False,
                                 "fmt": lambda v, r: fmt.clock(v) if v is not None else ""},
                                {"name": "time_s", "label": "Time in Zone", "num": True, "sortable": False,
                                 "fmt": lambda v, r: fmt.dur(v) if v is not None else "–"},
                                {"name": "levels", "label": "Level In → Out", "num": True, "sortable": False},
                                {"name": "deaths", "label": "Deaths", "num": True, "sortable": False, "fmt": lambda v, r: "" if v is None else str(v)},
                                {"name": "visits", "label": "Visits", "num": True, "sortable": False, "fmt": lambda v, r: "" if v is None else str(v)},
                            ], rows, page_size=len(rows))
                        note("Zones in the order you first entered them. Time in Zone adds up every visit during that act; "
                             "a zone from an earlier act shows the act it belongs to. Visits above 1 mean you went back.")


    holder: dict = {}

    def act_jump(e):
        n = int(str(e.args).strip('[]"\' '))
        if holder.get("tabs"):
            holder["tabs"].set_value("zones")
        ui.run_javascript(f'setTimeout(() => document.getElementById("act-zones-{n}")'
                          f'?.scrollIntoView({{behavior: "smooth"}}), 200)')
    ui.on("act_jump", act_jump)
    ui.add_body_html("""<script>
document.addEventListener("click", (e) => {
  const a = e.target.closest(".pt-actbar a");
  if (!a) return;
  e.preventDefault();
  emitEvent("act_jump", a.getAttribute("href").split("-").pop());
});
</script>""")

    with body:
        content()
    auto_refresh(content.refresh)


MS_COLS = [
    {"name": "done", "label": "", "sortable": False,
     "fmt": lambda v, r: ("✓?" if r.get("likely") else "✓") if v else "○"},
    {"name": "name", "label": "Milestone", "sortable": False,
     "fmt": lambda v, r: v + (f" · {r['detail']}" if r.get("detail") else "")},
    {"name": "ts_utc", "label": "Reached", "sortable": False, "fmt": lambda v, r: fmt.when(v)},
    {"name": "days", "label": "League Day", "num": True, "sortable": False,
     "fmt": lambda v, r: f"Day {int(v) + 1}" if v is not None and r["done"] else "–"},
    {"name": "played_s", "label": "Play Time", "num": True, "sortable": False,
     "fmt": lambda v, r: fmt.dur(v, True) if r["done"] else "–"},
    {"name": "character", "label": "Character", "sortable": False, "opt": True, "fmt": lambda v, r: v or ""},
    {"name": "level", "label": "Level", "num": True, "sortable": False, "fmt": lambda v, r: "" if v is None else str(v)},
]
BOSS_COLS = MS_COLS + [
    {"name": "attempts", "label": "Attempts", "num": True, "sortable": False, "fmt": lambda v, r: "" if v is None else str(v)},
    {"name": "deaths", "label": "Deaths", "num": True, "sortable": False, "fmt": lambda v, r: "" if v is None else str(v)},
]


@ui.page("/mapping")
def mapping_page():
    if (r := locked("/mapping")):
        return r
    ls = league_start()
    live = ls["phase"] == "mapping"
    lg = ls["league"] if live else STATE.league()
    lock = STATE.cached(("mapping_lock", lg), lambda c: metrics.mapping_lock(c, lg)) if lg else {"id": None}
    who = (f"{lock['name']} · first to run a T16 map" if lock.get("t16") else
           f"{lock['name']} · highest tier so far (first to a T16 map takes this)") if lock.get("id") else ""
    body = frame("/mapping", "League Start Mapping", " · ".join(x for x in (lg, who) if x),
                 None if live else (lambda: league_select(_reload)))

    @ui.refreshable
    def content():
        if not lg:
            return _no_data()
        m = STATE.cached(("mapping", lg), lambda c: metrics.mapping_progress(c, STATE.cfg, lg))
        k = m["kpis"]
        if not k:
            return empty("No characters in this league yet.")
        kpis([
            ("Voidstones", f"{k['voidstones']} of {k['voidstones_total']}", f"bosses killed by {m['character']}"),
            ("Highest Tier", fmt.tier(k["top_tier"]) if k["top_tier"] else "–"),
            ("Maps Ran", fmt.num(k["maps"]), f"{fmt.num(k['map_deaths'])} deaths in maps"),
            ("Time Mapping", fmt.dur(k["mapping_played_s"], True) if k["mapping_played_s"] is not None else "–",
             "play time since the campaign"),
            ("Level", fmt.num(k["level"])),
            ("League Day", f"Day {int(k['days']) + 1}" if k["days"] is not None else "–",
             f"{fmt.dur(k['played_s'], True)} played"),
        ], columns=6)

        nxt = [x for x in m["milestones"] if not x["done"] and not x.get("voidstone")][:4]
        if nxt:
            with card("Next Up"):
                with ui.element("div").classes("w-full").style(
                        "display:grid; gap:12px; grid-template-columns:repeat(auto-fill, minmax(max(200px, calc((100% - 36px) / 4)), 1fr))"):
                    for x in nxt:
                        with ui.element("div").classes("pt-kpi"):
                            ui.label(x["group"]).classes("k")
                            ui.label(x["name"]).classes("text-weight-bold").style("font-size:15px")
                            if x.get("attempts"):
                                ui.label(f"{x['attempts']} attempt{'s' if x['attempts'] != 1 else ''} so far").classes("pt-note")

        with card("Tier Progression"):
            table([
                {"name": "tier", "label": "Tier", "fmt": lambda v, r: fmt.tier(v)},
                {"name": "first_map", "label": "First Map", "fmt": lambda v, r: v or "–"},
                {"name": "days", "label": "League Day", "num": True, "fmt": lambda v, r: f"Day {int(v) + 1}" if r["done"] else "–"},
                {"name": "played_s", "label": "Play Time", "num": True, "fmt": lambda v, r: fmt.dur(v, True) if r["done"] else "–"},
                {"name": "level", "label": "Level", "num": True, "fmt": lambda v, r: "" if v is None else str(v)},
                {"name": "maps", "label": "Maps Ran", "num": True},
                {"name": "avg_s", "label": "Average Map", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                {"name": "fastest_s", "label": "Fastest", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                {"name": "deaths", "label": "Deaths", "num": True},
            ], m["tiers"], page_size=len(m["tiers"]))
            note(f"League Day and Play Time show when {m['character'] or 'the character'} first ran a map of that tier. "
                 "Play time is that character's, AFK left out. Every number on this page is for that character only.")

        groups_atlas = [x for x in m["milestones"] if x["group"] == "Atlas"]
        groups_char = [x for x in m["milestones"] if x["group"] in ("Character", "Labyrinth")]
        bosses = [x for x in m["milestones"] if x["group"] not in ("Atlas", "Character", "Labyrinth")]
        with card("Atlas Progression"):
            table(MS_COLS, groups_atlas, page_size=len(groups_atlas))
        with card("Character and Labyrinth"):
            table(BOSS_COLS, groups_char, page_size=len(groups_char))
        with card("Pinnacle Bosses and Voidstones"):
            rows = [{**x, "name": x["name"] if x.get("voidstone") else f"{x['group'].split()[0]} · {x['name']}"} for x in bosses]
            table(BOSS_COLS, rows, page_size=len(rows))
            note("✓ = defeat line in the log. ✓? = the fight has no defeat line, so leaving the arena alive counts. "
                 "Bosses and lines are in milestones.yaml.")

    with body:
        content()
    auto_refresh(content.refresh)

# ====================================================================== Characters
@ui.page("/character")
def character_page():
    if (r := locked("/character")):
        return r
    lg = STATE.league()
    body = frame("/character", "Characters", lg or "", lambda: league_select(_reload))
    chars = STATE.characters(lg)
    sel = {"id": STATE.pref("character_page")}
    if sel["id"] not in [c["id"] for c in chars]:
        sel["id"] = chars[0]["id"] if chars else None

    @ui.refreshable
    def picker():
        with ui.row().classes("w-full gap-3"):
            for c in chars:
                active = c["id"] == sel["id"]
                with ui.element("div").classes("pt-kpi cursor-pointer").style(
                        "flex:0 0 auto; min-width:190px;" + ("border-color:#d9a441;" if active else "")).on(
                        "click", lambda _, cid=c["id"]: choose(cid)):
                    ui.label(c["name"]).classes("text-weight-bold" + (" text-primary" if active else ""))
                    ui.label(f"{c['class'] or ''} · level {c['level'] or '?'}").classes("pt-note")
                    ui.label(f"{fmt.dur(c['active_s'], True)} played · {c['maps']} maps").classes("pt-note")

    def choose(cid):
        sel["id"] = cid
        STATE.set_pref("character_page", cid)
        picker.refresh()
        detail.refresh()

    @ui.refreshable
    def detail():
        cid = sel["id"]
        if not cid:
            return empty("No characters in this league yet.")
        d = STATE.cached(("character", cid), lambda c: {**metrics.character_detail(c, cid), "campaign": metrics.campaign_for(c, cid)})
        ch = d["character"]
        ui.label(f"{ch['name']} · {ch['class'] or ''} · level {ch['level'] or '?'} · first seen {fmt.date(ch['first_seen'])}").classes("pt-h2 q-mt-sm")
        cp = d["campaign"]
        kpis([
            ("Level", str(ch["level"] or "–")),
            ("Played", fmt.hours(d["total_active_s"])),
            ("Campaign", fmt.dur(cp["active_s"], True) if cp else "–",
             ("completed" if cp["completed"] else "in progress") if cp else "not in log"),
            ("Deaths", fmt.num(d["death_count"])),
            ("Passive changes", fmt.num(d["tree"]["change_count"]), f"{d['tree']['count']} points known now"),
        ])
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            with card("Level by play time", "flex-[3]"):
                lv = d["levels"]
                if lv:
                    ch_ = chart(None, [{"name": "Level", "type": "line", "color": GOLD,
                                        "data": [[round(x["played_s"] / 3600, 2), x["level"]] for x in lv]}],
                                kind="line", y_min=1, y_max=100, height=240, x_name="hours played")
                    ch_.options["xAxis"]["axisLabel"][":formatter"] = "v => v + 'h'"
                    ch_.options["tooltip"][":formatter"] = "p => 'Level ' + p[0].value[1] + ' after ' + p[0].value[0] + 'h played'"
                else:
                    empty("No level-ups logged.")
            with card("Playtime per day", "flex-[2]"):
                days = d["daily"][-45:]
                chart([fmt.day_label(x["day"]) for x in days],
                      [{"name": "Played", "data": [round(x["active_s"] / 3600, 2) for x in days], "color": TEAL}],
                      y="h", tooltip_fmt=HOURS_TIP, height=240)
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            with card("Deaths", "flex-1"):
                if d["death_by_kind"]:
                    ui.html(" ".join(f'<span class="pt-badge">{KIND.get(k, k)}: {v}</span>' for k, v in d["death_by_kind"].items()))
                table([
                    {"name": "ts_utc", "label": "When", "fmt": lambda v, r: fmt.when(v)},
                    {"name": "area_name", "label": "Where"},
                    {"name": "kind", "label": "Kind", "fmt": lambda v, r: KIND.get(v, v or "")},
                    {"name": "area_level", "label": "Area level", "num": True},
                ], d["deaths"], page_size=10, empty_text="No deaths. Nice.")
            with card("Passive tree changes", "flex-1"):
                table([
                    {"name": "ts_utc", "label": "When", "fmt": lambda v, r: fmt.when(v)},
                    {"name": "action", "label": "", "fmt": lambda v, r: "+" if v == "allocated" else "−"},
                    {"name": "name", "label": "Node"},
                ], d["tree"]["changes"], page_size=10, empty_text="No passive changes logged.")
                note("Only points changed while the log was recording are known.")
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            with card("Allocated notables & keystones (known)", "flex-1"):
                import re
                table([{"name": "name", "label": "Node"}, {"name": "count", "label": "Count", "num": True}],
                      [x for x in d["tree"]["by_name"] if not re.match(r"^(Strength|Dexterity|Intelligence|\+\d+ to )", x["name"] or "")],
                      page_size=10)
            with card("Masteries", "flex-1"):
                table([{"name": "name", "label": "Mastery"},
                       {"name": "since", "label": "Since", "fmt": lambda v, r: fmt.when(v)}],
                      d["masteries"]["allocated"], page_size=10, empty_text="None logged.")

    with body:
        if not chars:
            empty("No characters in this league yet.")
        else:
            picker()
            detail()
    auto_refresh(detail.refresh)


# ====================================================================== Atlas
@ui.page("/atlas")
def atlas_page():
    if (r := locked("/atlas")):
        return r
    lg = STATE.league()
    body = frame("/atlas", "Atlas tree", lg or "", lambda: league_select(_reload))

    @ui.refreshable
    def content():
        if not lg:
            return _no_data()
        d = STATE.cached(("atlas", lg), lambda c: metrics.atlas(c, STATE.cfg, lg))
        t = d["tree"]
        kpis([
            ("Points allocated (known)", fmt.num(t["count"])),
            ("Changes logged", fmt.num(t["change_count"])),
            ("Tree versions mapped with", fmt.num(len([v for v in d["versions"] if v["atlas_hash"] != "-"]))),
        ])
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            with card("Points by mechanic", "flex-1"):
                table([{"name": "group", "label": "Group", "fmt": lambda v, r: (v or "").capitalize()},
                       {"name": "count", "label": "Points", "num": True}], t["groups"], page_size=12)
            with card("Allocated nodes", "flex-1"):
                table([{"name": "name", "label": "Node"}, {"name": "count", "label": "Count", "num": True}],
                      t["by_name"], page_size=12)
            with card("Recent changes", "flex-1"):
                table([{"name": "ts_utc", "label": "When", "fmt": lambda v, r: fmt.when(v)},
                       {"name": "action", "label": "", "fmt": lambda v, r: "+" if v == "allocated" else "−"},
                       {"name": "name", "label": "Node"}], t["changes"], page_size=12)
        with card("Maps by atlas tree version"):
            table([
                {"name": "first", "label": "From", "fmt": lambda v, r: fmt.when(v)},
                {"name": "last", "label": "To", "fmt": lambda v, r: fmt.when(v)},
                {"name": "atlas_hash", "label": "Version"},
                {"name": "runs", "label": "Maps Ran", "num": True},
                {"name": "avg_active_s", "label": "Avg time", "num": True, "fmt": lambda v, r: fmt.dur(v)},
                {"name": "maps_per_hour", "label": "Maps/hour", "num": True, "fmt": lambda v, r: fmt.num(v, 1)},
                {"name": "avg_tier", "label": "Avg tier", "num": True, "fmt": lambda v, r: fmt.num(v, 1)},
                {"name": "deaths", "label": "Deaths", "num": True},
            ], list(reversed(d["versions"])), page_size=12)
            note("A new version starts whenever an atlas point changes. \"-\" means no atlas points were known yet.")

    with body:
        content()
    auto_refresh(content.refresh)


# ====================================================================== Currency
DEFAULT_ITEMS = ["Divine Orb", "Chaos Orb", "Exalted Orb", "Orb of Annulment", "Mirror Shard"]


@ui.page("/currency")
def currency_page():
    if (r := locked("/currency")):
        return r
    lg = STATE.league()
    body = frame("/currency", "Currency", lg or "", lambda: league_select(_reload))

    @ui.refreshable
    def content():
        d = STATE.cached(("currency", lg), lambda c: metrics.currency(c, lg))
        snaps = d["snapshots"]
        last = snaps[0] if snaps else None
        kpis([
            ("Latest total", f"{fmt.num(last['total_divine'], 1)} div" if last and last["total_divine"] else "–",
             f"{fmt.num(last['total_chaos'])} chaos · {fmt.when(last['ts_utc'])}" if last else "add a snapshot below"),
            ("Change since previous", (f"{'+' if last['delta_chaos'] >= 0 else ''}{fmt.num(last['delta_chaos'])} c"
                                       if last and last.get("delta_chaos") is not None else "–"),
             f"over {fmt.dur(last['played_s'], True)} played" if last and last.get("played_s") else ""),
            ("Per hour played", f"{fmt.num(last['chaos_per_hour'])} c/h" if last and last.get("chaos_per_hour") is not None else "–"),
        ])
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            with card("New snapshot", "flex-1"):
                items = [i["item"] for i in last["items"]] if last else DEFAULT_ITEMS
                prices = {i["item"]: i["chaos_each"] for i in last["items"]} if last else {}
                with ui.row().classes("gap-3"):
                    div = ui.number("Divine price (chaos)", value=last["divine_chaos"] if last else None).props("outlined dense dark")
                    note_in = ui.input("Note").props("outlined dense dark").classes("flex-1")
                rows_box = ui.column().classes("w-full gap-1 q-mt-sm")
                entries = []

                def add_row(name="", price=None):
                    with rows_box:
                        with ui.row().classes("w-full gap-2 no-wrap items-center") as r:
                            n = ui.input("Item", value=name).props("outlined dense dark").classes("flex-[2]")
                            q = ui.number("Amount").props("outlined dense dark").classes("flex-1")
                            p = ui.number("Chaos each", value=price).props("outlined dense dark").classes("flex-1").tooltip(
                                "Leave empty for Chaos Orb and Divine Orb")
                            e = (n, q, p, r)
                            ui.button(icon="close", on_click=lambda e=e: (entries.remove(e), e[3].delete())).props("flat dense round")
                    entries.append(e)
                for it in items:
                    add_row(it, prices.get(it))

                def save():
                    data = [{"item": (n.value or "").strip(), "qty": q.value, "chaos_each": p.value} for n, q, p, _ in entries]
                    data = [x for x in data if x["item"] and x["qty"] is not None]
                    if not data:
                        ui.notify("Enter at least one amount.", type="warning")
                        return
                    lgc = STATE.character(lg)
                    char = next((c["name"] for c in STATE.characters(lg) if c["id"] == lgc), STATE.cfg.settings.get("current_character"))
                    con = db.connect()
                    try:
                        metrics.add_currency_snapshot(con, {"league": lg, "character": char, "divine_chaos": div.value,
                                                            "note": note_in.value, "items": data})
                    finally:
                        con.close()
                    STATE.invalidate()
                    ui.notify("Snapshot saved.", type="positive")
                    content.refresh()

                with ui.row().classes("w-full q-mt-sm"):
                    ui.button("Add item", icon="add", on_click=lambda: add_row()).props("flat dense")
                    ui.space()
                    ui.button("Save snapshot", on_click=save).props("unelevated")
                note("Count what you have (stash + inventory). Saved with the current time and league.")
            with card("Total over time (divines)", "flex-1"):
                pts = [s for s in reversed(snaps) if s["total_divine"] is not None]
                if len(pts) >= 1:
                    chart([fmt.when(s["ts_utc"]) for s in pts],
                          [{"name": "Divines", "type": "line", "data": [round(s["total_divine"], 1) for s in pts], "color": GOLD}],
                          kind="line", height=260)
                else:
                    empty("Add a snapshot with a divine price to see this.")
        with card("Snapshots"):
            def delete(row):
                con = db.connect()
                try:
                    con.execute("DELETE FROM currency_snapshot_item WHERE snapshot_id=?", (row["_id"],))
                    con.execute("DELETE FROM currency_snapshot WHERE id=?", (row["_id"],))
                    con.commit()
                finally:
                    con.close()
                STATE.invalidate()
                content.refresh()
            rows = [{**s, "_id": s["id"]} for s in snaps]
            t = table([
                {"name": "ts_utc", "label": "When", "fmt": lambda v, r: fmt.when(v)},
                {"name": "total_chaos", "label": "Total (c)", "num": True, "fmt": lambda v, r: fmt.num(v)},
                {"name": "total_divine", "label": "Total (div)", "num": True, "fmt": lambda v, r: fmt.num(v, 1)},
                {"name": "delta_chaos", "label": "Change (c)", "num": True,
                 "fmt": lambda v, r: "–" if v is None else f"{'+' if v >= 0 else ''}{fmt.num(v)}"},
                {"name": "played_s", "label": "Played between", "num": True, "fmt": lambda v, r: fmt.dur(v, True) if v else "–"},
                {"name": "chaos_per_hour", "label": "c/hour", "num": True, "fmt": lambda v, r: fmt.num(v)},
                {"name": "character", "label": "Character"},
                {"name": "note", "label": "Note"},
            ], rows, empty_text="No snapshots yet.")
            if t:
                note("Click a snapshot to delete it.")
                t.on("rowClick", lambda e: confirm_delete(e.args[1]))

            def confirm_delete(row):
                with ui.dialog() as dlg, ui.card():
                    ui.label(f"Delete the snapshot from {fmt.when(row['ts_utc'])}?")
                    with ui.row():
                        ui.button("Cancel", on_click=dlg.close).props("flat")
                        ui.button("Delete", color="negative", on_click=lambda: (dlg.close(), delete(row)))
                dlg.open()

    with body:
        content()


# ====================================================================== Trades
@ui.page("/trades")
def trades_page():
    if (r := locked("/trades")):
        return r
    lg = STATE.league()
    body = frame("/trades", "Trades", lg or "", lambda: league_select(_reload))

    @ui.refreshable
    def content():
        d = STATE.cached(("trades", lg), lambda c: metrics.trades(c, lg))
        c = d["counts"]
        kpis([("Offers received", fmt.num(c["incoming"]), "people wanting your items"),
              ("Offers sent", fmt.num(c["outgoing"])),
              ("Trades accepted", fmt.num(c["accepted"])), ("Trades cancelled", fmt.num(c["cancelled"]))])
        with card("Offers per day"):
            days = d["by_day"]
            if days:
                chart([fmt.day_label(x["day"]) for x in days],
                      [{"name": "Received", "data": [x["incoming"] for x in days], "color": GOLD},
                       {"name": "Sent", "data": [x["outgoing"] for x in days], "color": TEAL}], height=220)
            else:
                empty("No trade whispers in this league.")
        cols = [{"name": "ts_utc", "label": "When", "fmt": lambda v, r: fmt.when(v)},
                {"name": "who", "label": "Player"}, {"name": "item", "label": "Item"},
                {"name": "price_amount", "label": "Price", "num": True,
                 "fmt": lambda v, r: f"{fmt.num(v, 1)} {r.get('price_currency') or ''}"}]
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            with card("Most requested from you", "flex-1"):
                table([{"name": "item", "label": "Item"}, {"name": "count", "label": "Offers", "num": True}], d["top_sold"])
            with card("Most bought", "flex-1"):
                table([{"name": "item", "label": "Item"}, {"name": "count", "label": "Offers", "num": True}], d["top_bought"])
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            with card("Received offers", "flex-1"):
                table(cols, d["incoming"])
            with card("Sent offers", "flex-1"):
                table(cols, d["outgoing"])
        note(d["note"])

    with body:
        content()
    auto_refresh(content.refresh)


# ====================================================================== Standard
@ui.page("/standard")
def standard_page():
    lg = STATE.league()
    body = frame("/standard", "Standard", "Every league combined, and how one league compares with the rest",
                 lambda: league_select(_reload, label="Compare league"))

    @ui.refreshable
    def content():
        d = STATE.cached(("standard", lg), lambda c: metrics.standard(c, STATE.cfg, lg))
        rows, t = d["leagues"], d["totals"]
        if not rows:
            return _no_data()
        fc = t["fastest_campaign"]
        heading("All leagues")
        kpis([
            ("Hours played", fmt.num(t["active_s"] / 3600), f"since {fmt.date(t['first_play'])}"),
            ("Leagues", fmt.num(t["leagues"]), f"{t['characters']} characters"),
            ("Maps", fmt.num(t["maps"]), f"{fmt.num(t['maps_per_hour'], 1)} per hour in maps"),
            ("Deaths", fmt.num(t["deaths"])),
            ("Campaigns completed", fmt.num(t["campaigns"]), f"fastest {fmt.dur(fc[0], True)} · {fc[1]}" if fc else ""),
        ])
        kpis([
            ("Average hours per league", fmt.num(t["avg_hours_per_league"], 0)),
            ("Average mapping hours per league", fmt.num(t["avg_map_hours_per_league"], 0)),
            ("Average maps per league", fmt.num(t["avg_maps_per_league"], 0)),
            ("Average divines per league", fmt.num(t["avg_divines_per_league"], 1) if t["avg_divines_per_league"] is not None else "–",
             "from currency snapshots"),
            ("Highest level", fmt.num(t["max_level"])),
        ])

        if d["compare"]:
            heading(f"{lg} vs your other leagues", "q-mt-md")
            # headline sentences for the biggest differences
            notable = sorted([c for c in d["compare"] if c["diff"] is not None and c["better"] is not None],
                             key=lambda c: -abs(c["diff"]))[:4]
            with card():
                for c in notable:
                    good = (c["diff"] > 0) == bool(c["better"])
                    word = "more" if c["diff"] > 0 else "less"
                    if c["fmt"] == "dur":
                        word = "longer" if c["diff"] > 0 else "shorter"
                    rank = f" · rank #{c['rank']} of {c['of']}" if c["rank"] else ""
                    ui.html(f'<div style="margin:2px 0">{c["label"]}: <b class="{"pt-up" if good else "pt-down"}">'
                            f'{abs(c["diff"]) * 100:.0f}% {word}</b> than your average league '
                            f'(<b>{fmt.by_fmt(c["value"], c["fmt"])}</b> vs {fmt.by_fmt(c["others_avg"], c["fmt"])}){rank}</div>')
            with ui.grid(columns=4).classes("w-full gap-3"):
                for c in d["compare"]:
                    with ui.element("div").classes("pt-compare"):
                        ui.html(f'<div class="k">{c["label"]}</div><div class="v">{fmt.by_fmt(c["value"], c["fmt"])}</div>')
                        if c["others_avg"] is not None:
                            cls = ""
                            if c["diff"] and c["better"] is not None:
                                cls = "pt-up" if (c["diff"] > 0) == c["better"] else "pt-down"
                            ui.html(f'<div class="pt-note">others avg {fmt.by_fmt(c["others_avg"], c["fmt"])} · '
                                    f'<span class="{cls}">{fmt.signed_pct(c["diff"])}</span>'
                                    + (f' · #{c["rank"]} of {c["of"]}' if c["rank"] and c["better"] is not None else "") + "</div>")

        names = [r["name"] for r in reversed(rows)]

        def bars(key, scale=1.0, digits=1):
            data = []
            for r in reversed(rows):
                v = r.get(key)
                data.append({"value": round(v * scale, digits) if v is not None else None,
                             "itemStyle": {"color": GOLD if r["name"] == lg else "#5a5148"}})
            return [{"name": key, "data": data}]

        with ui.grid(columns=2).classes("w-full gap-4 q-mt-md"):
            for title, key, scale, digits, tip in [
                ("Hours played", "hours", 1, 1, HOURS_TIP), ("Maps run", "maps", 1, 0, None),
                ("Maps per hour (inside maps)", "maps_per_hour", 1, 1, None), ("Deaths per map", "deaths_per_map", 1, 2, None),
                ("Fastest campaign (hours)", "best_campaign_s", 1 / 3600, 1, HOURS_TIP), ("Hours per day played", "hours_per_day", 1, 1, HOURS_TIP),
            ]:
                with card(title):
                    chart([n.replace(" (event)", "") for n in names], bars(key, scale, digits), legend=False, height=230,
                          tooltip_fmt=tip, all_labels=True)

        pace = d["pace"]
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            for title, key, tip in [("Hours played by league day", "hours", HOURS_TIP), ("Maps by league day", "maps", None)]:
                with card(title, "flex-1"):
                    longest = max((len(v) for v in pace.values()), default=0)
                    series = []
                    for name, pts in pace.items():
                        focus = name == lg
                        series.append({"name": name, "type": "line", "data": [p[key] for p in pts],
                                       "color": GOLD if focus else "#5a5148", "width": 3 if focus else 1.5,
                                       "z": 10 if focus else 1, "symbols": False})
                    chart([str(i) for i in range(1, longest + 1)], series, kind="line", height=260, legend=False,
                          tooltip_fmt=tip, x_name="days since league start")
        note(f"Gold is {lg}; grey is your other leagues.")

        with card("Every league"):
            table([
                {"name": "name", "label": "League"},
                {"name": "start", "label": "Start", "opt": True, "fmt": lambda v, r: fmt.date(v)},
                {"name": "days_played", "label": "Days played", "num": True},
                {"name": "active_s", "label": "Hours", "num": True, "fmt": lambda v, r: fmt.num(v / 3600, 0)},
                {"name": "characters", "label": "Characters", "num": True, "opt": True},
                {"name": "top_character", "label": "Main", "opt": True},
                {"name": "max_level", "label": "Highest level", "num": True},
                {"name": "maps", "label": "Maps Ran", "num": True},
                {"name": "maps_per_hour", "label": "Maps/hour", "num": True, "opt": True, "fmt": lambda v, r: fmt.num(v, 1)},
                {"name": "max_tier", "label": "Highest tier", "num": True, "fmt": lambda v, r: fmt.tier(v)},
                {"name": "deaths", "label": "Deaths", "num": True},
                {"name": "best_campaign_s", "label": "Fastest campaign", "num": True, "wrap": True,
                 "fmt": lambda v, r: f"{fmt.dur(v, True)} ({r['best_campaign']['character']})" if v else "–"},
                {"name": "divines", "label": "Divines", "num": True, "opt": True, "fmt": lambda v, r: fmt.num(v, 1)},
            ], rows, page_size=20)
            note("League start dates come from leagues.yaml in your config folder. Add each new league there when it launches.")

    with body:
        content()
    auto_refresh(content.refresh)


# ====================================================================== Settings
@ui.page("/settings")
def settings_page():
    body = frame("/settings", "Settings", "Saved to settings.yaml in your config folder")
    from .. import paths
    s = STATE.cfg.settings
    with body:
        with ui.row().classes("w-full gap-4 items-start pt-wrap"):
            with card("Tracker", "flex-[3]"):
                log_in = ui.input("Client.txt path (empty = find automatically)", value=s.get("log_path") or "").props(
                    "outlined dense dark").classes("w-full")
                with ui.row().classes("w-full gap-3"):
                    tz = ui.input("Time zone", value=s.get("timezone")).props("outlined dense dark")
                    ch = ui.input("Main character", value=s.get("current_character") or "").props("outlined dense dark")
                    lgi = ui.select(STATE.league_names(), value=s.get("current_league") if s.get("current_league") in STATE.league_names() else None,
                                    label="Default league").props("outlined dense dark").style("min-width:220px")
                with ui.row().classes("w-full gap-3 items-center"):
                    win = ui.select({"native": "Own window", "browser": "Web browser"}, value=s.get("window", "native"),
                                    label="Open the dashboard in").props("outlined dense dark").style("min-width:200px")
                    capm = ui.number("Link detailed map within (min)", value=s.get("capture_link_minutes", 10)).props("outlined dense dark")
                    clip = ui.switch("Clipboard map capture", value=bool(s.get("clipboard_capture", True)))
                with ui.row().classes("w-full gap-3 items-center"):
                    def set_theme(e):
                        config_mod.save_settings({"theme": e.value})
                        STATE.cfg.settings["theme"] = e.value
                        _reload()
                    ui.select({"exile": "Exile (Path of Exile style)", "classic": "Classic"}, value=s.get("theme", "exile"),
                              label="Look", on_change=set_theme).props("outlined dense dark").style("min-width:240px")

                    def set_lc(e):
                        config_mod.save_settings({"league_colors": bool(e.value)})
                        STATE.cfg.settings["league_colors"] = bool(e.value)
                        _reload()
                    ui.switch("Colours per league", value=bool(s.get("league_colors", True)), on_change=set_lc).tooltip(
                        "Exile look only: each league gets its own accent colour. Change one with color: '#rrggbb' "
                        "on its line in leagues.yaml.")

                def save():
                    config_mod.save_settings({
                        "log_path": (log_in.value or "").strip(), "timezone": (tz.value or "").strip() or "America/Chicago",
                        "current_character": (ch.value or "").strip(), "current_league": lgi.value or "",
                        "window": win.value, "capture_link_minutes": int(capm.value or 10), "clipboard_capture": bool(clip.value),
                    })
                    ui.notify("Saved. Restart the tracker for changes to apply.", type="positive")
                with ui.row().classes("w-full"):
                    ui.space()
                    ui.button("Save", on_click=save).props("unelevated")
            with card("Status", "flex-[2]"):
                st = STATE.tracker.status() if STATE.tracker else {}
                for k, v in [
                    ("Client.txt", st.get("log_path") or "not found"),
                    ("Read", f"{(st.get('log_offset') or 0) / 1048576:,.1f} of {(st.get('log_size') or 0) / 1048576:,.1f} MB"),
                    ("Last in-game activity", f"{fmt.when(st.get('last_event_utc'))} ({fmt.ago(st.get('last_event_utc'))})"),
                    ("Clipboard capture", "running" if st.get("clipboard") else "off"),
                    ("Data folder", str(paths.data_dir())),
                    ("Config files", str(paths.config_dir())),
                ]:
                    with ui.row().classes("w-full no-wrap gap-2"):
                        ui.label(k).classes("pt-note").style("min-width:150px")
                        ui.label(v).classes("text-sm").style("word-break:break-all")
        with card("League Start"):
            ls = league_start()
            phase = ls.get("real_phase") or ls.get("phase")
            ui.label("From league launch until your first character finishes Act 10, only Overview, League Start Campaign, "
                     "Standard and Settings are shown. After that, League Start Mapping is added until you have all four "
                     "Voidstones, then every dashboard opens. Both League Start pages stay afterwards, with a league picker "
                     "for past leagues. This follows the newest league below that has started.").classes("pt-sub")
            cur = ls.get("league")
            status = {"campaign": "Campaign phase", "mapping": f"Mapping phase ({ls.get('voidstones')} of 4 Voidstones)",
                      "done": "League start finished"}.get(phase, "Off")
            if ls.get("off"):
                status = "Off"
            elif ls.get("unlocked"):
                status += " · all dashboards opened early"
            ui.label(f"{cur or 'No league has started'} · {status}").classes("q-mt-sm text-sm")
            if ls.get("campaign_name"):
                ui.label(f"League Start Campaign is locked to {ls['campaign_name']}"
                         + (f" · League Start Mapping is locked to {ls['mapping_name']}" if ls.get("mapping_name") else "")
                         + ". The first character to finish the campaign, and the first to run a T16 map.").classes("pt-note")

            def set_mode(e):
                config_mod.save_settings({"league_start_mode": bool(e.value)})
                STATE.cfg.settings["league_start_mode"] = bool(e.value)
                _reload()

            def unlock(on: bool):
                STATE.set_pref("ls_unlocked", cur if on else None)
                _reload()
            with ui.row().classes("items-center gap-4 q-mt-sm"):
                ui.switch("League start mode", value=bool(STATE.cfg.settings.get("league_start_mode", True)), on_change=set_mode)
                if not ls.get("off") and phase in ("campaign", "mapping"):
                    if ls.get("unlocked"):
                        ui.button("Lock again", on_click=lambda: unlock(False)).props("outline")
                    else:
                        ui.button(f"Open all dashboards for {cur}", on_click=lambda: unlock(True)).props("outline")

            ui.label("Add the next league before it launches so new characters land in it. Start time is your local time.").classes(
                "pt-sub q-mt-md")
            with ui.row().classes("items-end gap-3"):
                nm = ui.input("League name").props("outlined dense dark").style("min-width:220px")
                dt = ui.input("Start date", placeholder="2026-12-04").props("outlined dense dark")
                tm = ui.input("Start time", value="14:00").props("outlined dense dark").style("max-width:110px")

                def add():
                    from datetime import datetime
                    try:
                        local = datetime.strptime(f"{(dt.value or '').strip()} {(tm.value or '').strip()}", "%Y-%m-%d %H:%M")
                    except ValueError:
                        ui.notify("Date as YYYY-MM-DD and time as HH:MM, please.", type="warning")
                        return
                    if not (nm.value or "").strip():
                        ui.notify("Give the league a name.", type="warning")
                        return
                    config_mod.add_league(nm.value.strip(), local.replace(tzinfo=fmt.TZ))
                    import threading

                    def work():
                        STATE.tracker.reload_config()
                        STATE.cfg = STATE.tracker.cfg
                        STATE.invalidate()
                    threading.Thread(target=work, daemon=True).start()
                    ui.notify(f"Added {nm.value.strip()}. Rebuilding so characters are sorted into the right league.", type="positive")
                ui.button("Add league", on_click=add).props("unelevated")
            lgs = list(reversed(STATE.cfg.leagues))[:4]
            ui.label("Latest leagues: " + " · ".join(f"{l.name} ({fmt.date(l.start.strftime('%Y-%m-%dT%H:%M:%SZ'))})" for l in lgs)).classes(
                "pt-note q-mt-sm")
        with card("Updates"):
            from nicegui import run as ng_run
            upd = STATE.updater
            box = ui.column().classes("w-full gap-1")

            def draw_updates():
                st = upd.state if upd else {}
                box.clear()
                with box:
                    if not st.get("git"):
                        ui.label("Git isn't installed, so the tracker can't check for updates. Install Git for Windows "
                                 "(https://git-scm.com/download/win), then restart the tracker.").classes("pt-sub")
                        return
                    if not st.get("connected"):
                        ui.label("This folder isn't connected to GitHub yet (it came from a download). Connect it once "
                                 "and the tracker keeps itself up to date from github.com/deweesa1/poe-tracker. "
                                 "Files you added to the folder yourself are left alone.").classes("pt-sub")
                        return
                    import time as _t
                    checked = st.get("checked")
                    ui.label(f"Your version: {st.get('version') or '?'}").classes("text-sm")
                    line = ("Checking…" if not checked else
                            f"Last checked {int((_t.time() - checked) // 60)} min ago" if _t.time() - checked >= 60 else
                            "Last checked just now")
                    if st.get("error"):
                        line += f" · couldn't reach GitHub ({st['error']})"
                    elif checked:
                        line += f" · {st['behind']} update{'s' if st['behind'] != 1 else ''} waiting" if st.get(
                            "available") else " · you're up to date"
                    ui.label(line).classes("pt-note")

            async def check_now():
                ui.notify("Checking GitHub…")
                await ng_run.io_bound(upd.check)
                draw_updates()
                if upd.state.get("available"):
                    from .layout import update_dialog
                    update_dialog()

            async def connect():
                ui.notify("Connecting this folder to GitHub…")
                ok, text = await ng_run.io_bound(upd.connect)
                ui.notify(text, type="positive" if ok else "negative")
                await ng_run.io_bound(upd.check)
                draw_updates()

            def set_auto(e):
                config_mod.save_settings({"update_check": bool(e.value)})
                STATE.cfg.settings["update_check"] = bool(e.value)

            draw_updates()
            with ui.row().classes("items-center gap-3 q-mt-sm"):
                if upd and upd.state.get("git") and not upd.state.get("connected"):
                    ui.button("Connect to GitHub", icon="link", on_click=connect).props("unelevated")
                else:
                    ui.button("Check for updates", icon="sync", on_click=check_now).props("outline")
                ui.switch("Check automatically (every 30 min)", value=bool(s.get("update_check", True)), on_change=set_auto)
        with card("Rebuild"):
            ui.label("Recalculates everything from the raw lines already stored. Use it after editing areas.yaml or "
                     "log_patterns.yaml. \"Re-read Client.txt\" starts from the very beginning of the log file "
                     "(about 15 seconds per 200 MB). Detailed maps and currency snapshots are kept.").classes("pt-sub")

            def rebuild(from_log):
                import threading
                threading.Thread(target=STATE.tracker.rebuild, kwargs={"from_log": from_log}, daemon=True).start()
                STATE.invalidate()
                ui.notify("Rebuild started. The status at the top shows progress.")
            with ui.row().classes("q-mt-sm"):
                ui.button("Rebuild from stored lines", on_click=lambda: rebuild(False)).props("outline")
                ui.button("Re-read Client.txt", on_click=lambda: rebuild(True)).props("outline")
        with card("GGG API"):
            ui.label("Stash currency, gear, gems and the full passive tree need GGG's OAuth API. GGG isn't accepting new "
                     "developer applications right now, so this stays off. Everything else works from your log.").classes("pt-sub")
