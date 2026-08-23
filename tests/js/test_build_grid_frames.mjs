/**
 * Unit tests for buildGridFrames (radar-utils.js)
 *
 * Tests the window-anchored grid generation (fix/grid-window-anchor).
 * Run with: node tests/js/test_build_grid_frames.mjs
 */

// ─── inline the function under test (avoids import/DOM issues) ───────────────
// Keep in sync with frontend/public/js/v2/radar-utils.js: buildGridFrames
function buildGridFrames(cogs, stepMinutes = 10, windowStart = null, windowEnd = null) {
    const stepMs = stepMinutes * 60 * 1000;
    const bySlot = {};
    if (cogs && cogs.length > 0) {
        cogs.forEach(cog => {
            const t    = new Date(cog.observation_time).getTime();
            const slot = Math.round(t / stepMs) * stepMs;
            if (!bySlot[slot]) bySlot[slot] = {};
            const prev = bySlot[slot][cog.radar_code];
            if (!prev || t > prev.t) {
                bySlot[slot][cog.radar_code] = { cog, t };
            }
        });
    }
    let slots;
    if (windowStart !== null && windowEnd !== null) {
        const startMs = Math.floor(new Date(windowStart).getTime() / stepMs) * stepMs;
        const endMs   = Math.ceil(new Date(windowEnd).getTime()   / stepMs) * stepMs;
        slots = [];
        for (let s = startMs; s <= endMs; s += stepMs) slots.push(s);
    } else {
        if (!cogs || cogs.length === 0) return [];
        slots = Object.keys(bySlot).map(Number).sort((a, b) => a - b);
    }
    return slots.map(slotMs => {
        const cogsByRadar = {};
        if (bySlot[slotMs]) {
            Object.values(bySlot[slotMs]).forEach(({ cog }) => {
                cogsByRadar[cog.radar_code] = cog;
            });
        }
        const firstCog = Object.values(cogsByRadar)[0] || null;
        return {
            displayTimestamp: new Date(slotMs).toISOString(),
            timestamp:        firstCog ? firstCog.observation_time : new Date(slotMs).toISOString(),
            cogsByRadar,
        };
    });
}

// ─── helpers ─────────────────────────────────────────────────────────────────
let passed = 0;
let failed = 0;

function assert(cond, msg) {
    if (cond) {
        console.log(`  ✓  ${msg}`);
        passed++;
    } else {
        console.error(`  ✗  ${msg}`);
        failed++;
    }
}

function makeTime(h, m = 0) {
    // Fixed date 2026-08-23, UTC
    return new Date(`2026-08-23T${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:00Z`).toISOString();
}

function makeCog(radarCode, h, m = 0) {
    return { radar_code: radarCode, observation_time: makeTime(h, m), id: `${radarCode}-${h}-${m}` };
}

// ─── Test Suite ───────────────────────────────────────────────────────────────

console.log('\n=== buildGridFrames unit tests ===\n');

// ── T1: Legacy (no window) — only slots with data ────────────────────────────
console.log('T1: legacy mode (no window) — data-driven slots');
{
    const cogs = [makeCog('RMA5', 8, 0), makeCog('RMA5', 8, 10), makeCog('RMA5', 8, 20)];
    const frames = buildGridFrames(cogs);
    assert(frames.length === 3, 'produces 3 frames for 3 distinct slots');
    assert(frames[0].displayTimestamp === makeTime(8, 0), 'first slot is 08:00');
    assert(frames[2].displayTimestamp === makeTime(8, 20), 'last slot is 08:20');
    assert(Object.keys(frames[0].cogsByRadar).length === 1, 'frame has cogsByRadar entry');
}

// ── T2: Window-anchored — all slots generated within window ──────────────────
console.log('\nT2: window-anchored — full slot range generated');
{
    // Window 08:00–09:30 → slots 08:00, 08:10, 08:20, 08:30, 08:40, 08:50, 09:00, 09:10, 09:20, 09:30
    const windowStart = makeTime(8, 0);
    const windowEnd   = makeTime(9, 30);
    const cogs = [makeCog('RMA5', 8, 0), makeCog('RMA5', 8, 20), makeCog('RMA5', 9, 20)];
    const frames = buildGridFrames(cogs, 10, windowStart, windowEnd);
    const expectedSlots = 10; // 08:00..09:30 inclusive = 10 slots
    assert(frames.length === expectedSlots, `produces ${expectedSlots} slots for 90-min window`);
    assert(frames[0].displayTimestamp === makeTime(8, 0), 'first slot anchored to window start 08:00');
    assert(frames[frames.length - 1].displayTimestamp === makeTime(9, 30), 'last slot anchored to window end 09:30');
}

// ── T3: Empty slots have empty cogsByRadar ────────────────────────────────────
console.log('\nT3: empty slots have cogsByRadar = {} and timestamp = slot boundary');
{
    const windowStart = makeTime(8, 0);
    const windowEnd   = makeTime(8, 30);
    const cogs = [makeCog('RMA5', 8, 0), makeCog('RMA5', 8, 30)]; // 08:10 and 08:20 are missing
    const frames = buildGridFrames(cogs, 10, windowStart, windowEnd);
    assert(frames.length === 4, 'produces 4 slots (08:00, 08:10, 08:20, 08:30)');
    assert(Object.keys(frames[1].cogsByRadar).length === 0, '08:10 slot has empty cogsByRadar');
    assert(Object.keys(frames[2].cogsByRadar).length === 0, '08:20 slot has empty cogsByRadar');
    assert(frames[1].timestamp === makeTime(8, 10), 'empty slot timestamp = slot boundary');
    assert(Object.keys(frames[0].cogsByRadar).length === 1, '08:00 slot has COG data');
    assert(Object.keys(frames[3].cogsByRadar).length === 1, '08:30 slot has COG data');
}

// ── T4: Window start is not on a 10-min boundary ─────────────────────────────
console.log('\nT4: window boundaries are non-aligned (floor start, ceil end)');
{
    // Window 08:03–08:47 → floor(8:03) = 08:00, ceil(8:47) = 08:50 → 6 slots
    const windowStart = new Date('2026-08-23T08:03:00Z').toISOString();
    const windowEnd   = new Date('2026-08-23T08:47:00Z').toISOString();
    const cogs = [makeCog('RMA5', 8, 10)];
    const frames = buildGridFrames(cogs, 10, windowStart, windowEnd);
    assert(frames[0].displayTimestamp === makeTime(8, 0),  'start floored to 08:00');
    assert(frames[frames.length - 1].displayTimestamp === makeTime(8, 50), 'end ceiled to 08:50');
    assert(frames.length === 6, '6 slots: 08:00, 08:10, 08:20, 08:30, 08:40, 08:50');
}

// ── T5: Multiple radars — window includes slot where only one has data ────────
console.log('\nT5: multi-radar — slot exists even when only one radar has data');
{
    const windowStart = makeTime(8, 0);
    const windowEnd   = makeTime(8, 20);
    // RMA5 has 08:00, 08:10, 08:20; RMA8 only has 08:00 and 08:20
    const cogs = [
        makeCog('RMA5', 8, 0), makeCog('RMA5', 8, 10), makeCog('RMA5', 8, 20),
        makeCog('RMA8', 8, 0),                           makeCog('RMA8', 8, 20),
    ];
    const frames = buildGridFrames(cogs, 10, windowStart, windowEnd);
    assert(frames.length === 3, '3 slots total');
    const f810 = frames[1]; // 08:10
    assert(f810.cogsByRadar['RMA5'] !== undefined, '08:10 has RMA5 data');
    assert(f810.cogsByRadar['RMA8'] === undefined, '08:10 has no RMA8 data (expected gap)');
    assert(Object.keys(f810.cogsByRadar).length === 1, '08:10 has exactly 1 radar entry');
}

// ── T6: COG at 07:54 rounds to 07:50 — stays within window ──────────────────
console.log('\nT6: COG at :54 rounds to :50 boundary — captured correctly');
{
    const windowStart = makeTime(7, 30);
    const windowEnd   = makeTime(9,  0);
    const cogs = [
        { radar_code: 'RMA5', observation_time: new Date('2026-08-23T07:54:00Z').toISOString(), id: 'x' },
        { radar_code: 'RMA5', observation_time: new Date('2026-08-23T09:06:00Z').toISOString(), id: 'y' },
    ];
    const frames = buildGridFrames(cogs, 10, windowStart, windowEnd);
    // Window: floor(7:30)=7:30 → ceil(9:00)=9:00 → 10 slots
    assert(frames[0].displayTimestamp === makeTime(7, 30), 'window starts at 07:30');
    assert(frames[frames.length - 1].displayTimestamp === makeTime(9, 0), 'window ends at 09:00');
    // 07:54 rounds to 07:50 — should be in slot 07:50
    const slot750 = frames.find(f => f.displayTimestamp === makeTime(7, 50));
    assert(slot750 !== undefined, '07:50 slot exists in window');
    assert(slot750.cogsByRadar['RMA5'] !== undefined, 'COG at 07:54 assigned to 07:50 slot');
    // 09:06 rounds to 09:10 — outside window, so NOT in frames
    const slot910 = frames.find(f => f.displayTimestamp === makeTime(9, 10));
    assert(slot910 === undefined, 'COG at 09:06 (rounds to 09:10) excluded — outside window');
}

// ── T7: Exact 1.5h window produces stable slot count ─────────────────────────
console.log('\nT7: exact 1.5h window (90 min) → always 10 slots');
{
    const now         = new Date('2026-08-23T09:00:00Z');
    const windowStart = new Date(now.getTime() - 90 * 60 * 1000).toISOString(); // 07:30
    const windowEnd   = now.toISOString();
    const cogs = [makeCog('RMA5', 7, 50), makeCog('RMA5', 8, 20), makeCog('RMA5', 8, 50)];
    const frames = buildGridFrames(cogs, 10, windowStart, windowEnd);
    assert(frames.length === 10, '90-min window always yields 10 slots (07:30..09:00)');
    assert(frames[0].displayTimestamp  === makeTime(7, 30), 'window pinned at 07:30');
    assert(frames[9].displayTimestamp  === makeTime(9,  0), 'window pinned at 09:00');
}

// ── T8: Empty cogs array with window → all-empty frames ──────────────────────
console.log('\nT8: empty cogs + window → frames with empty cogsByRadar (no crash)');
{
    const frames = buildGridFrames([], 10, makeTime(8, 0), makeTime(8, 30));
    assert(frames.length === 4, '4 slots generated even with no COG data');
    assert(frames.every(f => Object.keys(f.cogsByRadar).length === 0), 'all cogsByRadar empty');
}

// ── T9: latest obs_time wins when two COGs map to same slot ──────────────────
// 08:02 and 08:04 both round to 08:00 (both within 5 min of the boundary)
console.log('\nT9: latest COG wins when two map to the same slot');
{
    const cogs = [
        { radar_code: 'RMA5', observation_time: new Date('2026-08-23T08:02:00Z').toISOString(), id: 'early' },
        { radar_code: 'RMA5', observation_time: new Date('2026-08-23T08:04:00Z').toISOString(), id: 'late' },
    ];
    const frames = buildGridFrames(cogs, 10, makeTime(8, 0), makeTime(8, 0));
    assert(frames.length === 1, 'single slot');
    assert(frames[0].cogsByRadar['RMA5'].id === 'late', 'latest COG (08:04) wins over 08:02 in same slot');
}

// ─── Summary ─────────────────────────────────────────────────────────────────
console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) {
    console.error('TESTS FAILED');
    process.exit(1);
} else {
    console.log('ALL TESTS PASSED');
}
