"""Starting the NiceGUI dashboard, in its own window (default) or a browser."""
from __future__ import annotations

import logging

from nicegui import app, ui

from .. import config as config_mod, paths, service
from . import fmt
from .layout import STATE

log = logging.getLogger(__name__)


def _logos_folder() -> None:
    folder = paths.data_dir() / "league-logos"
    folder.mkdir(exist_ok=True)
    readme = folder / "README.txt"
    if not readme.exists():
        readme.write_text(
            "League colours from logos\n\n"
            "Save a league's logo here, named exactly like the league, e.g.\n"
            "  Curse of the Allflame.png\n"
            "  Mirage.jpg\n"
            "(png, jpg, jpeg or webp). The tracker picks the logo's main colour and themes\n"
            "that league with it. The images are only read for their colours; they aren't\n"
            "shown and never leave this folder. Restart the tracker after adding one.\n",
            encoding="utf-8")


def run(window: str | None = None, port: int | None = None) -> None:
    service.setup_logging()
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
    STATE.cfg = cfg
    STATE.tracker = tracker
    from .. import updater as updater_mod
    STATE.updater = updater_mod.Updater(cfg.settings.get("update_repo"))
    if cfg.settings.get("update_check", True):
        STATE.updater.start_background()
    STATE.load_prefs()
    app.on_shutdown(tracker.stop.set)

    app.add_static_files("/static", str(paths.PACKAGE_DIR / "ui" / "static"))
    from . import pages  # noqa: F401  (registers the pages)
    pages.start_warmup()
    _logos_folder()

    window = window or cfg.settings.get("window") or "native"
    native = window == "native"
    kwargs = dict(
        title="PoE Tracker", dark=True, reload=False, show_welcome_message=False,
        favicon="🔶", port=port or int(cfg.settings.get("port") or 8765),
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
        ui.run(native=True, window_size=(1500, 950), **kwargs)
    else:
        ui.run(show=bool(cfg.settings.get("open_browser", True)) and window != "headless", **kwargs)
