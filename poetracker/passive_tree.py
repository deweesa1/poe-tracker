"""Names and text for the character passive tree, from Grinding Gear Games'
official skilltree-export (github.com/grindinggear/skilltree-export).

Downloaded the first time a profile snapshot is opened (not shipped with the
app) and kept as a small index in the data folder: node number -> name, kind,
ascendancy and stats, plus mastery effect texts. Refreshed every few days.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request

from . import paths

log = logging.getLogger(__name__)

URL = "https://raw.githubusercontent.com/grindinggear/skilltree-export/master/data.json"
REFRESH_S = 3 * 86400
_state = {"busy": False, "error": None, "index": None, "mtime": 0.0}


def _file():
    d = paths.data_dir() / "passivetree"
    d.mkdir(exist_ok=True)
    return d / "index.json"


def ensure() -> None:
    f = _file()
    if _state["busy"] or (f.exists() and time.time() - f.stat().st_mtime < REFRESH_S):
        return
    _state["busy"] = True
    threading.Thread(target=_download, daemon=True, name="passive-tree").start()


def _download() -> None:
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "poe-tracker (passive tree names)"})
        with urllib.request.urlopen(req, timeout=90) as r:
            tree = json.loads(r.read())
        idx = build(tree)
        f = _file()
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, separators=(",", ":")), encoding="utf-8")
        tmp.replace(f)
        _state["error"] = None
    except Exception as e:
        log.warning("passive tree download failed: %s", e)
        _state["error"] = f"Couldn't download the passive tree names ({type(e).__name__})."
    finally:
        _state["busy"] = False


def build(tree: dict) -> dict:
    nodes, effects = {}, {}
    for k, n in tree["nodes"].items():
        if k == "root":
            continue
        kind = ("keystone" if n.get("isKeystone") else "mastery" if n.get("isMastery") else
                "jewel" if n.get("isJewelSocket") else "notable" if n.get("isNotable") else
                "start" if n.get("classStartIndex") is not None else "normal")
        nodes[k] = [n.get("name") or "", kind, n.get("ascendancyName") or "", n.get("stats") or []]
        for e in n.get("masteryEffects") or []:
            effects[str(e["effect"])] = [n.get("name") or "", e.get("stats") or []]
    return {"nodes": nodes, "effects": effects}


def index() -> dict | None:
    f = _file()
    if not f.exists():
        return None
    mt = f.stat().st_mtime
    if _state["index"] is None or mt != _state["mtime"]:
        try:
            _state["index"], _state["mtime"] = json.loads(f.read_text(encoding="utf-8")), mt
        except Exception:
            return None
    return _state["index"]


def status() -> dict:
    return {"ready": _file().exists(), "busy": _state["busy"], "error": _state["error"]}
