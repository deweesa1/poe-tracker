-- Snapshots of a character from its public pathofexile.com profile (gear,
-- jewels, passive tree), taken automatically at league start milestones or by
-- hand. Keyed by character name + league (not character id) so a rebuild of
-- the log tables keeps them.
CREATE TABLE IF NOT EXISTS profile_snapshot (
    id             INTEGER PRIMARY KEY,
    character_name TEXT NOT NULL,
    league         TEXT,
    trigger        TEXT NOT NULL,          -- act3, level80, t6, t11, voidstone:<name>, manual
    label          TEXT,                   -- "Act 3 finished", "Level 80"...
    event_utc      TEXT,                   -- when it happened in game (manual: when asked)
    ts_utc         TEXT NOT NULL,          -- when the profile was read
    level          INTEGER,
    class          TEXT,
    items          BLOB,                   -- zlib-compressed JSON from get-items
    passives       BLOB,                   -- zlib-compressed JSON from get-passive-skills
    hash           TEXT,
    status         TEXT NOT NULL DEFAULT 'ok',   -- ok / same (nothing changed) / error
    error          TEXT
);
CREATE INDEX IF NOT EXISTS ix_snap_char ON profile_snapshot(character_name, league, ts_utc);
CREATE INDEX IF NOT EXISTS ix_snap_trigger ON profile_snapshot(league, trigger, character_name);
