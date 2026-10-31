"""Influence, fractured and synthesised symbols for item cards.

The small round symbols come from Path of Building's assets on GitHub
(github.com/PathOfBuildingCommunity/PathOfBuilding, src/Assets); the art
is Grinding Gear Games'. They're downloaded once into the data folder
(icons/), not shipped with the app."""
from __future__ import annotations

import logging
import threading
import urllib.request

from . import paths

log = logging.getLogger(__name__)

RAW = "https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding/master/src/Assets/"
FILES = {"crusader": "crusadericon.png", "elder": "eldericon.png", "fractured": "fracturedicon.png",
         "hunter": "huntericon.png", "redeemer": "redeemericon.png", "shaper": "shapericon.png",
         "synthesised": "synthesisicon.png", "warlord": "warlordicon.png"}
_state = {"busy": False}


def cache_dir():
    d = paths.data_dir() / "icons"
    d.mkdir(exist_ok=True)
    return d


def have(key: str) -> bool:
    return key in FILES and (cache_dir() / f"{key}.png").exists()


def ensure() -> None:
    if _state["busy"] or all(have(k) for k in FILES):
        return
    _state["busy"] = True

    def run():
        try:
            for k, f in FILES.items():
                if have(k):
                    continue
                req = urllib.request.Request(RAW + f, headers={"User-Agent": "poe-tracker (item symbols)"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    (cache_dir() / f"{k}.png").write_bytes(r.read())
        except Exception as e:
            log.warning("item symbols download failed: %s", e)
        finally:
            _state["busy"] = False
    threading.Thread(target=run, daemon=True, name="icons").start()
