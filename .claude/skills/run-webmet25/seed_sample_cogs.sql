-- seed_sample_cogs.sql — insert a small set of fake radar_cogs rows so the v2
-- frontend's product dropdown / coverage modes / time-range queries populate for
-- UI testing WITHOUT real COG files on disk.
--
-- NOTE: only the metadata endpoints (/products?vol_nr=…, /cogs) need these rows.
-- Frame IMAGES (/frames/{id}/image.png) still 404 because file_path points at
-- nonexistent files — that's fine for verifying dropdown/switch/field behaviour.
--
-- Apply (against the dev prod DB):
--   docker exec -i radar_db-gl \
--     psql -U radar -d radar_prod_db < .claude/skills/run-webmet25/seed_sample_cogs.sql
-- Remove: DELETE FROM radar_cogs WHERE file_path LIKE '/sample/%';

BEGIN;

DELETE FROM radar_cogs WHERE file_path LIKE '/sample/%';

-- 13 timestamps, 10 min apart, ending "now".
WITH ts AS (
    SELECT generate_series(now() - interval '120 min', now(), interval '10 min') AS obs
),
-- (vol_nr, polarimetric_var) combos. cd = vols 01/02, vig = vol 04.
-- COLMAX/COLMAXo + DBZH/DBZHo have BOTH variants (Filtered switch enabled);
-- KDPo (cd) and VRADo (vig) are unfiltered-only (Filtered switch disabled).
combo AS (
    SELECT * FROM (VALUES
        ('01','COLMAX'), ('01','COLMAXo'), ('01','DBZH'), ('01','DBZHo'), ('01','KDPo'),
        ('04','DBZHo'), ('04','COLMAXo'), ('04','VRADo')
    ) AS c(vol_nr, pvar)
)
INSERT INTO radar_cogs
    (radar_code, product_id, estrategia_code, observation_time,
     polarimetric_var, vol_nr, status, show_me, radar_coverage_m,
     file_path, file_name)
SELECT
    'AR5',
    (SELECT id FROM radar_products WHERE product_key = combo.pvar),
    '0315',
    ts.obs,
    combo.pvar,
    combo.vol_nr,
    'AVAILABLE',
    true,
    240000,
    '/sample/AR5_0315_' || combo.vol_nr || '_' || combo.pvar || '_'
        || to_char(ts.obs, 'YYYYMMDDHH24MISS') || '.tif',
    'AR5_0315_' || combo.vol_nr || '_' || combo.pvar || '_'
        || to_char(ts.obs, 'YYYYMMDDHH24MISS') || '.tif'
FROM ts CROSS JOIN combo;

COMMIT;

SELECT vol_nr, polarimetric_var, count(*)
FROM radar_cogs WHERE file_path LIKE '/sample/%'
GROUP BY vol_nr, polarimetric_var ORDER BY vol_nr, polarimetric_var;
