/**
 * Pure helpers that pair tracking frames (one per NC cube) with the COLMAX COG
 * of the same volume. No DOM / Leaflet dependencies (unit-testable).
 *
 * A cube and its volume's COLMAX share the volume's timestamp, but several
 * volumes can produce a COLMAX in the same minute (e.g. vol 01 at 22:45:47 and
 * the single-elevation vol 04 at 22:45:27). So COGs are bucketed by minute and
 * the one closest in time to the frame wins — the cube's own volume — instead
 * of whichever happened to be stored last for that minute.
 */

/** "2026-10-28T22:45:47Z" -> "2026-10-28T22:45" (both sides are UTC ISO strings). */
export const isoMinute = iso => String(iso).slice(0, 16);

/** Add COGs (with a bbox) to `index`: Map<minute, cog[]>. Returns the index. */
export function indexCogsByMinute(index, cogs) {
    for (const cog of cogs || []) {
        if (!cog?.bbox) continue;
        const key = isoMinute(cog.observation_time);
        const list = index.get(key) || [];
        list.push(cog);
        index.set(key, list);
    }
    return index;
}

/** The COG in `index` closest in time to `iso` (same minute), or undefined. */
export function closestCog(index, iso) {
    const list = index.get(isoMinute(iso));
    if (!list?.length) return undefined;
    const t = Date.parse(iso);
    let best = list[0];
    for (const cog of list) {
        if (Math.abs(Date.parse(cog.observation_time) - t) < Math.abs(Date.parse(best.observation_time) - t)) {
            best = cog;
        }
    }
    return best;
}
