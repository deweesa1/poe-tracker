"""PoE Tracker: a local Path of Exile play tracker built on Client.txt."""
__version__ = "0.1.0"

APP_ID = "deweesa1.PoETracker"


def _windows_app_id() -> None:
    """Tell Windows this is PoE Tracker, not Python: the taskbar then groups its
    windows under PoE Tracker's icon (and a pinned shortcut from the installer,
    which carries the same id)."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


_windows_app_id()
