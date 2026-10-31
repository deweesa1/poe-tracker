"""Updates from GitHub: the tracker checks the project's git repository in the
background and can pull the new version and restart itself.

Works when the project folder is a git clone (Update PoE Tracker.bat or the
Settings page sets that up) and Git for Windows is installed. Your data lives
in the data folder, not here, so updating never touches it.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

PROJECT_DIR = paths.PACKAGE_DIR.parent
DEFAULT_REPO = "https://github.com/deweesa1/poe-tracker.git"
BRANCH = "main"
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0     # don't flash a console window


def _git(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    # git writes UTF-8; Windows would otherwise decode it as cp1252 ("Â·")
    return subprocess.run(["git", *args], cwd=PROJECT_DIR, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=_NO_WINDOW)


class Updater:
    def __init__(self, repo_url: str | None = None):
        self.repo_url = repo_url or DEFAULT_REPO
        self.lock = threading.Lock()
        self.state: dict = {"checked": None, "available": False, "behind": 0, "changes": [], "error": None,
                            "version": None, "connected": False, "git": bool(shutil.which("git")), "busy": False}

    # -- facts about this folder ------------------------------------------
    def connected(self) -> bool:
        return self.state["git"] and (PROJECT_DIR / ".git").exists()

    def version(self) -> str | None:
        if not self.connected():
            return None
        r = _git("log", "-1", "--format=%h|%cd", "--date=format:%b %d, %H:%M")
        out = r.stdout.strip()
        return out.replace("|", " · ") if out else None

    # -- check / apply ----------------------------------------------------
    def check(self) -> dict:
        with self.lock:
            st = self.state
            st["git"] = bool(shutil.which("git"))
            st["connected"] = self.connected()
            st["version"] = self.version()
            if not st["connected"]:
                st.update(available=False, behind=0, changes=[], error=None)
                return dict(st)
            try:
                f = _git("fetch", "-q", "origin", BRANCH)
                if f.returncode:
                    raise RuntimeError(f.stderr.strip().splitlines()[-1] if f.stderr.strip() else "fetch failed")
                n = _git("rev-list", "--count", f"HEAD..origin/{BRANCH}")
                behind = int(n.stdout.strip() or 0)
                log_ = _git("log", "--format=%s", f"HEAD..origin/{BRANCH}") if behind else None
                st.update(available=behind > 0, behind=behind, error=None,
                          changes=[l for l in (log_.stdout.splitlines() if log_ else []) if l.strip()][:15])
            except Exception as e:     # offline, no access...
                st.update(error=str(e))
            st["checked"] = time.time()
            return dict(st)

    def apply(self) -> tuple[bool, str]:
        """Pull the new version. Returns (ok, message)."""
        with self.lock:
            self.state["busy"] = True
            try:
                r = _git("pull", "--ff-only", "origin", BRANCH, timeout=180)
                if r.returncode:
                    msg = (r.stderr or r.stdout).strip()
                    if "local changes" in msg or "would be overwritten" in msg:
                        msg = "Some files in the project folder were edited by hand, so the update stopped."
                    return False, msg
                self.state.update(available=False, behind=0, changes=[])
                self.state["version"] = self.version()
                return True, "Updated."
            finally:
                self.state["busy"] = False

    def connect(self) -> tuple[bool, str]:
        """Turn a folder unzipped from a download into a clone of the repo."""
        if not shutil.which("git"):
            return False, "Git isn't installed (https://git-scm.com/download/win)."
        steps = [("init", "-q"), ("remote", "add", "origin", self.repo_url), ("fetch", "-q", "origin", BRANCH),
                 ("checkout", "-q", "-f", "-B", BRANCH, f"origin/{BRANCH}"),
                 ("branch", "-q", f"--set-upstream-to=origin/{BRANCH}", BRANCH)]
        for s in steps:
            r = _git(*s, timeout=180)
            if r.returncode and not (s[0] == "remote" and "already exists" in r.stderr):
                return False, (r.stderr or r.stdout).strip() or f"git {s[0]} failed"
        self.state["connected"] = True
        self.state["version"] = self.version()
        return True, "Connected to GitHub."

    def check_soon(self, older_than: float = 90) -> None:
        """Check in the background if the last check is older than this (seconds)."""
        st = self.state
        if st.get("busy") or self.lock.locked() or (st.get("checked") and time.time() - st["checked"] < older_than):
            return
        threading.Thread(target=self.check, daemon=True, name="update-check").start()

    def start_background(self, every_minutes: float = 2) -> None:
        def loop():
            time.sleep(20)               # let the tracker finish starting first
            while True:
                try:
                    self.check()
                except Exception:
                    log.exception("update check failed")
                time.sleep(every_minutes * 60)
        threading.Thread(target=loop, daemon=True, name="updates").start()


def restart_app() -> None:
    """Start a fresh copy of the tracker once this one has closed. Runs
    `python -m poetracker restart` with no console window: it waits for this
    copy to let go of the database, installs any new Python packages quietly,
    then opens the tracker again."""
    exe = _windowless_python()
    again = [a for a in sys.argv[1:] if a in ("run", "--dev", "--browser")]   # reopen the same way (e.g. dev mode)
    if sys.platform == "win32":
        subprocess.Popen([exe, "-m", "poetracker", "restart", *again], cwd=PROJECT_DIR,
                         creationflags=_NO_WINDOW | 0x00000008 | 0x00000200,   # no window, detached, own group
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
    else:
        subprocess.Popen([exe, "-m", "poetracker", "restart", *again], cwd=PROJECT_DIR, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _windowless_python() -> str:
    """pythonw.exe next to the running Python on Windows (no console), else this Python."""
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.name.lower() == "python.exe" and (exe.parent / "pythonw.exe").exists():
        return str(exe.parent / "pythonw.exe")
    return str(exe)


def _console_python() -> str:
    """python.exe for running pip (pip under pythonw can't report progress, but works too)."""
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


def run_restart(args: list[str] | None = None, wait: float = 60.0) -> int:
    """The hidden helper behind restart_app()."""
    from . import service
    service.setup_logging()
    # 1. wait for the old tracker to close (it holds tracker.lock while running)
    if not service.single_instance(wait=wait):
        log.warning("restart: the old tracker didn't close within %ss", wait)
        return 1
    service.release_instance()
    # 2. new packages, quietly (needs internet; a failure isn't fatal)
    req = PROJECT_DIR / "requirements.txt"
    if req.exists():
        try:
            r = subprocess.run([_console_python(), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                                "-r", str(req)], cwd=PROJECT_DIR, capture_output=True, text=True, timeout=600,
                               creationflags=_NO_WINDOW)
            if r.returncode:
                log.warning("restart: pip install failed: %s", (r.stderr or r.stdout)[-800:])
        except Exception:
            log.exception("restart: pip install failed")
    # 3. open the tracker again, the way it was started. Dev mode gets its log
    # window back (a new console), the normal tracker none.
    args = [a for a in (args or []) if a in ("run", "--dev", "--browser")]
    if "--dev" in args and sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "title PoE Tracker (dev) & " + subprocess.list2cmdline(
                              [_console_python(), "-m", "poetracker", *args]) + " & pause"],
                         cwd=PROJECT_DIR, creationflags=0x00000010)        # CREATE_NEW_CONSOLE
        return 0
    subprocess.Popen([_windowless_python(), "-m", "poetracker", *args], cwd=PROJECT_DIR,
                     creationflags=(_NO_WINDOW | 0x00000008) if sys.platform == "win32" else 0,
                     start_new_session=sys.platform != "win32",
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0
