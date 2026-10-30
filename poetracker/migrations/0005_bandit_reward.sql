-- Helping a bandit instead of killing all three gives a stat reward, which the
-- game announces: "You have received +15% to all Elemental Resistances."
CREATE TABLE bandit_reward (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    character_id  INTEGER REFERENCES character(id),
    visit_id      INTEGER REFERENCES area_visit(id),
    reward        TEXT NOT NULL,
    ts_utc        TEXT NOT NULL,
    UNIQUE (source, source_offset)
);
