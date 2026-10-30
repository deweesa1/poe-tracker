-- Silver layer: cleaned, typed facts derived from the log.
-- All times are UTC ISO-8601 text ("2026-07-28T21:57:00Z"); "day" is the
-- local calendar date from the log, used for daily grouping.
-- (source, source_offset) is the natural key of the log line a row came
-- from, so re-processing the same line can never create a duplicate.

CREATE TABLE app_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Bronze layer: every relevant raw line, exactly as read, so the silver
-- tables can be rebuilt after a parser or config change.
CREATE TABLE bronze_log_line (
    source        TEXT    NOT NULL,
    source_offset INTEGER NOT NULL,
    text          TEXT    NOT NULL,
    PRIMARY KEY (source, source_offset)
) WITHOUT ROWID;

CREATE TABLE league (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    start_utc TEXT,
    end_utc   TEXT
);

CREATE TABLE character (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    class      TEXT,
    league_id  INTEGER REFERENCES league(id),
    first_seen TEXT,
    last_seen  TEXT,
    level      INTEGER,
    other      INTEGER NOT NULL DEFAULT 0,   -- 1 = someone else (joined/left your area)
    UNIQUE (name, league_id)
);

-- One game launch (from "LOG FILE OPENING" to the last line before the next).
CREATE TABLE game_session (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    pid           INTEGER,
    start_utc     TEXT NOT NULL,
    end_utc       TEXT,
    day           TEXT,
    UNIQUE (source, source_offset)
);

-- One login to a character inside a session (character select -> play).
CREATE TABLE login (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    session_id    INTEGER REFERENCES game_session(id),
    start_utc     TEXT NOT NULL,
    character_id  INTEGER REFERENCES character(id),
    char_source   TEXT,               -- 'log' (named in this login) | 'inferred' | 'setting'
    UNIQUE (source, source_offset)
);

-- A run: one map instance (or boss / activity), including side areas
-- entered from it and portals back into it.
CREATE TABLE run (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    session_id   INTEGER REFERENCES game_session(id),
    login_id     INTEGER REFERENCES login(id),
    character_id INTEGER REFERENCES character(id),
    kind         TEXT NOT NULL,       -- map | boss | activity | other
    activity     TEXT,
    area_id      TEXT NOT NULL,
    area_name    TEXT,
    area_level   INTEGER,
    tier         INTEGER,
    seed         INTEGER,
    start_utc    TEXT NOT NULL,
    end_utc      TEXT,
    day          TEXT,
    atlas_hash   TEXT,
    UNIQUE (source, source_offset)
);

CREATE TABLE area_visit (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    session_id    INTEGER REFERENCES game_session(id),
    login_id      INTEGER REFERENCES login(id),
    character_id  INTEGER REFERENCES character(id),
    run_id        INTEGER REFERENCES run(id),
    area_id       TEXT NOT NULL,
    area_name     TEXT,
    area_level    INTEGER,
    seed          INTEGER,
    kind          TEXT NOT NULL,
    act           INTEGER,
    start_utc     TEXT NOT NULL,
    end_utc       TEXT,
    day           TEXT,
    UNIQUE (source, source_offset)
);
CREATE INDEX ix_visit_char ON area_visit(character_id, start_utc);
CREATE INDEX ix_visit_run ON area_visit(run_id);
CREATE INDEX ix_visit_login ON area_visit(login_id);

CREATE TABLE level_up (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    character_id  INTEGER REFERENCES character(id),
    class         TEXT,
    level         INTEGER NOT NULL,
    ts_utc        TEXT NOT NULL,
    visit_id      INTEGER REFERENCES area_visit(id),
    UNIQUE (source, source_offset)
);

CREATE TABLE death (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    character_id  INTEGER REFERENCES character(id),
    ts_utc        TEXT NOT NULL,
    visit_id      INTEGER REFERENCES area_visit(id),
    run_id        INTEGER REFERENCES run(id),
    UNIQUE (source, source_offset)
);

-- Passive / atlas / mastery point changes, in order.
CREATE TABLE passive_change (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    character_id  INTEGER REFERENCES character(id),
    login_id      INTEGER REFERENCES login(id),
    league        TEXT,
    tree          TEXT NOT NULL,      -- character | atlas | mastery
    action        TEXT NOT NULL,      -- allocated | unallocated
    node_id       TEXT NOT NULL,
    name          TEXT,
    ts_utc        TEXT NOT NULL,
    UNIQUE (source, source_offset)
);

CREATE TABLE afk_period (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    session_id    INTEGER REFERENCES game_session(id),
    start_utc     TEXT NOT NULL,
    end_utc       TEXT,
    UNIQUE (source, source_offset)
);

-- NPC lines heard during runs (mapped to mechanics at query time, so
-- editing mechanics.yaml needs no rebuild).
CREATE TABLE run_speaker (
    run_id    INTEGER NOT NULL REFERENCES run(id),
    speaker   TEXT NOT NULL,
    lines     INTEGER NOT NULL DEFAULT 0,
    first_utc TEXT,
    PRIMARY KEY (run_id, speaker)
);

CREATE TABLE whisper (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    ts_utc        TEXT NOT NULL,
    day           TEXT,
    direction     TEXT NOT NULL,      -- From | To
    who           TEXT,
    message       TEXT,
    trade_kind    TEXT,               -- buy_offer | null
    item          TEXT,
    price_amount  REAL,
    price_currency TEXT,
    trade_league  TEXT,
    UNIQUE (source, source_offset)
);

CREATE TABLE trade_result (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    ts_utc        TEXT NOT NULL,
    result        TEXT NOT NULL,
    UNIQUE (source, source_offset)
);

-- Copied map text (Ctrl+C on a map in game).
CREATE TABLE map_capture (
    id          INTEGER PRIMARY KEY,
    ts_utc      TEXT NOT NULL,
    raw_hash    TEXT NOT NULL,
    raw_text    TEXT NOT NULL,
    rarity      TEXT,
    name        TEXT,
    base        TEXT,
    tier        INTEGER,
    quantity    INTEGER,
    item_rarity INTEGER,
    pack_size   INTEGER,
    properties  TEXT,                 -- JSON of every "Name: +N%" property
    mods        TEXT,                 -- JSON list of mod lines
    corrupted   INTEGER,
    identified  INTEGER,
    run_id      INTEGER REFERENCES run(id),
    UNIQUE (raw_hash, ts_utc)
);

-- Currency snapshots you enter by hand (until the stash API is available).
CREATE TABLE currency_snapshot (
    id            INTEGER PRIMARY KEY,
    ts_utc        TEXT NOT NULL,
    league        TEXT,
    character     TEXT,
    note          TEXT,
    divine_chaos  REAL,               -- price of 1 divine in chaos at the time
    source        TEXT DEFAULT 'manual'
);
CREATE TABLE currency_snapshot_item (
    snapshot_id INTEGER NOT NULL REFERENCES currency_snapshot(id) ON DELETE CASCADE,
    item        TEXT NOT NULL,
    qty         REAL NOT NULL,
    chaos_each  REAL,
    PRIMARY KEY (snapshot_id, item)
);
