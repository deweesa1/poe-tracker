-- Indexes for the lookups the dashboard does most (deaths per visit/run,
-- levels and deaths over time, visits by area, runs by character).
CREATE INDEX IF NOT EXISTS ix_death_visit ON death(visit_id);
CREATE INDEX IF NOT EXISTS ix_death_run ON death(run_id);
CREATE INDEX IF NOT EXISTS ix_death_char ON death(character_id, ts_utc);
CREATE INDEX IF NOT EXISTS ix_level_char ON level_up(character_id, ts_utc);
CREATE INDEX IF NOT EXISTS ix_visit_area ON area_visit(area_id, character_id);
CREATE INDEX IF NOT EXISTS ix_run_char ON run(character_id, kind, start_utc);
CREATE INDEX IF NOT EXISTS ix_passive_char ON passive_change(character_id, ts_utc);

-- Same visit views, with unixepoch() instead of strftime('%s') (about twice as fast).
DROP VIEW IF EXISTS v_visit_active;
DROP VIEW IF EXISTS v_visit;
CREATE VIEW v_visit AS
SELECT
    v.*,
    MAX(0, unixepoch(COALESCE(v.end_utc, v.start_utc)) - unixepoch(v.start_utc)) AS dur_s,
    COALESCE((
        SELECT SUM(MAX(0,
            MIN(unixepoch(COALESCE(v.end_utc, v.start_utc)), unixepoch(COALESCE(a.end_utc, v.end_utc, v.start_utc)))
          - MAX(unixepoch(v.start_utc), unixepoch(a.start_utc))))
        FROM afk_period a
        WHERE a.session_id = v.session_id
          AND a.start_utc < COALESCE(v.end_utc, v.start_utc)
          AND COALESCE(a.end_utc, '9999') > v.start_utc
    ), 0) AS afk_s
FROM area_visit v;
CREATE VIEW v_visit_active AS
SELECT *, MAX(0, dur_s - afk_s) AS active_s FROM v_visit;
