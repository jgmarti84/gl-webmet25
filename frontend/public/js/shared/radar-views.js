/**
 * One-radar detail views (spec C): small pure helpers shared by the map, radar.html and the admin panel.
 * No DOM here, so they can be tested with node.
 */

// Stored resource meaning "every radar, including future ones". /permissions/me never returns it: the API
// expands it to real codes. Only the admin panel sees it (in a user's saved list).
export const ALL_RADARS = '*';

/** True if `code` is in the resolved list from GET /permissions/me. */
export function canOpenDetailView(code, views) {
    return Array.isArray(views) && views.includes(code);
}

/** Short text for a saved list in the admin users table: "Ninguna", "Todas" or "RMA1, RMA17". */
export function viewsSummary(stored) {
    if (!stored || stored.length === 0) return 'Ninguna';
    if (stored.includes(ALL_RADARS)) return 'Todas';
    return stored.join(', ');
}
