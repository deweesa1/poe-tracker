"""Updates from GitHub: the tracker checks github.com/deweesa1/poe-tracker in the
background and can update itself and restart.

Two ways, picked automatically:
- Installed copy (PoE Tracker Setup.exe; the app folder has version.json): like
  Path of Building, it asks GitHub which files the newest version has (with each
  file's fingerprint), downloads only the ones that differ from yours, checks
  them and swaps them in. No Git needed.
- Developer copy (a git clone, e.g. in C:/dev/poe-tracker): git fetch / pull, which
  needs Git for Windows. Your data lives
in the data folder, not here, so updating never touches it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
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


VERSION_FILE = "version.json"          # in an installed copy: {"commit": "<sha>", "date": "..."}
APP_PARTS = ("poetracker/", "requirements.txt")   # the files an installed copy gets from GitHub


def installed_copy() -> bool:
    return (PROJECT_DIR / VERSION_FILE).exists() and not (PROJECT_DIR / ".git").exists()


def _owner_repo(url: str) -> str:
    m = re.search(r"github\.com[/:]([^/]+)/([^/.]+)", url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else "deweesa1/poe-tracker"


_TOKEN: dict = {"value": None}     # a GitHub access token, for a private repository (Settings → Updates)


def _http(url: str, timeout: float = 30, raw: bool = False):
    import urllib.request
    headers = {"User-Agent": "poe-tracker-updater",
               "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    if _TOKEN["value"] and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {_TOKEN['value']}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if raw else json.loads(data.decode("utf-8"))


_HEAD: dict = {"etag": None, "sha": None}


def _head_sha(repo: str) -> str:
    """The newest commit on the branch, asked cheaply: GitHub answers "not
    modified" when nothing changed, and those answers don't count against the
    60-an-hour limit, so the tracker can ask every minute."""
    import urllib.error
    import urllib.request
    headers = {"User-Agent": "poe-tracker-updater", "Accept": "application/vnd.github.sha"}
    if _TOKEN["value"]:
        headers["Authorization"] = f"Bearer {_TOKEN['value']}"
    if _HEAD["etag"] and _HEAD["sha"]:
        headers["If-None-Match"] = _HEAD["etag"]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/commits/{BRANCH}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _HEAD["sha"] = r.read().decode().strip()
            _HEAD["etag"] = r.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code != 304:
            raise
    return _HEAD["sha"]


def blob_sha(data: bytes) -> str:
    """Git's fingerprint of a file's contents (what GitHub lists for every file)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def file_sha(data: bytes) -> tuple[str, str]:
    """A file's fingerprint as stored, and with Windows line endings (CRLF) turned
    into LF the way Git stores text files. A file matches GitHub's if either does."""
    raw = blob_sha(data)
    return raw, (blob_sha(data.replace(b"\r\n", b"\n")) if b"\r\n" in data else raw)


def _local_files() -> dict[str, Path]:
    """The app files in this copy, by their path in the repo."""
    out = {}
    req = PROJECT_DIR / "requirements.txt"
    if req.exists():
        out["requirements.txt"] = req
    for f in (PROJECT_DIR / "poetracker").rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
            out[f.relative_to(PROJECT_DIR).as_posix()] = f
    return out


def _git(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    # git writes UTF-8; Windows would otherwise decode it as cp1252 ("Â·")
    return subprocess.run(["git", *args], cwd=PROJECT_DIR, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=_NO_WINDOW)


class Updater:
    def __init__(self, repo_url: str | None = None, token: str | None = None):
        self.repo_url = repo_url or DEFAULT_REPO
        _TOKEN["value"] = (token or "").strip() or None
        self.repo = _owner_repo(self.repo_url)
        self.installed = installed_copy()
        self.lock = threading.Lock()
        self.state: dict = {"checked": None, "available": False, "behind": 0, "changes": [], "error": None,
                            "version": None, "connected": False, "busy": False, "installed": self.installed,
                            "git": self.installed or bool(shutil.which("git")), "needs_installer": False}
        self._target: str | None = None       # newest commit seen by check()
        self._backoff_until = 0.0              # GitHub asked us to slow down
        self.state["connected"] = self.connected()
        self.state["version"] = self.version()

    # -- facts about this folder ------------------------------------------
    def connected(self) -> bool:
        if self.installed:
            return True
        return bool(shutil.which("git")) and (PROJECT_DIR / ".git").exists()

    def _local_version(self) -> dict:
        try:
            return json.loads((PROJECT_DIR / VERSION_FILE).read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def version(self) -> str | None:
        if self.installed:
            v = self._local_version()
            return f"{v['commit'][:7]} · {v.get('date', '')}".strip(" ·") if v.get("commit") else None
        if not self.connected():
            return None
        r = _git("log", "-1", "--format=%h|%cd", "--date=format:%b %d, %H:%M")
        out = r.stdout.strip()
        return out.replace("|", " · ") if out else None

    # -- check / apply ----------------------------------------------------
    def check(self) -> dict:
        if self.installed:
            return self._check_installed()
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
        """Get the new version. Returns (ok, message)."""
        if self.installed:
            return self._apply_installed()
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

    # -- installed copies: fingerprint list from GitHub, changed files only ----
    def _check_installed(self) -> dict:
        with self.lock:
            st = self.state
            st["version"] = self.version()
            st["connected"] = True            # an installed copy always updates from GitHub
            try:
                if time.time() < self._backoff_until:
                    st["checked"] = time.time()
                    return dict(st)
                target = _head_sha(self.repo)
                local = self._local_version().get("commit")
                if local == target:
                    st.update(available=False, behind=0, changes=[], error=None)
                elif target != self._target or not st.get("available"):     # only look up what changed once
                    behind, changes = 1, []
                    try:
                        if local:
                            cmp = _http(f"https://api.github.com/repos/{self.repo}/compare/{local}...{target}")
                            behind = cmp.get("ahead_by") or behind
                            changes = [c["commit"]["message"].splitlines()[0] for c in reversed(cmp.get("commits") or [])]
                        else:
                            changes = [_http(f"https://api.github.com/repos/{self.repo}/commits/{target}")
                                       ["commit"]["message"].splitlines()[0]]
                    except Exception:
                        pass
                    st.update(available=True, behind=behind, changes=changes[:15], error=None)
                self._target = target
            except Exception as e:
                import urllib.error
                if isinstance(e, urllib.error.HTTPError) and e.code in (403, 429):
                    self._backoff_until = time.time() + 600     # hourly limit used up: wait it out
                st.update(error=_short_error(e))
            st["checked"] = time.time()
            return dict(st)

    def _apply_installed(self) -> tuple[bool, str]:
        with self.lock:
            self.state["busy"] = True
            try:
                target = self._target or _http(f"https://api.github.com/repos/{self.repo}/commits/{BRANCH}")["sha"]
                tree = _http(f"https://api.github.com/repos/{self.repo}/git/trees/{target}?recursive=1", timeout=60)
                remote = {t["path"]: t["sha"] for t in tree.get("tree", [])
                          if t.get("type") == "blob" and t["path"].startswith(APP_PARTS)
                          and "__pycache__" not in t["path"]}
                if not remote:
                    return False, "GitHub sent an empty file list; try again later."
                local = _local_files()
                hashes = {p: file_sha(f.read_bytes()) for p, f in local.items()}

                def same(p):
                    return remote[p] in hashes.get(p, ())
                if remote.get("requirements.txt") and not same("requirements.txt"):
                    # new Python packages: the installer brings those, a file update can't
                    self.state["needs_installer"] = True
                    return False, ("This update needs new Python packages, so it comes as a new installer. Download "
                                   f"PoE Tracker Setup.exe from https://github.com/{self.repo}/releases/latest and run "
                                   "it; your data is kept.")
                todo = [p for p in remote if not same(p)]
                staged: dict[str, bytes] = {}
                for p in todo:
                    from urllib.parse import quote
                    # through the API, so a private repository works with a token
                    data = _http(f"https://api.github.com/repos/{self.repo}/contents/{quote(p)}?ref={target}",
                                 timeout=60, raw=True)
                    if blob_sha(data) != remote[p]:
                        return False, f"A downloaded file didn't match GitHub's fingerprint ({p}); nothing was changed."
                    staged[p] = data
                # everything downloaded and checked: now swap the files in
                for p, data in staged.items():
                    dest = PROJECT_DIR / p
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dest.with_name(dest.name + ".new")
                    tmp.write_bytes(data)
                    os.replace(tmp, dest)
                removed = 0
                for p, f in local.items():
                    if p not in remote and p.startswith("poetracker/"):
                        try:
                            f.unlink()
                            removed += 1
                        except OSError:
                            pass
                date = time.strftime("%b %d, %H:%M")
                try:
                    c = _http(f"https://api.github.com/repos/{self.repo}/commits/{target}")
                    from datetime import datetime
                    date = datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00")).astimezone().strftime(
                        "%b %d, %H:%M")
                except Exception:
                    pass
                (PROJECT_DIR / VERSION_FILE).write_text(json.dumps({"commit": target, "date": date}), encoding="utf-8")
                self.state.update(available=False, behind=0, changes=[], version=self.version())
                log.info("updated to %s: %d files changed, %d removed", target[:7], len(staged), removed)
                return True, f"Updated ({len(staged)} file{'s' if len(staged) != 1 else ''})."
            except Exception as e:
                log.exception("update failed")
                return False, f"Update failed: {_short_error(e)}"
            finally:
                self.state["busy"] = False

    def set_token(self, token: str | None) -> None:
        _TOKEN["value"] = (token or "").strip() or None

    def check_soon(self, older_than: float = 90) -> None:
        """Check in the background if the last check is older than this (seconds)."""
        if self.installed:
            older_than = max(older_than, 60)      # an unchanged answer is free (see _head_sha)
        st = self.state
        if st.get("busy") or self.lock.locked() or (st.get("checked") and time.time() - st["checked"] < older_than):
            return
        threading.Thread(target=self.check, daemon=True, name="update-check").start()

    def start_background(self, every_minutes: float = 2) -> None:
        if self.installed:
            every_minutes = 1                      # cheap: GitHub says "not modified" without using the hourly limit

        def loop():
            time.sleep(20)               # let the tracker finish starting first
            while True:
                try:
                    self.check()
                except Exception:
                    log.exception("update check failed")
                time.sleep(every_minutes * 60)
        threading.Thread(target=loop, daemon=True, name="updates").start()


def _short_error(e: Exception) -> str:
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 403:
            return "GitHub says to slow down; it'll check again in a few minutes"
        if e.code in (401, 404):
            return ("GitHub won't show the project (private repository?): add an access token in Settings → Updates"
                    if not _TOKEN["value"] else "GitHub didn't accept the access token")
        return f"GitHub answered {e.code}"
    if isinstance(e, urllib.error.URLError):
        return "couldn't reach GitHub (offline?)"
    return str(e)[:200]


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
    if req.exists() and not installed_copy():
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
