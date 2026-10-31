# PoE Tracker

> **Disclaimer:** PoE Tracker is an unofficial, fan-made tool. It is not affiliated with, endorsed by, or sponsored by Grinding Gear Games in any way. Path of Exile and all related names, artwork and game data are trademarks or copyrights of Grinding Gear Games.

A personal Path of Exile tracker that runs on your PC. It reads the game's `Client.txt` log while you play and shows a dashboard in your browser: play time, maps, tiers, mechanics, campaign act times, levels, deaths, passive and atlas tree changes, trade whispers, copied maps, and currency snapshots that you enter yourself.

It never touches the game. It only reads the log file and, if you turn it on, the clipboard.

## Install

1. Download **PoE-Tracker-Setup.exe** from the [latest release](https://github.com/deweesa1/poe-tracker/releases/latest) and run it.
   Windows SmartScreen warns the first time (the installer isn't code-signed): click *More info → Run anyway*.
2. It installs for your user only (no admin prompt) into `%LOCALAPPDATA%\Programs\PoE Tracker`, with its own copy of Python, and adds **PoE Tracker** to the Start menu (and the desktop if you tick it). Pin it to the taskbar like any app.
3. The tracker updates itself: when *Update ready* appears at the bottom of the side menu, click it. Only the files that changed are downloaded.

Uninstall from Windows Settings → Apps. Your data in `%LOCALAPPDATA%\PoETracker` is kept.

The Start menu also has **PoE Tracker (with log window)**, which shows the app's messages.

Developer mode (a *Developer* card in Settings that forces League Start to any league and phase) is for development copies: `tools\Start PoE Tracker (dev).bat`. An installed copy only turns it on with `dev_mode: true` in its `settings.yaml`.

## Run from source (development)

1. Double-click **`Start PoE Tracker.bat`**. The first run creates a Python environment in `.venv` and installs `requirements.txt` (needs Python 3.13+ and internet).
2. `tools\` has the other ways in: with a log window, developer mode, running the tests, and updating a source copy from GitHub (needs Git).

A source copy is a git clone and updates with git; an installed copy updates file by file from GitHub (like Path of Building), no Git needed.

### Build the installer

GitHub builds it: push a tag like `v0.2.0` and the *Build installer* workflow publishes `PoE-Tracker-Setup.exe` as a release. To build it on your own PC: Python 3.13 and Inno Setup 6, then `pwsh installer\build.ps1 -Version 0.2.0`.

### From a terminal

```powershell
.venv\Scripts\python -m poetracker              # start (own window)
.venv\Scripts\python -m poetracker run --browser   # open in the web browser instead
.venv\Scripts\python -m poetracker status       # where things are, row counts
.venv\Scripts\python -m poetracker rebuild      # recalculate after editing config
.venv\Scripts\python -m unittest discover -s tests -v   # run the tests
```

## In game

- **NPC dialogue:** Options → UI → *Output Dialogue To Chat* must be on. Mechanics like Einhar or Delirium are detected from dialogue.
- **Copied maps:** with the tracker running, hover a map and press **Ctrl+C** (the game's own copy key). The tracker doesn't add any hotkey; it just notices map text on the clipboard. The map is saved with its quantity, pack size and mods, then linked to the next map you open within 10 minutes. Maps you price-check with Awakened PoE Trade get captured the same way. You can also paste map text under *Maps → Copied maps*.
- **Currency:** enter what you have on the *Currency* page now and then. It works out profit per hour played between snapshots.

## Where your data lives

`%LOCALAPPDATA%\PoETracker\`

| | |
|---|---|
| `tracker.db` | the SQLite database (open it with DB Browser for SQLite, DuckDB, pandas…) |
| `config\*.yaml` | your editable settings, league dates, area rules, NPC → mechanic list |
| `prefs.json` | the dashboard's remembered filters |
| `backups\` | a copy of the database from each day you start the tracker (last 7 are kept) |
| `poetracker.log` | the app's own log, useful if something goes wrong |

## How it works (medallion layers)

- **Bronze:** every relevant raw log line, stored as-is in `bronze_log_line`, keyed by (log generation, byte offset).
- **Silver:** typed tables built from those lines: `game_session`, `login`, `character`, `area_visit`, `run`, `level_up`, `death`, `passive_change`, `afk_period`, `run_speaker`, `whisper`, plus `map_capture` and `currency_snapshot`.
- **Gold:** SQL views (`v_visit_active`, `v_own_character`) and `poetracker/metrics.py`, which turn silver rows into dashboard numbers.

Code map:

| File | Job |
|---|---|
| `ingest.py` | reads Client.txt from the last offset, detects resets, writes bronze, commits state with the offset |
| `logline.py` | splits a line into time/pid/message and matches `log_patterns.yaml` |
| `pipeline.py` | the event bus: detectors register with `@on("kind")` |
| `detectors/` | sessions & logins, visits & runs, character identification, passives/AFK/NPC/trades |
| `areas.py` | area id → town / campaign / map / boss / activity / side area (`areas.yaml`) |
| `captures.py` | copied-map parsing, clipboard watcher, linking to runs |
| `metrics.py` | everything the dashboard shows |
| `ui/` | the NiceGUI dashboard: `layout.py` (frame, filters), `widgets.py` (tiles, tables, charts), `pages.py` (every page) |

## What the log can and can't tell

- **Character:** level-ups and deaths name your character. A login with neither is assumed to be the previous character. If you hop onto an alt without levelling or dying, that time can land on the wrong character. Players who join or leave your area are recognised as other people.
- **Time:** "played" means time in areas minus AFK periods. Time inside a map counts every portal entry and side area of that map instance; hideout time between portals doesn't count.
- **Leagues:** a character belongs to the league that was running when it first appeared. Start dates are in `config\leagues.yaml`. Add each new league there when it launches, or pin a character to a league.
- **Passive and atlas trees:** only points changed while the log was recording are known.
- **Not possible from the log:** stash contents, gear, gems and links.
- **Profile snapshots:** with your account name (Name#1234) in Settings and a public Characters tab, the tracker reads
  gear, jewels and the passive tree from your pathofexile.com profile (the same public profile Path of Building's
  "Import by account name" reads). During league start this happens at the end of each act, every 10 levels while
  mapping, the first yellow and red map, and each Voidstone; afterwards there's a Snapshot now button on the Characters
  page. One request at a time, following the site's rate limits; no login is used and snapshots stay on your PC.

## Credits

See the disclaimer at the top (also in `DISCLAIMER.txt`). The Atlas Tree page draws the tree from GGG's official
[atlastree-export](https://github.com/grindinggear/atlastree-export), downloaded on first use into the data folder
(nothing of it is shipped with the app); passive names come from GGG's
[skilltree-export](https://github.com/grindinggear/skilltree-export) the same way. Atlas node ids are linked with [RePoE](https://github.com/repoe-fork/repoe).
