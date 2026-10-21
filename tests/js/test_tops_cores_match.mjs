/**
 * Unit tests for tops-cores-match.js (match tops/cores records to displayed COGs).
 *
 * Scenario taken from RMA7 on 2026-10-20: scans 22:22:35 and 22:35:24 plus
 * 22:44:27 on a 10-min grid with Math.round binning -> 22:35:24 and 22:44:27
 * collide in slot 22:40 and slot 22:30 is empty.
 * Run with: node tests/js/test_tops_cores_match.mjs
 */
import { buildGridFrames } from '../../frontend/public/js/v2/radar-utils.js';
import {
    recordKey,
    displayedCogTimeSpan,
    matchRecordsToFrames,
} from '../../frontend/public/js/shared/tops-cores-match.js';

let passed = 0;
let failed = 0;
function assert(cond, msg) {
    if (cond) { console.log(`  ✓  ${msg}`); passed++; }
    else { console.error(`  ✗  ${msg}`); failed++; }
}

const cog = (t, vol = '01', radar = 'RMA7') =>
    ({ radar_code: radar, strategy: '0315', vol_nr: vol, observation_time: t });
const rec = (t, vol = '01', radar = 'RMA7') =>
    ({ radar_code: radar, strategy: '0315', vol_nr: vol, observation_time: t });

const T = ['2026-10-20T22:13:32Z', '2026-10-20T22:22:35Z', '2026-10-20T22:35:24Z',
           '2026-10-20T22:44:27Z', '2026-10-20T22:53:30Z'];
const cogs = T.map(t => cog(t));
const records = T.map(t => rec(t));

console.log('\n=== matchRecordsToFrames unit tests ===\n');

console.log('T1: each frame is paired with the record of its own displayed COG');
{
    const frames = buildGridFrames(cogs, 10, new Date('2026-10-20T22:00:00Z'), new Date('2026-10-20T23:00:00Z'));
    const m = matchRecordsToFrames(frames, records);
    const timeAt = i => m[i].has('RMA7') ? records[m[i].get('RMA7')].observation_time : null;
    const slot = iso => frames.findIndex(f => f.displayTimestamp === iso);
    assert(timeAt(slot('2026-10-20T22:10:00.000Z')) === T[0], '22:10 slot -> 22:13:32 record');
    assert(timeAt(slot('2026-10-20T22:20:00.000Z')) === T[1], '22:20 slot -> 22:22:35 record');
    assert(timeAt(slot('2026-10-20T22:30:00.000Z')) === null, 'empty 22:30 slot -> no record of its own (hold shows previous)');
    assert(timeAt(slot('2026-10-20T22:40:00.000Z')) === T[3], '22:40 slot shows 22:44:27 COG -> 22:44:27 record, not 22:35:24');
    assert(timeAt(slot('2026-10-20T22:50:00.000Z')) === T[4], '22:50 slot -> 22:53:30 record');
}

console.log('T2: the record of a COG that is never displayed is never matched');
{
    const frames = buildGridFrames(cogs, 10, new Date('2026-10-20T22:00:00Z'), new Date('2026-10-20T23:00:00Z'));
    const used = new Set(matchRecordsToFrames(frames, records).flatMap(mm => [...mm.values()]));
    assert(!used.has(2), '22:35:24 record unused (its COG was displaced by 22:44:27)');
}

console.log('T3: exact match only — no tolerance');
{
    const frames = [{ cogsByRadar: { RMA7: cog('2026-10-20T22:22:35Z') } }];
    const m = matchRecordsToFrames(frames, [rec('2026-10-20T22:22:36Z')]);
    assert(!m[0].has('RMA7'), 'record 1 s off does not match');
}

console.log('T4: strategy / vol_nr must agree (vol 02 COG gets no vol 01 record)');
{
    const frames = [{ cogsByRadar: { RMA7: cog('2026-10-20T22:22:35Z', '02') } }];
    const m = matchRecordsToFrames(frames, [rec('2026-10-20T22:22:35Z', '01')]);
    assert(!m[0].has('RMA7'), 'vol 02 COG not paired with vol 01 record');
}

console.log('T5: multi-radar frames pair per radar; missing record leaves radar absent');
{
    const frames = [{ cogsByRadar: {
        RMA1: cog('2026-10-20T22:20:00Z', '01', 'RMA1'),
        RMA7: cog('2026-10-20T22:22:35Z'),
    } }];
    const m = matchRecordsToFrames(frames, [rec('2026-10-20T22:20:00Z', '01', 'RMA1')]);
    assert(m[0].get('RMA1') === 0, 'RMA1 matched');
    assert(!m[0].has('RMA7'), 'RMA7 without record absent');
    const other = matchRecordsToFrames(frames, [rec('2026-10-20T22:20:00Z', '01', 'RMA7')]);
    assert(other[0].size === 0, 'same time but other radar does not match');
}

console.log('T6: displayedCogTimeSpan ignores empty slots, null when no COGs');
{
    const frames = buildGridFrames(cogs, 10, new Date('2026-10-20T22:00:00Z'), new Date('2026-10-20T23:00:00Z'));
    const span = displayedCogTimeSpan(frames);
    assert(span.from.toISOString() === '2026-10-20T22:13:32.000Z', 'span starts at first displayed COG');
    assert(span.to.toISOString() === '2026-10-20T22:53:30.000Z', 'span ends at last displayed COG');
    assert(displayedCogTimeSpan([{ cogsByRadar: {} }]) === null, 'null for COG-less frames');
}

console.log('T7: recordKey is stable across ISO formats of the same instant');
{
    assert(recordKey('A', '0315', '01', '2026-10-20T22:22:35Z') === recordKey('A', '0315', '01', '2026-10-20T22:22:35.000Z'),
        'Z vs .000Z identical');
}

console.log(`\n${'─'.repeat(40)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) { console.error('TESTS FAILED'); process.exit(1); }
else console.log('ALL TESTS PASSED');
