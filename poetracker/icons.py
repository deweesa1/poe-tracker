"""Influence, fractured and synthesised symbols for item cards.

The small round symbols come from Path of Building's assets on GitHub
(github.com/PathOfBuildingCommunity/PathOfBuilding, src/Assets); the
Searing Exarch and Eater of Worlds ones are their altar icons as poedb.tw
shows them. The art is Grinding Gear Games'. They're downloaded once into
the data folder (icons/), not shipped with the app."""
from __future__ import annotations

import logging
import threading
import urllib.request

from . import paths

log = logging.getLogger(__name__)

RAW = "https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding/master/src/Assets/"
POEDB = "https://cdn.poedb.tw/image/Art/2DArt/minimap/player/"
FILES = {"crusader": RAW + "crusadericon.png", "elder": RAW + "eldericon.png", "fractured": RAW + "fracturedicon.png",
         "hunter": RAW + "huntericon.png", "redeemer": RAW + "redeemericon.png", "shaper": RAW + "shapericon.png",
         "synthesised": RAW + "synthesisicon.png", "warlord": RAW + "warlordicon.png",
         "searing": POEDB + "CleansingFireAltar.webp", "tangled": POEDB + "TangleAltar.webp"}


def name(key: str) -> str:
    """The saved file's name, e.g. shaper.png or searing.webp."""
    return key + "." + FILES[key].rsplit(".", 1)[-1]
_state = {"busy": False}


def cache_dir():
    d = paths.data_dir() / "icons"
    d.mkdir(exist_ok=True)
    return d


def have(key: str) -> bool:
    return key in FILES and (cache_dir() / name(key)).exists()


def ensure() -> None:
    import time
    if _state["busy"] or all(have(k) for k in FILES) or time.time() - _state.get("tried", 0) < 3600:
        return
    _state["tried"] = time.time()
    _state["busy"] = True

    def run():
        try:
            for k, url in FILES.items():
                if have(k):
                    continue
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "poe-tracker (item symbols)"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        (cache_dir() / name(k)).write_bytes(r.read())
                except Exception as e:          # that one stays a text tag
                    log.warning("item symbol %s download failed: %s", k, e)
        finally:
            _state["busy"] = False
    threading.Thread(target=run, daemon=True, name="icons").start()
