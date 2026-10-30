"""Where things live on disk.

Data (database, your editable config copies, app logs) goes in the data
folder: %LOCALAPPDATA%\\PoETracker on Windows, ~/.poetracker elsewhere.
Set the POETRACKER_HOME environment variable to use a different folder
(the tests do this).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULTS_DIR = PACKAGE_DIR / "defaults"
MIGRATIONS_DIR = PACKAGE_DIR / "migrations"

CONFIG_FILES = ("settings.yaml", "leagues.yaml", "log_patterns.yaml", "areas.yaml", "mechanics.yaml", "milestones.yaml")


def data_dir() -> Path:
    env = os.environ.get("POETRACKER_HOME")
    if env:
        base = Path(env)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "PoETracker"
    else:
        base = Path.home() / ".poetracker"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_dir() -> Path:
    d = data_dir() / "config"
    d.mkdir(exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "tracker.db"


def backups_dir() -> Path:
    d = data_dir() / "backups"
    d.mkdir(exist_ok=True)
    return d


def app_log_path() -> Path:
    return data_dir() / "poetracker.log"
