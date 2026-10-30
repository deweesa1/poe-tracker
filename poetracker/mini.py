"""The mini tracker: a small always-on-top window showing /mini from the
running tracker. Started with "python -m poetracker mini" (the main window's
mini button does this).

Locked (default while playing): clicks pass through to the game and the
window never takes focus. Unlocked: drag it, resize it, use its buttons.
Toggle with the hotkey (mini_hotkey in settings.yaml, set in Settings), or with the
lock button in the main window's side menu.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.request

from . import config as config_mod, paths

log = logging.getLogger(__name__)
TITLE = "PoE Tracker - Mini"
DEFAULT_HOTKEY = "ctrl+alt+m"


def hotkey_label(settings: dict | None) -> str:
    """'ctrl+shift+f11' -> 'Ctrl+Shift+F11' for display."""
    text = (settings or {}).get("mini_hotkey") or DEFAULT_HOTKEY
    nice = {"scrolllock": "Scroll Lock", "pageup": "Page Up", "pagedown": "Page Down", "numlock": "Num Lock"}

    def one(p):
        if p in nice:
            return nice[p]
        if p.startswith("num") and p[3:].isdigit():
            return f"Num {p[3:]}"
        return p.upper() if p.startswith("f") and p[1:].isdigit() else p.capitalize()
    return "+".join(one(p) for p in text.replace(" ", "").split("+"))
PORT_FILE = "ui_port.txt"


def write_port(port: int) -> None:
    try:
        (paths.data_dir() / PORT_FILE).write_text(str(port), encoding="utf-8")
    except Exception:
        log.exception("couldn't write the port file")


def _server_url() -> str | None:
    try:
        port = int((paths.data_dir() / PORT_FILE).read_text(encoding="utf-8").strip())
    except Exception:
        return None
    url = f"http://127.0.0.1:{port}"
    return url if _alive(url) else None


def _alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/mini", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _prefs_path():
    return paths.data_dir() / "mini.json"


def _load_prefs() -> dict:
    try:
        return json.loads(_prefs_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_prefs(p: dict) -> None:
    try:
        _prefs_path().write_text(json.dumps(p), encoding="utf-8")
    except Exception:
        pass


VK = {"scrolllock": 0x91, "pause": 0x13, "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21,
      "pagedown": 0x22, "delete": 0x2E, "numlock": 0x90,
      **{f"num{i}": 0x60 + i for i in range(10)},
      **{f"f{i}": 0x6F + i for i in range(1, 13)}, **{chr(c): c for c in range(ord("0"), ord("9") + 1)},
      **{chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)}}
MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}


def parse_hotkey(text: str) -> tuple[int, int] | None:
    mods, key = 0, None
    for part in (text or "").lower().replace(" ", "").split("+"):
        if part in MODS:
            mods |= MODS[part]
        elif part in VK:
            key = VK[part]
    return (mods | 0x4000, key) if key else None       # 0x4000 = MOD_NOREPEAT


class Win32:
    """The few Windows calls the mini window needs (click-through, on top, opacity)."""
    GWL_EXSTYLE = -20
    WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x08000000
    LWA_ALPHA = 0x2
    HWND_TOPMOST = -1
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x10, 0x20

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes
        self.u = ctypes.windll.user32
        self.u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self.u.FindWindowW.restype = wintypes.HWND

    def find(self, title: str, timeout: float = 15):
        end = time.time() + timeout
        while time.time() < end:
            h = self.u.FindWindowW(None, title)
            if h:
                return h
            time.sleep(0.2)
        return None

    def apply(self, hwnd, locked: bool, opacity: float, click_through: bool = False) -> None:
        ex = self.u.GetWindowLongPtrW(hwnd, self.GWL_EXSTYLE)
        ex |= self.WS_EX_LAYERED | self.WS_EX_TOOLWINDOW          # see-through; no taskbar / Alt+Tab entry
        ex &= ~(self.WS_EX_TRANSPARENT | self.WS_EX_NOACTIVATE)
        if locked:
            ex |= self.WS_EX_NOACTIVATE                            # never takes focus from the game
            if click_through:
                ex |= self.WS_EX_TRANSPARENT                       # clicks pass straight through
        self.u.SetWindowLongPtrW(hwnd, self.GWL_EXSTYLE, ex)
        self.u.SetLayeredWindowAttributes(hwnd, 0, int(max(0.3, min(1.0, opacity)) * 255), self.LWA_ALPHA)
        self.u.SetWindowPos(hwnd, self.HWND_TOPMOST, 0, 0, 0, 0,
                            self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOACTIVATE | self.SWP_FRAMECHANGED)

    def hotkey_loop(self, mods: int, key: int, on_press) -> bool:
        """Blocks: calls on_press() each time the hotkey is pressed."""
        from ctypes import wintypes
        if not self.u.RegisterHotKey(None, 1, mods, key):
            return False
        msg = wintypes.MSG()
        while self.u.GetMessageW(self.ct.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:      # WM_HOTKEY
                try:
                    on_press()
                except Exception:
                    log.exception("hotkey action failed")
        return True


def run_mini() -> int:
    from .service import setup_logging, single_instance
    setup_logging()
    url = _server_url()
    if not url:
        _message("PoE Tracker isn't running. Start it first, then open the mini tracker from its top bar.")
        return 1
    if not single_instance(name="mini.lock", wait=0):
        # already open: bring it forward. If there's no window, an old copy got
        # stuck after closing; end it and open a fresh one.
        if _bring_forward():
            return 0
        _kill_stale()
        if not single_instance(name="mini.lock", wait=5):
            return 0
    _write_pid()
    import webview
    cfg = config_mod.load_config()
    s = cfg.settings
    p = _load_prefs()
    state = {"locked": bool(p.get("locked", False)), "opacity": float(s.get("mini_opacity", 0.92)),
             "through": bool(s.get("mini_click_through", False)), "collapsed": bool(p.get("collapsed", False))}
    win32 = Win32() if sys.platform == "win32" else None
    hwnd_box: dict = {}

    def apply():
        if win32 and hwnd_box.get("h"):
            win32.apply(hwnd_box["h"], state["locked"], state["opacity"], state["through"])
        try:
            win.evaluate_js(f"window.ptSetLocked && window.ptSetLocked({str(state['locked']).lower()});"
                            f"window.ptSetCollapsed && window.ptSetCollapsed({str(state['collapsed']).lower()})")
        except Exception:
            pass

    class Api:
        def toggle_lock(self):
            state["locked"] = not state["locked"]
            apply()
            save()

        def set_lock(self, locked):
            state["locked"] = bool(locked)
            apply()
            save()

        def set_collapsed(self, collapsed, need_h=0):
            """Collapse to the timer and bar (shrinking the window to fit), or expand back."""
            collapsed = bool(collapsed)
            try:
                if collapsed and not state["collapsed"]:
                    p["expanded_h"] = win.height
                    if need_h:
                        win.resize(win.width, max(60, int(need_h)))
                elif not collapsed and state["collapsed"]:
                    win.resize(win.width, int(p.get("expanded_h") or 380))
            except Exception:
                log.debug("collapse resize failed", exc_info=True)
            state["collapsed"] = collapsed
            save()

        def resize(self, w, h):
            # frameless windows have no border to drag, so the page's corner grip calls this
            try:
                win.resize(max(220, int(w)), max(60, int(h)))
            except Exception:
                log.debug("resize failed", exc_info=True)

        def close(self):
            save()
            closing.set()
            # destroy from another thread: doing it inside the JS call can hang the window
            threading.Thread(target=win.destroy, daemon=True).start()

    def save():
        try:
            p.update(x=win.x, y=win.y, width=win.width, height=win.height, locked=state["locked"],
                     collapsed=state["collapsed"])
        except Exception:
            p.update(locked=state["locked"], collapsed=state["collapsed"])
        _save_prefs(p)

    closing = threading.Event()
    win = webview.create_window(
        TITLE, url + "/mini", js_api=Api(), width=int(p.get("width", 300)), height=int(p.get("height", 380)),
        x=p.get("x"), y=p.get("y"), frameless=True, easy_drag=True, on_top=True, resizable=True,
        min_size=(220, 60), background_color="#15120b")

    def started():
        if win32:
            hwnd_box["h"] = win32.find(TITLE)
        time.sleep(1.0)                # let the page load before telling it the lock state
        apply()
        hk = parse_hotkey(s.get("mini_hotkey", DEFAULT_HOTKEY))
        if win32 and hk:
            def toggle():
                state["locked"] = not state["locked"]
                apply()
                save()
            def hot():
                p.update(hotkey=s.get("mini_hotkey", DEFAULT_HOTKEY), hotkey_ok=True)
                _save_prefs(p)
                if not win32.hotkey_loop(hk[0], hk[1], toggle):
                    log.warning("mini hotkey %s is taken by another program", s.get("mini_hotkey"))
                    p.update(hotkey_ok=False)
                    _save_prefs(p)
            threading.Thread(target=hot, daemon=True, name="mini-hotkey").start()
        # remember where it was put; close when the main tracker closes
        last, gone = None, 0
        while not closing.wait(5):
            try:
                now = (win.x, win.y, win.width, win.height)
                if now != last:
                    last = now
                    save()
            except Exception:
                pass
            gone = 0 if _alive(url) else gone + 1
            if gone >= 3:
                save()
                win.destroy()
                return

    win.events.closed += closing.set
    webview.start(started)
    # Make sure nothing keeps this process (and mini.lock) alive after the window
    # is gone, or the button can't open the mini tracker again.
    try:
        (paths.data_dir() / "mini.pid").unlink()
    except OSError:
        pass
    os._exit(0)


def _write_pid() -> None:
    try:
        (paths.data_dir() / "mini.pid").write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass


def _bring_forward() -> bool:
    """Show the open mini window on top. False when there's no such window."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, TITLE)
        if not hwnd or not ctypes.windll.user32.IsWindowVisible(hwnd):
            return False
        ctypes.windll.user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _kill_stale() -> None:
    """End a mini tracker process that lost its window but kept running."""
    try:
        pid = int((paths.data_dir() / "mini.pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return
    if pid == os.getpid():
        return
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10,
                           creationflags=0x08000000)
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
    except Exception:
        log.exception("couldn't end the old mini tracker")


def _message(text: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "PoE Tracker", 0x40)
    except Exception:
        print(text)


def launch_mini() -> None:
    """Open the mini tracker as its own process (from the main window's button)."""
    import subprocess
    exe = sys.executable
    if sys.platform == "win32" and exe.lower().endswith("python.exe"):
        w = exe[:-10] + "pythonw.exe"
        from pathlib import Path
        exe = w if Path(w).exists() else exe
    flags = 0x00000008 | 0x08000000 if sys.platform == "win32" else 0      # detached, no console
    subprocess.Popen([exe, "-m", "poetracker", "mini"], cwd=str(paths.PACKAGE_DIR.parent), creationflags=flags,
                     close_fds=True)
