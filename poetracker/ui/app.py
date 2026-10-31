"""Starting the NiceGUI dashboard, in its own window (default) or a browser."""
from __future__ import annotations

import logging

from nicegui import app, ui

from .. import config as config_mod, paths, service
from . import fmt
from .layout import STATE

log = logging.getLogger(__name__)


def run(window: str | None = None, port: int | None = None, dev: bool = False) -> None:
    service.setup_logging()
    STATE.dev = dev
    if not service.single_instance():
        log.warning("PoE Tracker is already running; not starting a second copy")
        msg = ("PoE Tracker is already running.\n\nIf you can't see its window, end the leftover "
               "'pythonw.exe' (Python) process in Task Manager and start it again.")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, "PoE Tracker", 0x40)
        except Exception:
            print(msg)
        return
    cfg = config_mod.load_config()
    fmt.set_tz(cfg.timezone)
    try:
        service.daily_backup()
    except Exception:
        log.exception("backup failed")

    tracker = service.Tracker(cfg)
    if tracker.log_path:
        log.info("Watching %s", tracker.log_path)
    else:
        log.warning("Client.txt not found. Set log_path in %s", paths.config_dir() / "settings.yaml")
    tracker.start()
    service.remove_leftovers()
    STATE.cfg = cfg
    STATE.tracker = tracker
    from .. import updater as updater_mod
    STATE.updater = updater_mod.Updater(cfg.settings.get("update_repo"), cfg.settings.get("update_token"))
    if cfg.settings.get("update_check", True):
        STATE.updater.start_background()
    STATE.load_prefs()
    from .. import profile
    STATE.snaps = profile.Snapshotter(cfg, stamp=lambda: (lambda st: (st.get("last_event_utc"), st.get("data_gen")))(
        tracker.status()))
    STATE.snaps.start()
    app.on_shutdown(tracker.stop.set)

    app.add_static_files("/static", str(paths.PACKAGE_DIR / "ui" / "static"))
    from .. import atlas_tree
    app.add_static_files("/atlastree", str(atlas_tree.cache_dir()))     # GGG's tree art, downloaded on first use
    from .. import passive_tree
    app.add_static_files("/passivetree", str(passive_tree.cache_dir()))

    @app.get("/snaptree/{snap_id}")
    def snap_tree(snap_id: int, part: str = "main"):
        """A snapshot's passive tree drawing (fetched by the Characters page)."""
        from fastapi.responses import Response
        from .. import profile
        from . import tree_view
        con = STATE.con()
        try:
            snap = profile.load(con, snap_id)
        finally:
            con.close()
        if not snap or not snap.get("passives"):
            return Response("", media_type="image/svg+xml")
        ch = (snap.get("items") or {}).get("character") or {}
        lay = passive_tree.layout() or {}
        asc = ch.get("class") or snap.get("class") or ""
        base = (lay.get("asc_base") or {}).get(asc, asc)
        body = tree_view.svg(snap_id, snap["passives"], base, asc, part)
        return Response(body, media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})
    from . import pages  # noqa: F401  (registers the pages)
    from . import mini_page  # noqa: F401  (the mini window's page)
    from . import layout

    # One window, many pages: the side menu and top bar are built once and the
    # pages are swapped inside them (no full reload when you switch pages).
    @ui.page("/")
    @ui.page("/{_:path}")
    def index():
        layout.build_shell()
        ui.context.client.pt_sub = ui.sub_pages(pages.ROUTES).classes("w-full")
    pages.start_warmup()

    window = window or cfg.settings.get("window") or "native"
    native = window == "native"
    kwargs = dict(
        title="PoE Tracker", dark=True, reload=False, show_welcome_message=False,
        favicon=str(paths.PACKAGE_DIR / "ui" / "static" / "icon.png"), port=port or int(cfg.settings.get("port") or 8765),
        host="127.0.0.1",
    )
    if native:
        try:
            import webview  # noqa: F401
        except ImportError:
            log.warning("pywebview isn't installed; opening in the browser instead")
            native = False
    if native:
        from nicegui import native as ng_native
        kwargs["port"] = port or ng_native.find_open_port()
    # the mini tracker finds the dashboard through this file
    from .. import mini as mini_mod
    mini_mod.write_port(kwargs["port"])
    if cfg.settings.get("mini_on_start") and window != "headless":
        app.on_startup(lambda: mini_mod.launch_mini())
    if native:
        from . import winpos
        size, extra = winpos.window_args()
        app.native.window_args.update(extra)
        winpos.track(app)
        service.set_window_icon("PoE Tracker")
        ui.run(native=True, window_size=size, **kwargs)
    else:
        ui.run(show=bool(cfg.settings.get("open_browser", True)) and window != "headless", **kwargs)
