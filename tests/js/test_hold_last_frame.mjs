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

// ─── TopsCoresLayer showFrame hold logic (data-selection only) ───────────────
// Inline the marker-selection logic from tops-cores.js: showFrame().
// Tests exercise which radar codes/markers are collected, without Leaflet.
function selectTopsCoresMarkers(frameData, frameIndex, holdRadarCodes = []) {
    const currentMap = frameData[frameIndex];
    if (!currentMap) return [];

    const heldSet  = holdRadarCodes.length > 0 ? new Set(holdRadarCodes) : null;
    const prevMap  = (heldSet && frameIndex > 0) ? frameData[frameIndex - 1] : null;

    const radarCodesToShow = new Set([
        ...currentMap.keys(),
        ...(heldSet ? [...heldSet] : []),
    ]);

    const markers = [];
    radarCodesToShow.forEach(code => {
        const sourceMap = (heldSet && heldSet.has(code) && prevMap) ? prevMap : currentMap;
        const radarMarkers = sourceMap.get(code);
        if (radarMarkers) markers.push(...radarMarkers);
    });
    return markers;
}

function makeMarker(id) { return { id, lat: 0, lon: 0, dbz: null, alt: null }; }

console.log('\n=== TopsCoresLayer showFrame hold-sync tests ===\n');

// ── TC1: No hold — markers from current frame only ───────────────────────────
console.log('TC1: no hold — current frame markers shown');
{
    const m5a = makeMarker('RMA5-frameA');
    const m5b = makeMarker('RMA5-frameB');
    const frameData = [
        new Map([['RMA5', [m5a]]]),
        new Map([['RMA5', [m5b]]]),
    ];
    const markers = selectTopsCoresMarkers(frameData, 1, []);
    assert(markers.length === 1,           'one marker at frame 1');
    assert(markers[0].id === 'RMA5-frameB','marker is from frame 1');
}

// ── TC2: Hold — held radar gets markers from frame i-1 ───────────────────────
console.log('\nTC2: held radar — tops/cores from frame i-1');
{
    const m5prev = makeMarker('RMA5-prev');
    const m8curr = makeMarker('RMA8-curr');
    const frameData = [
        new Map([['RMA5', [m5prev]]]),               // frame 0: RMA5 has data
        new Map([['RMA8', [m8curr]]]),               // frame 1: RMA5 missing, RMA8 present
    ];
    const markers = selectTopsCoresMarkers(frameData, 1, ['RMA5']);
    assert(markers.length === 2,           '2 markers: held RMA5 + current RMA8');
    assert(markers.some(m => m.id === 'RMA5-prev'), 'RMA5 markers from frame 0 (held)');
    assert(markers.some(m => m.id === 'RMA8-curr'), 'RMA8 markers from frame 1 (current)');
}

// ── TC3: Double gap — hold not applied when prev frame also empty ─────────────
console.log('\nTC3: double gap — no hold when prev frame also empty for that radar');
{
    const m8curr = makeMarker('RMA8-curr');
    const frameData = [
        new Map([['RMA5', [makeMarker('RMA5-f0')]]]),  // frame 0: RMA5 present
        new Map([['RMA8', [m8curr]]]),                  // frame 1: RMA5 missing (empty for RMA5)
        new Map([['RMA8', [makeMarker('RMA8-f2')]]]),   // frame 2: RMA5 still missing
    ];
    // At frame 2, computeHoldRadarCodes would return [] (frame 1 had no RMA5 data)
    // so holdRadarCodes for RMA5 should be empty — simulating the one-gap rule
    const markers = selectTopsCoresMarkers(frameData, 2, []);
    assert(markers.length === 1,           'no held markers at frame 2 (one-gap rule enforced by computeHoldRadarCodes)');
    assert(markers[0].id === 'RMA8-f2',   'only RMA8 frame-2 markers shown');
}

// ── TC4: Hold at frame 0 — no previous frame, holdRadarCodes ignored ──────────
console.log('\nTC4: hold at frame 0 — no prev frame, held codes produce nothing');
{
    const frameData = [
        new Map([['RMA5', [makeMarker('RMA5-f0')]]]),
    ];
    // frame 0 with hold requested — prevMap is null because frameIndex === 0
    const markers = selectTopsCoresMarkers(frameData, 0, ['RMA8']);
    assert(markers.length === 1,           'only real frame-0 markers shown');
    assert(markers[0].id === 'RMA5-f0',   'held code with no prev frame shows nothing extra');
}

// ── TC5: Completely empty current frame, all radars held ──────────────────────
console.log('\nTC5: fully empty frame — all markers from prev frame via hold');
{
    const m5 = makeMarker('RMA5-prev');
    const m8 = makeMarker('RMA8-prev');
    const frameData = [
        new Map([['RMA5', [m5]], ['RMA8', [m8]]]),  // frame 0: both present
        new Map(),                                    // frame 1: empty
    ];
    const markers = selectTopsCoresMarkers(frameData, 1, ['RMA5', 'RMA8']);
    assert(markers.length === 2,              '2 held markers from frame 0');
    assert(markers.some(m => m.id === 'RMA5-prev'), 'RMA5 held');
    assert(markers.some(m => m.id === 'RMA8-prev'), 'RMA8 held');
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
