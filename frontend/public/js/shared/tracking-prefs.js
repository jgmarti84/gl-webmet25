/**
 * Saved choices and request shape for the single-radar view's tracking tool.
 * Pure functions (no DOM, no fetch), so they can be tested with node.
 */

/** "Track the last N volumes" choices offered in the panel. */
export const LAST_N_CHOICES = [3, 5, 10];
export const DEFAULT_LAST_N = 3;

/**
 * The saved N, if it is one of the choices and within the service's cap;
 * otherwise the largest choice that fits, falling back to the default.
 */
export function restoreLastN(raw, maxLastN = Infinity) {
    const allowed = LAST_N_CHOICES.filter(n => n <= maxLastN);
    const n = Number(raw);
    if (allowed.includes(n)) return n;
    if (allowed.includes(DEFAULT_LAST_N)) return DEFAULT_LAST_N;
    return allowed.length ? allowed[allowed.length - 1] : DEFAULT_LAST_N;
}

/**
 * The saved forecast leads: a JSON list, kept only where it names leads that
 * exist. Missing or unreadable -> the defaults. An empty list is a real
 * choice (no forecasts) and is kept.
 */
export function restoreLeads(raw, allLeads, defaults) {
    let saved;
    try { saved = JSON.parse(raw); } catch { return [...defaults]; }
    if (!Array.isArray(saved)) return [...defaults];
    return allLeads.filter(lead => saved.map(Number).includes(lead));
}

/**
 * The tracking request for the view's window. The window inputs hold whole
 * minutes, so the newest volume (e.g. 14:32:45 shown as 14:32) would fall
 * just past `end`; one minute of slack keeps it in. null without a window.
 */
export function trackingRequest(radar, window, lastN, config) {
    if (!window?.start || !window?.end) return null;
    const start = new Date(window.start);
    const end = new Date(new Date(window.end).getTime() + 60 * 1000);
    if (!(start < end)) return null;
    return { radar, start: start.toISOString(), end: end.toISOString(), lastN, config };
}
