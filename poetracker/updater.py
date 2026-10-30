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
    return subprocess.run(["git", *args], cwd=PROJECT_DIR, capture_output=True, text=True, timeout=timeout,
                          creationflags=_NO_WINDOW)


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
        r = _git("log", "-1", "--format=%h · %cd", "--date=format:%b %d, %H:%M")
        return r.stdout.strip() or None

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

    def start_background(self, every_minutes: float = 30) -> None:
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
    """Start a fresh copy of the tracker a moment after this one closes. Uses
    Start PoE Tracker.bat when present, so new Python packages get installed."""
    bat = PROJECT_DIR / "Start PoE Tracker.bat"
    if sys.platform == "win32":
        launch = f'start "" /min "{bat}"' if bat.exists() else f'start "" "{sys.executable}" -m poetracker'
        subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & {launch}', cwd=PROJECT_DIR, shell=True,
                         creationflags=_NO_WINDOW | 0x00000008)   # DETACHED_PROCESS
    else:
        subprocess.Popen(["sh", "-c", f'sleep 3; "{sys.executable}" -m poetracker'], cwd=PROJECT_DIR,
                         start_new_session=True)
