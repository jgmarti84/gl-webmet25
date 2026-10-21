/**
 * Unit tests for tops-cores-match.js (marker lookup by displayed-COG identity).
 *
 * Scenarios come from production:
 *  - RMA7 2026-10-20: scans 22:22:35 / 22:35:24 / 22:44:27 on a 10-min grid with
 *    Math.round binning -> 22:35:24 and 22:44:27 collide in slot 22:40, slot 22:30
 *    is empty (image held).
 *  - RMA14 + AR5, removing AR5 deletes the 16:30 slot and shifts every frame index;
 *    markers must follow the displayed COG, not the frame position.
 * Run with: node tests/js/test_tops_cores_match.mjs
 */
import { buildGridFrames, } from '../../frontend/public/js/v2/radar-utils.js';
import { computeHoldRadarCodes } from '../../frontend/public/js/v2/animation.js';
import {
    recordKey,
    cogKey,
    collectDisplayedCogs,
    cogTimeSpan,
    selectWantedRecords,
    markersForFrame,
} from '../../frontend/public/js/shared/tops-cores-match.js';

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}

const cog = (t, vol = '01', radar = 'RMA7', strategy = '0315') =>
    ({ radar_code: radar, strategy, vol_nr: vol, observation_time: t });
const rec = (t, vol = '01', radar = 'RMA7', strategy = '0315') =>
    ({ radar_code: radar, strategy, vol_nr: vol, observation_time: t });
// markers identify their scan so assertions can tell which one is drawn
const cache = (...entries) => new Map(entries.map(([c, tag]) => [cogKey(c), [{ tag }]]));
const tags = ms => ms.map(m => m.tag);

const T = ['2026-10-20T22:13:32Z', '2026-10-20T22:22:35Z', '2026-10-20T22:35:24Z',
           '2026-10-20T22:44:27Z', '2026-10-20T22:53:30Z'];
const cogs = T.map(t => cog(t));
const byTime = new Map(cogs.map((c, i) => [cogKey(c), [{ tag: `scan${i}` }]]));
const W0 = new Date('2026-10-20T22:00:00Z'), W1 = new Date('2026-10-20T23:00:00Z');

console.log('\n=== tops-cores-match unit tests ===\n');

console.log('T1: each frame draws the markers of its own displayed COG (RMA7 incident)');
{
    const frames = buildGridFrames(cogs, 10, W0, W1);
    const at = iso => {
        const i = frames.findIndex(f => f.displayTimestamp === iso);
        return tags(markersForFrame(frames[i], frames[i - 1], computeHoldRadarCodes(frames, i), byTime));
    };
    assert(at('2026-10-20T22:20:00.000Z')[0] === 'scan1', '22:20 slot -> 22:22:35 scan');
    assert(at('2026-10-20T22:30:00.000Z')[0] === 'scan1', 'empty 22:30 slot holds 22:20 scan (same as the held image)');
    assert(at('2026-10-20T22:40:00.000Z')[0] === 'scan3', '22:40 slot shows the 22:44:27 COG -> scan3, not 22:35:24');
    assert(at('2026-10-20T22:50:00.000Z')[0] === 'scan4', '22:50 slot -> 22:53:30 scan');
    assert(at('2026-10-20T23:00:00.000Z')[0] === 'scan4', 'empty 23:00 slot holds 22:50 scan');
}

console.log('T2: regression — removing a radar shifts frame indices, markers still follow the COG');
{
    const rma14 = ['2026-10-21T16:46:35Z', '2026-10-21T16:54:58Z', '2026-10-21T17:03:18Z'].map(t => cog(t, '01', 'RMA14'));
    const ar5 = [cog('2026-10-21T16:30:19Z', '03', 'AR5', '1000'), cog('2026-10-21T17:00:19Z', '03', 'AR5', '1000')];
    const markers = new Map([
        ...rma14.map((c, i) => [cogKey(c), [{ tag: `rma14-${i}` }]]),
        ...ar5.map((c, i) => [cogKey(c), [{ tag: `ar5-${i}` }]]),
    ]);
    const w0 = new Date('2026-10-21T16:30:00Z'), w1 = new Date('2026-10-21T17:30:00Z');
    const rma14Tag = (frames, iso) => {
        const i = frames.findIndex(f => f.displayTimestamp === iso);
        return tags(markersForFrame(frames[i], frames[i - 1], computeHoldRadarCodes(frames, i), markers))
            .filter(t => t.startsWith('rma14'));
    };
    const before = buildGridFrames([...rma14, ...ar5], 10, w0, w1);
    assert(rma14Tag(before, '2026-10-21T17:00:00.000Z')[0] === 'rma14-2', 'before removal: 17:00 -> 17:03:18 scan');

    // what removeRadarIncremental does: drop the radar, then drop frames left empty
    const after = before.map(f => ({ ...f, cogsByRadar: Object.fromEntries(
        Object.entries(f.cogsByRadar).filter(([code]) => code !== 'AR5')) }))
        .filter(f => Object.keys(f.cogsByRadar).length > 0);
    assert(after.length === before.length - 1 || after.length < before.length, 'removal deleted at least one frame (indices shifted)');
    assert(rma14Tag(after, '2026-10-21T17:00:00.000Z')[0] === 'rma14-2', 'after removal: 17:00 still -> 17:03:18 scan');
    assert(rma14Tag(after, '2026-10-21T16:50:00.000Z')[0] === 'rma14-1', 'after removal: 16:50 still -> 16:54:58 scan');
    assert(!tags(markersForFrame(after[0], null, [], markers)).some(t => t.startsWith('ar5')),
        'removed radar contributes no markers');
}

console.log('T3: held radar uses the previous frame\'s COG; missing cache entry draws nothing');
{
    const prev = { cogsByRadar: { RMA7: cog(T[1]), RMA1: cog('2026-10-20T22:20:00Z', '01', 'RMA1') } };
    const cur = { cogsByRadar: { RMA1: cog('2026-10-20T22:30:00Z', '01', 'RMA1') } };
    const m = new Map([[cogKey(prev.cogsByRadar.RMA7), [{ tag: 'rma7-held' }]],
                       [cogKey(cur.cogsByRadar.RMA1), [{ tag: 'rma1-cur' }]]]);
    const out = tags(markersForFrame(cur, prev, ['RMA7'], m)).sort();
    assert(out.join() === 'rma1-cur,rma7-held', 'RMA7 held from previous COG, RMA1 from its current COG');
    assert(markersForFrame(cur, prev, ['RMA7'], new Map()).length === 0, 'nothing cached -> nothing drawn (no neighbour borrowed)');
    assert(markersForFrame(null, null, [], m).length === 0, 'null frame -> empty');
}

console.log('T4: exact identity only — time, strategy, vol_nr and radar must agree');
{
    const f = { cogsByRadar: { RMA7: cog('2026-10-20T22:22:35Z') } };
    const base = [cog('2026-10-20T22:22:35Z'), 'x'];
    assert(markersForFrame(f, null, [], cache(base)).length === 1, 'identical identity matches');
    assert(markersForFrame(f, null, [], cache([cog('2026-10-20T22:22:36Z'), 'x'])).length === 0, '1 s off does not match');
    assert(markersForFrame(f, null, [], cache([cog('2026-10-20T22:22:35Z', '02'), 'x'])).length === 0, 'other vol_nr does not match');
    assert(markersForFrame(f, null, [], cache([cog('2026-10-20T22:22:35Z', '01', 'RMA7', '1000'), 'x'])).length === 0, 'other strategy does not match');
    assert(markersForFrame(f, null, [], cache([cog('2026-10-20T22:22:35Z', '01', 'RMA1'), 'x'])).length === 0, 'other radar does not match');
}

console.log('T5: collectDisplayedCogs / cogTimeSpan / selectWantedRecords');
{
    const frames = buildGridFrames(cogs, 10, W0, W1);
    const displayed = collectDisplayedCogs(frames);
    assert(displayed.size === 4 && !displayed.has(cogKey(cogs[2])), '22:35:24 COG is not displayed (displaced) -> not collected');
    const span = cogTimeSpan(displayed.values());
    assert(span.from.toISOString() === '2026-10-20T22:13:32.000Z' && span.to.toISOString() === '2026-10-20T22:53:30.000Z',
        'span covers displayed COGs only');
    assert(cogTimeSpan([]) === null, 'null span for no COGs');
    const wanted = selectWantedRecords(T.map(t => rec(t)), displayed);
    assert(wanted.length === 4 && !wanted.some(r => r.observation_time === T[2]), 'records of non-displayed COGs are not fetched');
    assert(collectDisplayedCogs(null).size === 0, 'null frames tolerated');
}

console.log('T6: key is stable across ISO formats of the same instant');
{
    assert(recordKey('A', '0315', '01', '2026-10-20T22:22:35Z') === recordKey('A', '0315', '01', '2026-10-20T22:22:35.000Z'), 'Z vs .000Z identical');
}

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
