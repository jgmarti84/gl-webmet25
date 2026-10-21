/**
 * Pure helpers that pair tops/cores records with the COGs actually displayed
 * in the animation frames. No DOM / Leaflet dependencies (unit-testable).
 *
 * A tops/cores record belongs to a COG when radar_code, strategy, vol_nr and
 * observation_time are all identical — both are produced from the same volume.
 * Matching by the displayed COG (instead of by distance to the frame's slot
 * time) keeps markers consistent with the image even when several scans fall
 * in one slot, a slot has none, or the image is held from the previous frame.
 */

/**
 * @param {string} radarCode
 * @param {string} strategy
 * @param {string} volNr
 * @param {string|number|Date} observationTime
 * @returns {string}
 */
export function recordKey(radarCode, strategy, volNr, observationTime) {
    return `${radarCode}|${strategy}|${volNr}|${new Date(observationTime).getTime()}`;
}

/**
 * Time span covering every COG displayed in the frames (empty slots are
 * ignored: they carry no COG).
 *
 * @param {Array} frames  [{cogsByRadar: {code: cog}}, …]
 * @returns {{from: Date, to: Date}|null}  null when no frame has a COG
 */
export function displayedCogTimeSpan(frames) {
    let min = Infinity;
    let max = -Infinity;
    frames.forEach(f => {
        Object.values(f.cogsByRadar || {}).forEach(cog => {
            const t = new Date(cog.observation_time).getTime();
            if (t < min) min = t;
            if (t > max) max = t;
        });
    });
    return Number.isFinite(min) ? { from: new Date(min), to: new Date(max) } : null;
}

/**
 * For each frame, find the record belonging to each displayed COG.
 *
 * @param {Array} frames   [{cogsByRadar: {code: cog}}, …]
 * @param {Array} records  tops/cores metadata records ({radar_code, strategy,
 *                         vol_nr, observation_time, …})
 * @returns {Array<Map<string, number>>}  one Map per frame: radar_code → index
 *   into `records`. Radars whose displayed COG has no record are absent.
 */
export function matchRecordsToFrames(frames, records) {
    const byKey = new Map();
    records.forEach((rec, i) => {
        byKey.set(recordKey(rec.radar_code, rec.strategy, rec.vol_nr, rec.observation_time), i);
    });

    return frames.map(frame => {
        const matches = new Map();
        Object.entries(frame.cogsByRadar || {}).forEach(([code, cog]) => {
            const idx = byKey.get(recordKey(cog.radar_code ?? code, cog.strategy, cog.vol_nr, cog.observation_time));
            if (idx !== undefined) matches.set(code, idx);
        });
        return matches;
    });
}
