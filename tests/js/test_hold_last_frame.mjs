/**
 * Unit tests for computeHoldRadarCodes (animation.js)
 *
 * Tests the one-gap hold-last-frame logic (fix/hold-last-frame).
 * Run with: node tests/js/test_hold_last_frame.mjs
 */

// ─── inline the function under test (avoids import/DOM issues) ───────────────
// Keep in sync with frontend/public/js/v2/animation.js: computeHoldRadarCodes
function computeHoldRadarCodes(frames, frameIndex) {
    if (frameIndex <= 0 || !frames[frameIndex] || !frames[frameIndex - 1]) return [];
    const currentRadars = new Set(Object.keys(frames[frameIndex].cogsByRadar || {}));
    return Object.keys(frames[frameIndex - 1].cogsByRadar || {})
        .filter(code => !currentRadars.has(code));
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

function frame(cogsByRadar) {
    return { cogsByRadar };
}

function cog(radarCode) {
    return { radar_code: radarCode, observation_time: '2026-08-23T08:00:00Z' };
}

// ─── Test Suite ───────────────────────────────────────────────────────────────

console.log('\n=== computeHoldRadarCodes unit tests ===\n');

// ── T1: Frame 0 — never holds (no previous frame) ────────────────────────────
console.log('T1: frame 0 — always returns empty (no previous frame)');
{
    const frames = [
        frame({ RMA5: cog('RMA5') }),
        frame({ RMA5: cog('RMA5') }),
    ];
    const holds = computeHoldRadarCodes(frames, 0);
    assert(holds.length === 0, 'no hold at frame 0');
}

// ── T2: No gap — all radars present at current frame → no holds ───────────────
console.log('\nT2: no gap — all radars present → no holds');
{
    const frames = [
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8') }),
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8') }),
    ];
    const holds = computeHoldRadarCodes(frames, 1);
    assert(holds.length === 0, 'no holds when all radars present');
}

// ── T3: Single gap — one radar missing at current frame → hold it ────────────
console.log('\nT3: single gap — RMA8 missing at frame 1 → hold from frame 0');
{
    const frames = [
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8') }),
        frame({ RMA5: cog('RMA5') }),                   // RMA8 missing
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8') }),
    ];
    const holds1 = computeHoldRadarCodes(frames, 1);
    assert(holds1.length === 1,           'one hold code at frame 1');
    assert(holds1[0] === 'RMA8',          'RMA8 is the held radar at frame 1');

    // frame 2 has RMA8 again → no holds
    const holds2 = computeHoldRadarCodes(frames, 2);
    assert(holds2.length === 0,           'no holds at frame 2 (RMA8 back)');
}

// ── T4: Double gap — hold at T+1 but NOT at T+2 (one-gap rule) ───────────────
console.log('\nT4: double gap — hold at T+1, no hold at T+2 (one-gap rule)');
{
    const frames = [
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8') }),  // 0: both present
        frame({ RMA5: cog('RMA5') }),                      // 1: RMA8 missing
        frame({ RMA5: cog('RMA5') }),                      // 2: RMA8 still missing
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8') }),  // 3: RMA8 back
    ];

    // Frame 1: RMA8 was in frame 0 → hold
    const holds1 = computeHoldRadarCodes(frames, 1);
    assert(holds1.includes('RMA8'),  'frame 1: RMA8 held (prev frame had it)');

    // Frame 2: RMA8 is missing in frame 1 too → NO hold (one-gap rule)
    const holds2 = computeHoldRadarCodes(frames, 2);
    assert(!holds2.includes('RMA8'), 'frame 2: RMA8 NOT held (two consecutive gaps)');
    assert(holds2.length === 0,      'frame 2: no holds at all');

    // Frame 3: RMA8 is back → no holds needed
    const holds3 = computeHoldRadarCodes(frames, 3);
    assert(holds3.length === 0,      'frame 3: no holds (data returned)');
}

// ── T5: All radars missing at current frame → hold all from previous ──────────
console.log('\nT5: completely empty frame → all radars held from previous');
{
    const frames = [
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8'), RMA14: cog('RMA14') }),
        frame({}),   // completely empty
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8'), RMA14: cog('RMA14') }),
    ];
    const holds = computeHoldRadarCodes(frames, 1);
    assert(holds.length === 3,         '3 radars held for a completely empty frame');
    assert(holds.includes('RMA5'),     'RMA5 held');
    assert(holds.includes('RMA8'),     'RMA8 held');
    assert(holds.includes('RMA14'),    'RMA14 held');

    // Frame 2 (all back) → no holds
    const holds2 = computeHoldRadarCodes(frames, 2);
    assert(holds2.length === 0,        'no holds at frame 2 after empty slot');
}

// ── T6: Completely empty previous frame → no holds (nothing to borrow) ────────
console.log('\nT6: previous frame also empty → no holds (nothing to borrow)');
{
    const frames = [
        frame({}),  // 0: empty
        frame({}),  // 1: empty
        frame({ RMA5: cog('RMA5') }),
    ];
    const holds = computeHoldRadarCodes(frames, 1);
    assert(holds.length === 0, 'no holds when previous frame also has no data');
}

// ── T7: New radar appears at current frame (not in previous) → not held ────────
console.log('\nT7: new radar appearing — not affected by hold logic');
{
    const frames = [
        frame({ RMA5: cog('RMA5') }),
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8') }),  // RMA8 new
    ];
    const holds = computeHoldRadarCodes(frames, 1);
    assert(holds.length === 0, 'no holds when new radar appears (present in current frame)');
}

// ── T8: Multiple radars, only one missing → only that one held ─────────────────
console.log('\nT8: multi-radar, partial gap — only missing radar is held');
{
    const frames = [
        frame({ RMA5: cog('RMA5'), RMA8: cog('RMA8'), RMA14: cog('RMA14') }),
        frame({ RMA5: cog('RMA5'),                      RMA14: cog('RMA14') }),  // RMA8 gap
    ];
    const holds = computeHoldRadarCodes(frames, 1);
    assert(holds.length === 1,        'exactly one hold');
    assert(holds[0] === 'RMA8',       'only RMA8 is held');
}

// ── T9: frameIndex out of bounds / missing frames → empty ─────────────────────
console.log('\nT9: edge cases — out of bounds / undefined frames');
{
    const frames = [
        frame({ RMA5: cog('RMA5') }),
    ];
    assert(computeHoldRadarCodes(frames, -1).length === 0, 'negative index → empty');
    assert(computeHoldRadarCodes(frames, 5).length  === 0, 'index beyond array → empty');
    assert(computeHoldRadarCodes([], 0).length       === 0, 'empty frames array → empty');
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
