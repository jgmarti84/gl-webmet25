/**
 * Unit tests for colmax-match.js (tracking frame -> COLMAX COG of the same volume).
 *
 * Scenario from production: RMA1 2026-10-28 has COLMAX for vol 01 at 22:45:47
 * and for the single-elevation vol 04 at 22:45:27 — the same minute. The cube
 * (vol 01) must get vol 01's COLMAX, whatever order the API returns them in.
 * Run with: node tests/js/test_colmax_match.mjs
 */
import { isoMinute, indexCogsByMinute, closestCog } from '../../frontend/public/js/shared/colmax-match.js';

let failures = 0;
function assert(cond, msg) {
    if (cond) { console.log(`ok   - ${msg}`); } else { console.log(`FAIL - ${msg}`); failures++; }
}

const bbox = { min_lat: -33, max_lat: -29, min_lon: -66, max_lon: -61 };
const vol01 = { id: 5158894, observation_time: '2026-10-28T22:45:47Z', vol_nr: '01', bbox };
const vol04 = { id: 5158821, observation_time: '2026-10-28T22:45:27Z', vol_nr: '04', bbox };
const earlier = { id: 5158783, observation_time: '2026-10-28T22:36:44Z', vol_nr: '01', bbox };
const noBbox = { id: 1, observation_time: '2026-10-28T22:50:00Z', vol_nr: '01', bbox: null };

assert(isoMinute('2026-10-28T22:45:47Z') === '2026-10-28T22:45', 'isoMinute keeps date, hour and minute');

// The API returns newest first: vol01 (22:45:47), then vol04 (22:45:27).
const newestFirst = indexCogsByMinute(new Map(), [vol01, vol04, earlier, noBbox]);
assert(newestFirst.get('2026-10-28T22:45').length === 2, 'both COGs of the same minute are kept');
assert(!newestFirst.has('2026-10-28T22:50'), 'COGs without a bbox are skipped');
assert(closestCog(newestFirst, '2026-10-28T22:45:47Z')?.vol_nr === '01', 'cube at 22:45:47 gets vol 01 (newest-first order)');

const oldestFirst = indexCogsByMinute(new Map(), [earlier, vol04, vol01]);
assert(closestCog(oldestFirst, '2026-10-28T22:45:47Z')?.vol_nr === '01', 'cube at 22:45:47 gets vol 01 (oldest-first order)');

assert(closestCog(newestFirst, '2026-10-28T22:36:44Z')?.id === 5158783, 'a minute with a single COG returns it');
assert(closestCog(newestFirst, '2026-10-28T22:40:00Z') === undefined, 'a minute with no COLMAX returns undefined');

// Pagination appends into the same index.
const paged = indexCogsByMinute(indexCogsByMinute(new Map(), [vol01]), [vol04]);
assert(paged.get('2026-10-28T22:45').length === 2, 'indexing several pages accumulates per minute');

console.log(failures ? `\n${failures} failure(s)` : '\nall passed');
process.exit(failures ? 1 : 0);
