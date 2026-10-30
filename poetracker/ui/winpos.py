"""Remember where the main window was, and open it there next time.

Without this, pywebview places the window itself, and on Windows with display
scaling (125%, 150%...) it lands off-centre, toward the bottom right. The
first time, the window is sized to fit the screen and centred; after that it
opens where you left it (and maximized if you left it maximized).
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time

from .. import paths

log = logging.getLogger(__name__)
FILE = "window.json"
DEFAULT_SIZE = (1500, 950)


def _load() -> dict:
    try:
        return json.loads((paths.data_dir() / FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        (paths.data_dir() / FILE).write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def _screen() -> tuple[int, int, int, int, int, int, int, int] | None:
    """(work area x, y, w, h, virtual desktop x, y, w, h) on Windows, else None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)    # SPI_GETWORKAREA
        gm = ctypes.windll.user32.GetSystemMetrics
        return (r.left, r.top, r.right - r.left, r.bottom - r.top, gm(76), gm(77), gm(78), gm(79))
    except Exception:
        return None


def window_args() -> tuple[tuple[int, int], dict]:
    """(window_size, extra create_window args) for ui.run."""
    d = _load()
    scr = _screen()
    w, h = int(d.get("width") or DEFAULT_SIZE[0]), int(d.get("height") or DEFAULT_SIZE[1])
    x, y = d.get("x"), d.get("y")
    if scr:
        wx, wy, ww, wh, vx, vy, vw, vh = scr
        # a saved spot that's no longer on any screen (monitor unplugged...) is dropped
        if x is not None and y is not None and not (vx <= x + 120 <= vx + vw and vy <= y + 20 <= vy + vh):
            x = y = None
        w, h = min(w, ww), min(h, wh)
        if x is None or y is None:
            w, h = min(w, int(ww * 0.92)), min(h, int(wh * 0.92))
            x, y = wx + (ww - w) // 2, wy + (wh - h) // 2
    extra = {}
    if x is not None and y is not None:
        extra.update(x=int(x), y=int(y))
    if d.get("maximized"):
        extra["maximized"] = True
    return (w, h), extra


def track(app) -> None:
    """Save the window's position and size as you move it (written at most every 2s)."""
    d = _load()
    state = {"dirty": False, "max": bool(d.get("maximized"))}
    lock = threading.Lock()

    def moved(e):
        x, y = e.args.get("x"), e.args.get("y")
        if state["max"] or x is None or y is None or x <= -30000:      # minimized windows report -32000
            return
        with lock:
            d.update(x=int(x), y=int(y))
            state["dirty"] = True

    def resized(e):
        w, h = e.args.get("width"), e.args.get("height")
        if state["max"] or not w or not h or w < 300 or h < 200:
            return
        with lock:
            d.update(width=int(w), height=int(h))
            state["dirty"] = True

    def maximized(_e=None):
        state["max"] = True
        with lock:
            d["maximized"] = True
            state["dirty"] = True

    def restored(_e=None):
        state["max"] = False
        with lock:
            d["maximized"] = False
            state["dirty"] = True

    app.native.on("moved", moved)
    app.native.on("resized", resized)
    app.native.on("maximized", maximized)
    app.native.on("restored", restored)

    def writer():
        while True:
            time.sleep(2)
            with lock:
                if state["dirty"]:
                    _save(d)
                    state["dirty"] = False
    threading.Thread(target=writer, daemon=True, name="winpos").start()
