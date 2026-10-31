"""Running everything together: log watcher, clipboard watcher, dashboard."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import captures, config as config_mod, db, ingest, paths

log = logging.getLogger("poetracker")

STANDARD_LOCATIONS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt",
    r"C:\Program Files\Steam\steamapps\common\Path of Exile\logs\Client.txt",
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\Client.txt",
    r"C:\Program Files\Grinding Gear Games\Path of Exile\logs\Client.txt",
]


def setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = logging.handlers.RotatingFileHandler(paths.app_log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    if sys.stdout is not None:  # a windowed .exe has no console
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(message)s"))
        sh.setLevel(logging.INFO)
        root.addHandler(sh)


def _steam_libraries() -> list[Path]:
    libs: list[Path] = []
    if sys.platform != "win32":
        return libs
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            libs.append(Path(winreg.QueryValueEx(k, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    extra = []
    for lib in libs:
        vdf = lib / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            import re
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
                extra.append(Path(m.group(1).replace("\\\\", "\\")))
    return libs + extra


def find_log(cfg: config_mod.Config) -> Path | None:
    configured = (cfg.settings.get("log_path") or "").strip()
    if configured:
        p = Path(configured.strip('"'))
        if p.is_dir():
            # a folder was given: use the Client.txt inside it (or in its logs folder)
            for c in (p / "Client.txt", p / "logs" / "Client.txt"):
                if c.exists():
                    return c
            return p / "Client.txt"
        return p
    candidates = [Path(p) for p in STANDARD_LOCATIONS]
    candidates += [lib / "steamapps" / "common" / "Path of Exile" / "logs" / "Client.txt" for lib in _steam_libraries()]
    for c in candidates:
        if c.exists():
            return c
    return None


def daily_backup(keep: int = 7) -> Path | None:
    src = paths.db_path()
    if not src.exists():
        return None
    target = paths.backups_dir() / f"tracker-{datetime.now():%Y-%m-%d}.db"
    if target.exists():
        return target
    s = sqlite3.connect(src)
    d = sqlite3.connect(target)
    with d:
        s.backup(d)
    s.close()
    d.close()
    olds = sorted(paths.backups_dir().glob("tracker-*.db"))
    for old in olds[:-keep]:
        old.unlink(missing_ok=True)
    return target


_LOCK_HANDLE = None


def single_instance(wait: float = 8.0, name: str = "tracker.lock") -> bool:
    """Take an exclusive lock on tracker.lock in the data folder. Returns False
    when another copy of the tracker still holds it after `wait` seconds (two
    copies writing the same database at once corrupts it). The short wait lets
    a restart after an update start while the old copy is closing."""
    global _LOCK_HANDLE
    deadline = time.time() + wait
    while True:
        f = open(paths.data_dir() / name, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            if time.time() >= deadline:
                return False
            time.sleep(0.5)
            continue
        globals().setdefault("_LOCKS", []).append(f)   # keep it open (and locked) for the life of the process
        _LOCK_HANDLE = f
        return True


def release_instance() -> None:
    """Let go of the locks single_instance() took (the restart helper uses this)."""
    for f in globals().pop("_LOCKS", []):
        try:
            f.close()
        except OSError:
            pass


# Files earlier versions left behind that nothing uses any more.
LEFTOVERS_PROJECT = ("poetracker/server.py", "poetracker/web", "poetracker/ggg")
LEFTOVERS_DATA = ("league-logos",)


def remove_leftovers() -> None:
    """Delete files from older versions of the tracker (the old browser
    dashboard, the old league-logo theme...). Your data is never touched."""
    import shutil
    for base, names in ((paths.PACKAGE_DIR.parent, LEFTOVERS_PROJECT), (paths.data_dir(), LEFTOVERS_DATA)):
        for n in names:
            p = base / n
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                elif p.exists():
                    p.unlink()
                else:
                    continue
                log.info("removed leftover %s", p)
            except OSError:
                log.warning("couldn't remove leftover %s", p)
    try:
        (paths.data_dir() / "exports").rmdir()      # only if empty (it was never used)
    except OSError:
        pass


def safety_copy(name: str = "before-rebuild") -> Path | None:
    """A copy of the database taken just before a rebuild wipes the tables."""
    src = paths.db_path()
    if not src.exists():
        return None
    target = paths.backups_dir() / f"tracker-{name}.db"
    s = sqlite3.connect(src)
    d = sqlite3.connect(target)
    with d:
        s.backup(d)
    s.close()
    d.close()
    return target


class Tracker:
    def __init__(self, cfg: config_mod.Config):
        self.cfg = cfg
        self.stop = threading.Event()
        self.log_path = find_log(cfg)
        self.con = db.open_db()
        self.ingestor = ingest.Ingestor(self.con, cfg, self.log_path) if self.log_path else None
        self.busy = threading.Lock()
        self.phase = "starting"
        self.progress = None
        self.clip: captures.ClipboardWatcher | None = None
        self.last_error = None
        self.data_gen = 0          # bumps after a rebuild, so cached results from before are dropped
        self._log_size = None
        self.log_active_at = 0.0   # when Client.txt last grew (the game writes to it all the time while running)

    def status(self) -> dict:
        """Where reading stands. Pages ask for this many times a second, so the
        answer is reused for up to a second."""
        hit = getattr(self, "_status_hit", None)
        now = time.monotonic()
        if hit and now - hit[0] < 1.0 and hit[1]["phase"] == self.phase and hit[1]["data_gen"] == self.data_gen:
            return dict(hit[1])
        out = self._status()
        self._status_hit = (now, out)
        return dict(out)

    def _status(self) -> dict:
        size = None
        if self.log_path and self.log_path.exists():
            size = os.path.getsize(self.log_path)
        try:
            con = db.connect(readonly=True)
            offset = db.get_state(con, "log_offset", 0)
            st = db.get_state(con, "pipeline_state", {}) or {}
            caps = con.execute("SELECT COUNT(*) FROM map_capture").fetchone()[0]
            con.close()
        except Exception:
            offset, st, caps = None, {}, None
        return {
            "phase": self.phase, "progress": self.progress, "log_path": str(self.log_path) if self.log_path else None,
            "log_found": bool(self.log_path and self.log_path.exists()), "log_size": size, "log_offset": offset,
            "last_event_utc": st.get("last_ts"), "captures": caps,
            "clipboard": bool(self.clip and self.clip.is_alive()), "error": self.last_error,
            "now_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "data_gen": self.data_gen,
            "log_quiet_s": (time.time() - self.log_active_at) if self.log_active_at else None,
        }

    def _progress(self, done, total):
        self.progress = round(done / total, 3) if total else None

    def _rules_changed(self) -> str | None:
        """If areas.yaml or log_patterns.yaml changed since the data was built,
        say how to rebuild ("stored" or "log"); otherwise None."""
        import hashlib
        import json
        fp_areas = hashlib.sha1(json.dumps([self.cfg.area_rules, self.cfg.side_mechanics, self.cfg.milestones,
                                             [(l.name, str(l.start)) for l in self.cfg.leagues],
                                             self.cfg.character_leagues], sort_keys=True, default=str).encode()).hexdigest()
        fp_pats = hashlib.sha1(json.dumps([self.cfg.patterns, sorted(self.cfg.npc_ignore)], sort_keys=True).encode()).hexdigest()
        old = db.get_state(self.con, "rules_fp")
        db.set_state(self.con, "rules_fp", [fp_areas, fp_pats])
        self.con.commit()
        has_data = self.con.execute("SELECT 1 FROM area_visit LIMIT 1").fetchone()
        if not has_data:
            return None
        if not old:
            return "stored"   # data built before this check existed
        if old[1] != fp_pats:
            return "log"
        if old[0] != fp_areas:
            return "stored"
        return None

    def catch_up(self) -> None:
        if not self.ingestor:
            self.phase = "no log"
            return
        how = self._rules_changed()
        if how:
            log.info("Area rules or log patterns changed; rebuilding (%s)", how)
            self.rebuild(from_log=(how == "log"))
        try:
            captures.reparse_all(self.con)
            captures.relink_all(self.con, self.cfg)
        except Exception:
            log.exception("re-reading copied maps failed")
        with self.busy:
            self.phase = "reading log"
            t = time.time()
            n = self.ingestor.run_once(self._progress)
            captures.link_pending(self.con, self.cfg)
            self.progress = None
            self.phase = "live"
            if n:
                log.info("Read %s events in %.1fs", n, time.time() - t)

    def _loop(self) -> None:
        try:
            self.catch_up()
        except Exception as e:
            self.last_error = str(e)
            log.exception("initial read failed")
        last_ckpt = time.time()
        while not self.stop.is_set():
            self.stop.wait(2.0)
            if time.time() - last_ckpt > 900:
                self._checkpoint()
                last_ckpt = time.time()
            try:
                size = os.path.getsize(self.log_path) if self.log_path else None
                if size != self._log_size:
                    if self._log_size is not None:
                        self.log_active_at = time.time()
                    self._log_size = size
            except OSError:
                pass
            if not self.ingestor:
                self.log_path = find_log(self.cfg)
                if self.log_path:
                    self.ingestor = ingest.Ingestor(self.con, self.cfg, self.log_path)
                continue
            try:
                with self.busy:
                    if self.ingestor.run_once():
                        captures.link_pending(self.con, self.cfg)
                self.last_error = None
            except Exception as e:
                self.last_error = str(e)
                log.exception("ingest failed")
        self._checkpoint()

    def _checkpoint(self) -> None:
        """Fold the write-ahead log back into tracker.db so it doesn't keep growing."""
        try:
            with self.busy:
                self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            log.debug("checkpoint skipped", exc_info=True)

    def rebuild(self, from_log: bool = False) -> None:
        with self.busy:
            self.phase = "rebuilding"
            try:
                try:
                    if self.con.execute("SELECT 1 FROM area_visit LIMIT 1").fetchone():
                        safety_copy()
                except Exception:
                    log.exception("safety copy before rebuild failed")
                ingest.rebuild(self.con, self.cfg, self.log_path, from_log=from_log, progress=self._progress)
                self.last_error = None
            except Exception as e:
                self.last_error = str(e)
                log.exception("rebuild failed")
            finally:
                self.progress = None
                self.data_gen += 1
                self.phase = "live"

    def reload_config(self) -> None:
        """Pick up edited config files (e.g. a league added in Settings) and
        rebuild if they change how the log is read."""
        cfg = config_mod.load_config()
        with self.busy:
            self.cfg = cfg
            if self.log_path:
                self.ingestor = ingest.Ingestor(self.con, cfg, self.log_path)
            if self.clip:
                self.clip.config = cfg
        how = self._rules_changed()
        if how:
            self.rebuild(from_log=(how == "log"))

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="ingest").start()
        if self.cfg.settings.get("clipboard_capture", True) and sys.platform == "win32":
            self.clip = captures.ClipboardWatcher(db.connect, self.cfg, self.stop)
            self.clip.start()
