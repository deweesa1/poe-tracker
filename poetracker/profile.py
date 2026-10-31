"""Snapshots of a character from its public pathofexile.com profile.

The profile pages on pathofexile.com read a character's gear, jewels and
passive tree from the same addresses Path of Building's "Import by account
name" uses (character-window/get-items and get-passive-skills). They work
without signing in when the account's Characters tab is public. They aren't
part of GGG's official API ("tolerated, not supported"), so this asks
politely: one request at a time, an identifying User-Agent, and it follows the
rate limits the server sends back with every answer.

During league start a snapshot is taken shortly after each milestone
(metrics.snapshot_triggers); after league start the Characters page has a
"Snapshot now" button. Nothing is sent anywhere else and no login is used.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone

from . import db, metrics, paths

log = logging.getLogger(__name__)

BASE = "https://www.pathofexile.com/character-window/"
UA = "PoETracker/1.0 (personal tracker; github.com/deweesa1/poe-tracker)"
DELAY_S = 75          # wait after a milestone so the game has saved the character
FRESH_S = 30 * 60     # a milestone older than this when first seen is skipped (app was closed)
POLL_S = 30


class ProfileError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_s(ts: str) -> float:
    return (datetime.now(timezone.utc) - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds()


# ---- talking to pathofexile.com --------------------------------------------
_net = threading.Lock()
_wait_until = {"t": 0.0}


def _respect_limits(headers) -> None:
    """Read X-Rate-Limit-<rule> ("max:period:penalty,...") and its -State
    ("hits:period:active_penalty,...") and wait before the next call when close."""
    wait = 2.0
    for k in headers.keys():
        if not k.lower().startswith("x-rate-limit-") or k.lower().endswith("-state") or k.lower() == "x-rate-limit-policy" \
                or k.lower() == "x-rate-limit-rules":
            continue
        state = headers.get(k + "-State") or ""
        for rule, cur in zip(headers.get(k, "").split(","), state.split(",")):
            try:
                mx, period, _ = (int(x) for x in rule.split(":"))
                hits, _, penalty = (int(x) for x in cur.split(":"))
            except ValueError:
                continue
            if penalty:
                wait = max(wait, penalty)
            elif hits >= mx - 1:
                wait = max(wait, period)
    _wait_until["t"] = time.time() + wait


def _get(endpoint: str, params: dict) -> dict:
    with _net:
        pause = _wait_until["t"] - time.time()
        if pause > 0:
            time.sleep(min(pause, 60))
        url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                _respect_limits(r.headers)
                raw = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
            except ValueError:
                log.warning("pathofexile.com sent something that isn't JSON for %s: %s", endpoint, raw[:300].replace("\n", " "))
                raise ProfileError("pathofexile.com answered with a web page instead of data (its bot protection, "
                                   "or the site is down). Try again in a few minutes.")
        except urllib.error.HTTPError as e:
            _respect_limits(e.headers)
            if e.code == 429:
                _wait_until["t"] = time.time() + float(e.headers.get("Retry-After") or 60)
                raise ProfileError("pathofexile.com asked to slow down; it will try again in a minute") from e
            body = ""
            try:
                body = e.read(2000).decode("utf-8", "replace")
            except Exception:
                pass
            log.warning("pathofexile.com %s on %s: %s", e.code, endpoint, body[:300].replace("\n", " "))
            if e.code == 403 and "<html" in body.lower():
                raise ProfileError("pathofexile.com turned the request away (its bot protection). Try again in a "
                                   "few minutes; if it keeps happening, tell me the message in poetracker.log.") from e
            if e.code == 403:
                raise ProfileError("The profile is private. On pathofexile.com: My Account → Privacy Settings, "
                                   "untick \"Hide characters\" (the Characters tab must be public).") from e
            if e.code == 404:
                raise ProfileError("Account or character not found. Use the full account name with its #1234.") from e
            raise ProfileError(f"pathofexile.com answered {e.code}") from e
        except urllib.error.URLError as e:
            raise ProfileError("Couldn't reach pathofexile.com (offline?)") from e
        except OSError as e:                         # timed out, connection reset...
            raise ProfileError(f"pathofexile.com didn't answer in time ({type(e).__name__}). Try again shortly.") from e
    if isinstance(data, dict) and data.get("error"):
        msg = (data["error"] or {}).get("message") or "unknown error"
        raise ProfileError(f"pathofexile.com: {msg}")
    return data


def characters(account: str, realm: str = "pc") -> list[dict]:
    """The account's characters (checks the account name and that the profile is public)."""
    data = _get("get-characters", {"accountName": account, "realm": realm})
    return data if isinstance(data, list) else []


def fetch(account: str, character: str, realm: str = "pc") -> tuple[dict, dict]:
    items = _get("get-items", {"accountName": account, "character": character, "realm": realm})
    passives = _get("get-passive-skills", {"accountName": account, "character": character, "realm": realm})
    return items, passives


# ---- storing ---------------------------------------------------------------
def _pack(d: dict | None) -> bytes | None:
    return zlib.compress(json.dumps(d, separators=(",", ":")).encode("utf-8"), 6) if d is not None else None


def unpack(b: bytes | None) -> dict | None:
    return json.loads(zlib.decompress(b).decode("utf-8")) if b else None


def _fingerprint(items: dict, passives: dict) -> str:
    keep = {"items": [(i.get("inventoryId"), i.get("id")) for i in items.get("items") or []],
            "hashes": sorted(passives.get("hashes") or []), "ex": sorted(passives.get("hashes_ex") or []),
            "mastery": passives.get("mastery_effects"),
            "jewels": [(i.get("x"), i.get("id")) for i in passives.get("items") or []]}
    return hashlib.sha1(json.dumps(keep, sort_keys=True).encode()).hexdigest()


def take(con, account: str, character: str, league: str | None, trigger: str, label: str,
         event_utc: str | None = None) -> dict:
    """Read the profile and store a snapshot row. Returns the row's summary."""
    row = {"character_name": character, "league": league, "trigger": trigger, "label": label,
           "event_utc": event_utc or _now(), "ts_utc": None, "status": "ok", "error": None}
    try:
        items, passives = fetch(account, character)
        ch = items.get("character") or {}
        h = _fingerprint(items, passives)
        prev = con.execute("SELECT hash FROM profile_snapshot WHERE character_name=? AND league IS ? AND status='ok' "
                           "ORDER BY ts_utc DESC LIMIT 1", (character, league)).fetchone()
        same = bool(prev and prev[0] == h)
        row.update(ts_utc=_now(), level=ch.get("level"), cls=ch.get("class"), hash=h,
                   status="same" if same else "ok",
                   items=None if same else _pack(items), passives=None if same else _pack(passives))
    except ProfileError as e:
        row.update(ts_utc=_now(), status="error", error=str(e), level=None, cls=None, hash=None, items=None, passives=None)
    con.execute("""INSERT INTO profile_snapshot(character_name, league, trigger, label, event_utc, ts_utc, level, class,
                   items, passives, hash, status, error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row["character_name"], row["league"], row["trigger"], row["label"], row["event_utc"], row["ts_utc"],
                 row["level"], row["cls"], row["items"], row["passives"], row["hash"], row["status"], row["error"]))
    con.commit()
    return {k: row[k] for k in ("character_name", "trigger", "label", "status", "error", "level")}


def snapshots(con, character: str, league: str | None) -> list[dict]:
    rows = con.execute("""SELECT id, trigger, label, event_utc, ts_utc, level, class, status, error
                          FROM profile_snapshot WHERE character_name=? AND league IS ? ORDER BY event_utc, id""",
                       (character, league)).fetchall()
    return [dict(zip(("id", "trigger", "label", "event_utc", "ts_utc", "level", "class", "status", "error"), r)) for r in rows]


def load(con, snap_id: int) -> dict | None:
    """One snapshot with its data; a 'same' row borrows the last stored data before it."""
    r = con.execute("SELECT id, character_name, league, label, event_utc, ts_utc, level, class, status, items, passives "
                    "FROM profile_snapshot WHERE id=?", (snap_id,)).fetchone()
    if not r:
        return None
    out = dict(zip(("id", "character", "league", "label", "event_utc", "ts_utc", "level", "class", "status"), r[:9]))
    items, passives = r[9], r[10]
    if out["status"] == "same":
        p = con.execute("SELECT items, passives FROM profile_snapshot WHERE character_name=? AND league IS ? AND status='ok' "
                        "AND (event_utc < ? OR (event_utc = ? AND id < ?)) ORDER BY event_utc DESC, id DESC LIMIT 1",
                        (out["character"], out["league"], out["event_utc"], out["event_utc"], snap_id)).fetchone()
        items, passives = (p[0], p[1]) if p else (None, None)
    out["items"], out["passives"] = unpack(items), unpack(passives)
    return out


# ---- the background worker -------------------------------------------------
class Snapshotter:
    """Watches for league start milestones and takes snapshots; also runs the
    "Snapshot now" requests from the Characters page."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.state: dict = {"busy": None, "last": None, "error": None, "done": 0}
        self._manual: list[tuple[str, str | None]] = []
        self._kick = threading.Event()
        self._seen: set = set()

    @property
    def account(self) -> str:
        return str((self.cfg.settings or {}).get("poe_account") or "").strip()

    @property
    def auto(self) -> bool:
        return bool((self.cfg.settings or {}).get("profile_snapshots", True))

    def request(self, character: str, league: str | None) -> None:
        self._manual.append((character, league))
        self._kick.set()

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="profile-snapshots").start()

    def _loop(self) -> None:
        time.sleep(15)
        while True:
            try:
                self._tick()
            except Exception:
                log.exception("profile snapshot check failed")
            self._kick.wait(POLL_S)
            self._kick.clear()

    def _run(self, con, character, league, key, label, event_utc) -> None:
        self.state["busy"] = character
        try:
            res = take(con, self.account, character, league, key, label, event_utc)
        except Exception as e:                      # never leave the page waiting
            log.exception("profile snapshot failed")
            res = {"character_name": character, "trigger": key, "status": "error", "error": f"Snapshot failed: {e}"}
        log.info("profile snapshot %s %s: %s %s", character, key, res.get("status"), res.get("error") or "")
        self.state["last"] = res
        self.state["busy"] = None
        self.state["done"] = self.state.get("done", 0) + 1

    def _tick(self) -> None:
        if not self.account:
            if self._manual:
                self._manual.clear()
                self.state["last"] = {"status": "error", "error": "Add your account name in Settings → Profile Snapshots."}
                self.state["done"] = self.state.get("done", 0) + 1
            return
        con = db.connect(paths.db_path())
        try:
            while self._manual:
                ch, lg = self._manual.pop(0)
                self._run(con, ch, lg, "manual", "Snapshot by you", None)
            if not self.auto:
                return
            league = metrics.current_league(self.cfg)
            done, errs = set(), {}
            for trig, ch, status, ts in con.execute(
                    "SELECT trigger, character_name, status, ts_utc FROM profile_snapshot WHERE league IS ?", (league,)):
                if status == "error":
                    n, last = errs.get((trig, ch), (0, ""))
                    errs[(trig, ch)] = (n + 1, max(last, ts))
                else:
                    done.add((trig, ch))
            for t in metrics.snapshot_triggers(con, self.cfg, league):
                k = (t["key"], t["character"])
                n, last = errs.get(k, (0, None))
                if k in done or n >= 3 or (last and _age_s(last) < 300):
                    continue                      # taken, or failed: up to 3 tries, 5 minutes apart
                age = _age_s(t["event_utc"])
                if age > FRESH_S and k not in self._seen:
                    continue                      # it happened while the tracker wasn't watching
                self._seen.add(k)
                if age < DELAY_S:
                    continue                      # give the game a moment to save the character
                self._run(con, t["character"], league, t["key"], t["label"], t["event_utc"])
        finally:
            self.state["busy"] = None
            con.close()
