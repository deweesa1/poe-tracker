"""Loading settings and the YAML config files.

On first run the defaults are copied into the data folder's config\\ so you
can edit them. Each file is merged over its default, so new keys added in an
update still have values.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import paths


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _deep_merge(base.get(k), v) if k in base else v
        return out
    return base if override is None else override


# sha1 of earlier default files. A user copy that still matches one of these
# was never edited, so it is safe to replace with the newer default.
OLD_DEFAULTS = {
    "areas.yaml": {"93a84d5fa5c4391f313dcb68fd700804288b7b10", "5082fff89c5b19732b54222dfec719d9d679168f"},
    "mechanics.yaml": {"ef061ed58a3b9d1447d66f29ad9c89367cf6ff6d", "496173c9f9d857a6efcab155affa87b0d157415e",
                       "8ee75f84eebdbdff3f1b2ac19fac4f5f6f2585d7"},
    "log_patterns.yaml": {"060a062dbfcbaa5c11b943dc1c9d5fa2179e7838", "3d63e084bd5858f03398cc067787499c015b785c"},
    "milestones.yaml": {"18eaea90326edae6cfe7303d00cd1f116df1ed02", "806edb9734d58a5fb28dab6dd75a0fd0906a36f9"},
}


def ensure_user_config() -> None:
    import hashlib
    for name in paths.CONFIG_FILES:
        target = paths.config_dir() / name
        if not target.exists():
            shutil.copyfile(paths.DEFAULTS_DIR / name, target)
        elif hashlib.sha1(target.read_bytes()).hexdigest() in OLD_DEFAULTS.get(name, ()):
            shutil.copyfile(paths.DEFAULTS_DIR / name, target)


def load_yaml(name: str, merge: bool = False) -> dict:
    """Read a config file from the user's config folder.

    merge=True (settings.yaml) fills in keys missing from the user's copy with
    the defaults. Other files are used exactly as the user wrote them, so
    deleting an entry really removes it.
    """
    default = yaml.safe_load((paths.DEFAULTS_DIR / name).read_text(encoding="utf-8")) or {}
    user_file = paths.config_dir() / name
    if not user_file.exists():
        return default
    user = yaml.safe_load(user_file.read_text(encoding="utf-8")) or {}
    if merge:
        return _deep_merge(default, user)
    return {**default, **user}


def parse_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class League:
    name: str
    start: datetime
    end: datetime | None = None


@dataclass
class Config:
    settings: dict
    leagues: list[League]
    character_leagues: dict[str, str]
    patterns: dict
    npc_ignore: set[str]
    area_rules: list[dict]
    side_mechanics: dict[str, str]
    speakers: dict[str, str]
    milestones: dict = field(default_factory=dict)
    content_rules: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    # convenience accessors
    @property
    def timezone(self) -> str:
        return self.settings.get("timezone") or "America/Chicago"

    def league_for(self, when: datetime, character: str | None = None) -> str:
        if character and character in self.character_leagues:
            return self.character_leagues[character]
        found = "Unknown"
        for lg in self.leagues:
            if when >= lg.start and (lg.end is None or when < lg.end):
                found = lg.name
        return found


def load_config() -> Config:
    ensure_user_config()
    settings = load_yaml("settings.yaml", merge=True)
    lg = load_yaml("leagues.yaml")
    leagues = sorted(
        (League(x["name"], parse_utc(x["start"])) for x in lg.get("leagues") or []),
        key=lambda l: l.start,
    )
    for a, b in zip(leagues, leagues[1:]):
        a.end = b.start
    pats = load_yaml("log_patterns.yaml")
    areas = load_yaml("areas.yaml")
    mech = load_yaml("mechanics.yaml")
    return Config(
        settings=settings,
        leagues=leagues,
        character_leagues=dict(lg.get("characters") or {}),
        patterns=pats.get("patterns") or {},
        npc_ignore=set(pats.get("npc_ignore") or []),
        area_rules=areas.get("rules") or [],
        side_mechanics=areas.get("side_mechanics") or {},
        speakers=mech.get("speakers") or {},
        milestones=load_yaml("milestones.yaml"),
        content_rules=areas.get("content") or [],
        extra={"league_colors": {x["name"]: x["color"] for x in lg.get("leagues") or [] if x.get("color")}},
    )


def save_settings(updates: dict) -> None:
    """Write changed settings back to the user's settings.yaml.

    Comments in the file are lost when the app rewrites it, so the app only
    does this when you press Save on the Settings page.
    """
    ensure_user_config()
    target: Path = paths.config_dir() / "settings.yaml"
    current = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    current = _deep_merge(current, updates)
    target.write_text(yaml.safe_dump(current, sort_keys=False, allow_unicode=True), encoding="utf-8")


def add_league(name: str, start_utc: datetime) -> None:
    """Add (or move) a league in the user's leagues.yaml."""
    ensure_user_config()
    target: Path = paths.config_dir() / "leagues.yaml"
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    lst = [x for x in (data.get("leagues") or []) if x.get("name") != name]
    lst.append({"name": name, "start": start_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    lst.sort(key=lambda x: str(x["start"]))
    data["leagues"] = lst
    data.setdefault("characters", {})
    header = ("# League start times in UTC. A character belongs to the league whose window\n"
              "# contains the first time it appears in the log. A league ends when the next one starts.\n"
              "# Pin characters to a league under 'characters' when the date rule gets it wrong.\n")
    target.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
