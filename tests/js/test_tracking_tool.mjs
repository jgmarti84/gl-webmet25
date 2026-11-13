/**
 * Unit tests for the single-radar view's tracking tool helpers:
 * slot matching (radar-utils.js), saved choices and request shape
 * (tracking-prefs.js) and the access rule (tracking-access.js).
 * Run with: node tests/js/test_tracking_tool.mjs
 */
import { buildGridFrames, buildTrackingSlotMap } from '../../frontend/public/js/v2/radar-utils.js';
import {
    LAST_N_CHOICES,
    DEFAULT_LAST_N,
    restoreLastN,
    restoreLeads,
    trackingRequest,
} from '../../frontend/public/js/shared/tracking-prefs.js';
import { canUseTracking } from '../../frontend/public/js/shared/tracking-access.js';

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ── slot matching ─────────────────────────────────────────────────────────────
console.log('buildTrackingSlotMap');
// Window 22:10..23:00 -> slots 22:10, 22:20, ..., 23:00 (indices 0..5)
const grid = buildGridFrames([], 10, '2026-10-20T22:10:00Z', '2026-10-20T23:00:00Z');
const frame = t => ({ timestamp: t });

{
    const m = buildTrackingSlotMap([frame('2026-10-20T22:22:35Z')], grid);
    assert(m.get(1) === 0, 'a frame goes into its nearest slot (22:22:35 -> 22:20)');
}
{
    const m = buildTrackingSlotMap([frame('2026-10-20T22:35:24Z'), frame('2026-10-20T22:44:27Z')], grid);
    assert(m.get(3) === 1 && !m.has(2), 'two frames in one slot: the latest wins (22:40); 22:30 stays empty');
}
{
    const m = buildTrackingSlotMap([frame('2026-10-20T21:30:00Z'), frame('2026-10-20T23:30:00Z')], grid);
    assert(m.size === 0, 'frames outside the grid are dropped');
}
{
    const frames = ['22:31:00', '22:40:00', '22:49:00'].map(t => frame(`2026-10-20T${t}Z`));
    const m = buildTrackingSlotMap(frames, grid);
    assert(eq([...m.entries()], [[2, 0], [3, 1], [4, 2]]), 'last N frames land on the last N slots they belong to');
    assert(!m.has(0) && !m.has(1), 'earlier slots have no tracking (overlay cleared there)');
}
{
    const m = buildTrackingSlotMap([frame('nonsense'), {}, null], grid);
    assert(m.size === 0, 'frames without a usable timestamp are ignored');
}
assert(buildTrackingSlotMap(null, null).size === 0, 'no frames, no grid: empty map');

// ── last N ────────────────────────────────────────────────────────────────────
console.log('restoreLastN');
assert(eq(LAST_N_CHOICES, [3, 5, 10]) && DEFAULT_LAST_N === 3, 'choices are 3 / 5 / 10, default 3');
assert(restoreLastN('5') === 5, 'a saved choice is kept');
assert(restoreLastN(null) === 3, 'nothing saved -> 3');
assert(restoreLastN('7') === 3, 'a value that is not a choice -> 3');
assert(restoreLastN('10', 5) === 3, 'a saved choice above the service cap -> 3');
assert(restoreLastN('10', 2) === 3, 'cap below every choice -> default (the service refuses; the panel says why)');

// ── forecast leads ────────────────────────────────────────────────────────────
console.log('restoreLeads');
const ALL = [9, 18, 27, 36, 45, 54, 63];
const DEF = [18, 36, 54];
assert(eq(restoreLeads(null, ALL, DEF), DEF), 'nothing saved -> 18, 36, 54');
assert(eq(restoreLeads('not json', ALL, DEF), DEF), 'unreadable -> defaults');
assert(eq(restoreLeads('{"a":1}', ALL, DEF), DEF), 'not a list -> defaults');
assert(eq(restoreLeads('[63, 9, 99]', ALL, DEF), [9, 63]), 'saved leads kept in order, unknown ones dropped');
assert(eq(restoreLeads('[]', ALL, DEF), []), 'an empty choice (no forecasts) is kept');
assert(eq(restoreLeads('["18"]', ALL, DEF), [18]), 'numbers saved as strings still match');

// ── request ───────────────────────────────────────────────────────────────────
console.log('trackingRequest');
{
    const start = new Date('2026-10-20T22:10:00Z');
    const end = new Date('2026-10-20T23:32:00Z');   // newest volume 23:32:45, shown as 23:32
    const r = trackingRequest('RMA1', { start, end }, 5, { dbz_threshold: 35 });
    assert(r.radar === 'RMA1' && r.lastN === 5 && r.config.dbz_threshold === 35, 'carries radar, N and settings');
    assert(r.start === '2026-10-20T22:10:00.000Z', 'start is the window start');
    assert(r.end === '2026-10-20T23:33:00.000Z', 'end gets one minute of slack (keeps the newest volume)');
}
assert(trackingRequest('RMA1', { start: null, end: null }, 3, {}) === null, 'no window yet -> null');
assert(trackingRequest('RMA1', null, 3, {}) === null, 'missing window -> null');

// ── access ────────────────────────────────────────────────────────────────────
console.log('canUseTracking');
const perm = (views, tracking) => ({ radar_detail_views: views, tools: { tracking } });
assert(canUseTracking('RMA1', perm(['RMA1'], true)) === true, 'view and tool: yes');
assert(canUseTracking('RMA1', perm(['RMA1'], false)) === false, 'view without the tool: no');
assert(canUseTracking('RMA1', perm(['RMA5'], true)) === false, 'tool without this view: no');
assert(canUseTracking('RMA1', { radar_detail_views: ['RMA1'] }) === false, 'an old answer without tools: no');
assert(canUseTracking('RMA1', null) === false, 'no permissions: no');

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
