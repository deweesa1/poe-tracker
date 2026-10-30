"""Classifying area ids (from areas.yaml) and reading act numbers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

CAMPAIGN_RE = re.compile(r"^(?P<part>\d)_(?P<act>\d+)_")


@dataclass(frozen=True)
class AreaInfo:
    kind: str                 # town | campaign | map | boss | activity | side | other
    act: int | None = None    # campaign act (1-10, 11 = epilogue town)
    activity: str | None = None


class AreaClassifier:
    def __init__(self, rules: list[dict], side_mechanics: dict[str, str]):
        self.rules = [(re.compile(r["match"]), r["kind"], r.get("activity")) for r in rules]
        self.side = [(re.compile(k), v) for k, v in side_mechanics.items()]
        self.classify = lru_cache(maxsize=4096)(self._classify)

    def _classify(self, area_id: str, level: int) -> AreaInfo:
        act = None
        m = CAMPAIGN_RE.match(area_id)
        if m:
            act = int(m["act"])
        for rx, kind, activity in self.rules:
            if rx.search(area_id):
                return AreaInfo(kind, act if kind in ("campaign", "town") else None, activity)
        return AreaInfo("side" if level >= 68 else "other", None, None)

    def side_mechanic(self, area_id: str) -> str | None:
        for rx, name in self.side:
            if rx.search(area_id):
                return name
        return None


def map_tier(level: int | None) -> int | None:
    if level is None or level < 68:
        return None
    return min(level - 67, 17)
