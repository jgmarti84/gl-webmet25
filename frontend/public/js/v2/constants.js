// =============================================================================
// COVERAGE MODES — single source of truth for volume↔mode mapping.
// Each entry defines which volumes (and strategy) belong to that mode, and
// whether filtered (non-'o') fields should be available to the user.
// Add / edit entries here to extend modes in the future.
// =============================================================================

export const COVERAGE_MODES = [
    {
        id:    'cd',
        label: 'C+D',
        // Each clause is a non-overlapping (strategy × volNrs) pair.
        // The API is queried once per clause; results are merged.
        include: [
            { strategy: ['0315'], volNrs: ['01', '02'] },   // RMA multi-field sweeps
            { strategy: ['1000'], volNrs: ['02', '03'] },   // AR C+D sweeps (VRAD + DBZH + COLMAX)
        ],
        filteredFieldsAvailable: true,
        // Field selected when switching INTO this mode and the previous field
        // is not available here (see the coverage-mode handler).
        defaultProductKey: 'COLMAXo',
    },
    {
        id:    'vig',
        label: 'VIG',
        include: [
            { strategy: ['0315'], volNrs: ['04'] },          // RMA wide-area surveillance
            { strategy: ['1000'], volNrs: ['01'] },          // AR wide-area surveillance (400 km)
        ],
        filteredFieldsAvailable: false,
        defaultProductKey: 'DBZHo',
    },
];

// =============================================================================
// CONSTANTS (identical to app.js)
// =============================================================================

export const MS_PER_HOUR = 3600 * 1000;
export const BUCKET_TOLERANCE_MINUTES = 5;
export const DEFAULT_LIVE_REFRESH_INTERVAL_MS = 1 * 60 * 1000;
export const DEFAULT_RADAR_STATUS_REFRESH_INTERVAL_MS = 10 * 60 * 1000;
export const LIVE_REFRESH_MAX_COGS = 200;
export const GEOLOCATION_AUTO_SELECT_COUNT = 3;
export const GEOLOCATION_AUTO_LOAD_HOURS = 1.5;
export const GEOLOCATION_AUTO_PRODUCT = 'COLMAX';
export const DEFAULT_TIME_WINDOW_HOURS = 1.5;
export const DEFAULT_FIELD_OPACITY = 0.7;
export const DEFAULT_COVERAGE_OPACITY = 0.4;