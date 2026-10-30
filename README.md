# PoE Tracker

A personal Path of Exile tracker that runs on your PC. It reads the game's `Client.txt` log while you play and shows a dashboard in your browser: play time, maps, tiers, mechanics, campaign act times, levels, deaths, passive and atlas tree changes, trade whispers, copied maps, and currency snapshots that you enter yourself.

It never touches the game. It only reads the log file and, if you turn it on, the clipboard.

## Start it

1. Double-click **`Start PoE Tracker.bat`**.
   - The first run creates a Python environment in `.venv` and installs the packages in `requirements.txt` (`pyyaml`, `tzdata`, `nicegui`, `pywebview`). It needs internet and takes a minute or two.
   - Your whole log is then read once (about 15 seconds for 200 MB).
2. The dashboard opens in **its own window**. Closing the window stops the tracker.

If something goes wrong, use **`Start PoE Tracker (with log window).bat`** to see the messages.

### Make an .exe

Double-click **`Build exe.bat`** (after the first start). It creates `dist\PoE Tracker\PoE Tracker.exe`. You can move that folder anywhere and pin the exe to the taskbar. The exe isn't digitally signed, so Windows SmartScreen will warn the first time: click *More info → Run anyway*.

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
- **Not possible from the log:** stash contents, gear, gems and links, and the full tree. Those would need GGG's API, which isn't open to new apps.
