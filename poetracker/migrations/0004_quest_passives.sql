-- Passive skill points from quests.
-- quest_point: one row per "You have received a Passive Skill Point." (or "2 Passive Skill Points.") line
-- (the game only says this for quest rewards; level-ups are separate).
CREATE TABLE quest_point (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    character_id  INTEGER REFERENCES character(id),
    visit_id      INTEGER REFERENCES area_visit(id),
    area_id       TEXT,
    points        INTEGER NOT NULL DEFAULT 1,
    ts_utc        TEXT NOT NULL,
    UNIQUE (source, source_offset)
);
CREATE INDEX ix_quest_point ON quest_point(character_id, ts_utc);

-- quest_report: the per-quest list printed by the in-game /passives command,
-- e.g. "(1 from The Dweller of the Deep)". report_utc groups one command's lines.
CREATE TABLE quest_report (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    character_id  INTEGER REFERENCES character(id),
    visit_id      INTEGER REFERENCES area_visit(id),
    report_utc    TEXT NOT NULL,
    quest         TEXT NOT NULL,
    points        INTEGER NOT NULL,
    UNIQUE (source, source_offset)
);
CREATE INDEX ix_quest_report ON quest_report(character_id, report_utc);
