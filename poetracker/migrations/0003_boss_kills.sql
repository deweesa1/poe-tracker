-- Boss kills detected from the boss's own defeat dialogue (see milestones.yaml).
CREATE TABLE boss_kill (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    boss          TEXT NOT NULL,
    character_id  INTEGER REFERENCES character(id),
    run_id        INTEGER REFERENCES run(id),
    visit_id      INTEGER REFERENCES area_visit(id),
    ts_utc        TEXT NOT NULL,
    UNIQUE (source, source_offset)
);
CREATE INDEX ix_boss_kill ON boss_kill(boss, ts_utc);
