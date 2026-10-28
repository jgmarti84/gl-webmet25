/**
 * Pure helpers that pair tops/cores records with the COGs actually displayed
 * in the animation frames. No DOM / Leaflet dependencies (unit-testable).
 *
 * A tops/cores record belongs to a COG when radar_code, strategy, vol_nr and
 * observation_time are all identical — both are produced from the same volume.
 *
 * Markers are looked up by that identity key, never by frame position, so
 * adding, removing or reordering frames (radar toggling, live refresh) can
 * never pair a frame with another scan's markers.
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
 * Identity key of a COG (same format as {@link recordKey}).
 * @param {{radar_code?: string, strategy: string, vol_nr: string, observation_time: string}} cog
 * @param {string} [fallbackRadar]  radar code to use when the COG object has none
 */
export function cogKey(cog, fallbackRadar) {
    return recordKey(cog.radar_code ?? fallbackRadar, cog.strategy, cog.vol_nr, cog.observation_time);
}

/**
 * Every distinct COG displayed in the frames (empty slots carry none).
 *
 * @param {Array} frames  [{cogsByRadar: {code: cog}}, …]
 * @returns {Map<string, object>}  cogKey → cog
 */
export function collectDisplayedCogs(frames) {
    const cogs = new Map();
    (frames || []).forEach(f => {
        Object.entries(f.cogsByRadar || {}).forEach(([code, cog]) => {
            cogs.set(cogKey(cog, code), cog);
        });
    });
    return cogs;
}

/**
 * Time span covering the given COGs.
 *
 * @param {Iterable<object>} cogs
 * @returns {{from: Date, to: Date}|null}  null when empty
 */
export function cogTimeSpan(cogs) {
    let min = Infinity;
    let max = -Infinity;
    for (const cog of cogs) {
        const t = new Date(cog.observation_time).getTime();
        if (t < min) min = t;
        if (t > max) max = t;
    }
    return Number.isFinite(min) ? { from: new Date(min), to: new Date(max) } : null;
}

/**
 * Records whose identity is among the wanted keys.
 *
 * @param {Array} records  tops/cores metadata records
 * @param {{has(key: string): boolean}} wantedKeys
 * @returns {Array}
 */
export function selectWantedRecords(records, wantedKeys) {
    return records.filter(rec =>
        wantedKeys.has(recordKey(rec.radar_code, rec.strategy, rec.vol_nr, rec.observation_time)));
}

/**
 * Markers to draw for a frame: for each radar, the markers of the COG that is
 * actually displayed. A held radar (absent from `frame`, image held from the
 * previous slot) uses the COG of `holdFrame`.
 *
 * @param {{cogsByRadar: object}} frame
 * @param {{cogsByRadar: object}|null} holdFrame  frame the held images come from
 * @param {string[]} holdRadarCodes
 * @param {Map<string, Array>} markersByKey  cogKey → marker-data[]
 * @returns {Array}
 */
export function markersForFrame(frame, holdFrame, holdRadarCodes, markersByKey) {
    if (!frame) return [];
    const held = new Set(holdRadarCodes || []);
    const codes = new Set([...Object.keys(frame.cogsByRadar || {}), ...held]);

    const markers = [];
    codes.forEach(code => {
        const source = held.has(code) ? holdFrame : frame;
        const cog = source && source.cogsByRadar ? source.cogsByRadar[code] : null;
        if (!cog) return;
        const data = markersByKey.get(cogKey(cog, code));
        if (data) markers.push(...data);
    });
    return markers;
}
