-- Gold layer: views that turn silver rows into numbers for the dashboard.

CREATE INDEX ix_afk_session ON afk_period(session_id, start_utc);

CREATE VIEW v_visit AS
SELECT
    v.*,
    MAX(0, strftime('%s', COALESCE(v.end_utc, v.start_utc)) - strftime('%s', v.start_utc)) AS dur_s,
    COALESCE((
        SELECT SUM(MAX(0,
            MIN(strftime('%s', COALESCE(v.end_utc, v.start_utc)), strftime('%s', COALESCE(a.end_utc, v.end_utc, v.start_utc)))
          - MAX(strftime('%s', v.start_utc), strftime('%s', a.start_utc))))
        FROM afk_period a
        WHERE a.session_id = v.session_id
          AND a.start_utc < COALESCE(v.end_utc, v.start_utc)
          AND COALESCE(a.end_utc, '9999') > v.start_utc
    ), 0) AS afk_s
FROM area_visit v;

CREATE VIEW v_visit_active AS
SELECT *, MAX(0, dur_s - afk_s) AS active_s FROM v_visit;

CREATE VIEW v_own_character AS
SELECT c.*, l.name AS league, l.start_utc AS league_start
FROM character c LEFT JOIN league l ON l.id = c.league_id
WHERE c.other = 0
  AND EXISTS (SELECT 1 FROM area_visit v WHERE v.character_id = c.id);
