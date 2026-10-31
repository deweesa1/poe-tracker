"""Influence, fractured and synthesised symbols for item cards.

The round symbols are Grinding Gear Games' art. Each is fetched from GGG's
own image site first (where the profile's item tooltips come from), then
poedb.tw, and only as a last resort Path of Building's copy on GitHub. The
Searing Exarch and Eater of Worlds ones are their altar icons, as poedb shows
them. They're downloaded once into the data folder (icons/), not shipped
with the app."""
from __future__ import annotations

import logging
import threading
import urllib.request

from . import paths

log = logging.getLogger(__name__)

GGG = "https://web.poecdn.com/image/item/popup/"            # GGG's own site, where the profile's tooltips come from
POEDB = "https://cdn.poedb.tw/image/"
POB = "https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding/master/src/Assets/"
# tried in order; the first that downloads wins (Path of Building's copy is only a last resort)
SOURCES = {
    **{k: [GGG + f"{k}-symbol.png", POEDB + f"item/popup/{k}-symbol.webp", POB + f"{k}icon.png"]
       for k in ("shaper", "elder", "crusader", "redeemer", "hunter", "warlord")},
    "fractured": [GGG + "fractured-symbol.png", POEDB + "item/popup/fractured-symbol.webp", POB + "fracturedicon.png"],
    "synthesised": [GGG + "synthetised-symbol.png", POEDB + "item/popup/synthetised-symbol.webp", POB + "synthesisicon.png"],
    "searing": [POEDB + "Art/2DArt/minimap/player/CleansingFireAltar.webp"],
    "tangled": [POEDB + "Art/2DArt/minimap/player/TangleAltar.webp"],
}
FILES = SOURCES                                    # keys = the symbols we know


def _saved(key: str):
    for f in sorted(cache_dir().glob(key + ".*")):
        if f.suffix in (".png", ".webp"):
            return f
    return None


def name(key: str) -> str:
    """The saved file's name, e.g. shaper.png or searing.webp."""
    f = _saved(key)
    return f.name if f else key + ".png"


_state = {"busy": False}


def cache_dir():
    d = paths.data_dir() / "symbols"
    d.mkdir(exist_ok=True)
    return d


def have(key: str) -> bool:
    return key in SOURCES and _saved(key) is not None


def ensure() -> None:
    import time
    if _state["busy"] or all(have(k) for k in FILES) or time.time() - _state.get("tried", 0) < 3600:
        return
    _state["tried"] = time.time()
    _state["busy"] = True

    def run():
        try:
            for k, urls in SOURCES.items():
                if have(k):
                    continue
                for url in urls:
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "poe-tracker (item symbols)"})
                        with urllib.request.urlopen(req, timeout=30) as r:
                            data = r.read()
                        if len(data) > 100:
                            (cache_dir() / (k + "." + url.rsplit(".", 1)[-1])).write_bytes(data)
                            break
                    except Exception as e:      # try the next source; none = a text tag
                        log.info("item symbol %s from %s failed: %s", k, url, e)
        finally:
            _state["busy"] = False
    threading.Thread(target=run, daemon=True, name="icons").start()
