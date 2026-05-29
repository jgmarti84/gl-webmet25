/**
 * Legend Module — Continuous gradient colormap legend.
 *
 * Layout (top → bottom):
 *   [title]
 *   [gradient bar]  |  [tick labels positioned absolutely]
 *   [unit]
 *
 * Tick source priority:
 *   1. colormapData.ticks  — Reference rows from the DB ({value, color}[])
 *   2. Auto: 5 evenly-spaced values across the display range
 */

/** Number of CSS gradient stops to sample from the colors array. */
const GRADIENT_SAMPLES = 32;

/** Number of auto ticks when no Reference rows are available. */
const AUTO_TICK_COUNT = 5;

/**
 * Choose decimal places for tick labels based on the display range width.
 * @param {number} range
 * @returns {number}
 */
function legendDecimalPlaces(range) {
    if (range >= 10) return 0;
    if (range >= 1)  return 1;
    return 2;
}

/**
 * Build a CSS linear-gradient string (bottom → top) from a hex color array.
 *
 * @param {string[]} colors       - Full colormap hex array (256 entries typical)
 * @param {number}   startFraction - Start of visible window within [0, 1]
 * @param {number}   endFraction   - End   of visible window within [0, 1]
 * @returns {string} CSS gradient value
 */
function buildGradient(colors, startFraction, endFraction) {
    const stops = [];
    for (let i = 0; i < GRADIENT_SAMPLES; i++) {
        // t: position within the display window, 0 (bottom) → 1 (top)
        const t = i / (GRADIENT_SAMPLES - 1);
        // map t to a position in the full colormap
        const fullFraction = startFraction + t * (endFraction - startFraction);
        const idx = Math.max(0, Math.min(colors.length - 1, Math.round(fullFraction * (colors.length - 1))));
        const pct = (t * 100).toFixed(1);
        stops.push(`${colors[idx]} ${pct}%`);
    }
    return `linear-gradient(to top, ${stops.join(', ')})`;
}

export class LegendRenderer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentColormap = null;
    }

    /**
     * Render the legend.
     *
     * @param {object} colormapData
     *   Expected shape:
     *     colors       {string[]}                        - hex color array (256 entries)
     *     vmin         {number}                          - full product range min
     *     vmax         {number}                          - full product range max
     *     ticks        {Array<{value:number, color:string}>} - Reference rows (may be empty)
     *     product_title {string}
     *     product_key   {string}
     *     unit          {string}
     *
     * @param {object} [filterOptions]
     *   filterVmin {number|null}
     *   filterVmax {number|null}
     */
    render(colormapData, filterOptions = {}) {
        if (!this.container) return;
        this.currentColormap = colormapData;
        this.container.innerHTML = '';

        if (!colormapData) return;

        // ── Title ──────────────────────────────────────────────────────────
        const title = document.createElement('div');
        title.className = 'legend-title';
        title.textContent = colormapData.product_title
            || colormapData.product_key
            || colormapData.colormap
            || 'Legend';
        this.container.appendChild(title);

        // ── Gradient bar (new format) ──────────────────────────────────────
        if (colormapData.colors && Array.isArray(colormapData.colors)) {
            const colors = colormapData.colors;
            const fullVmin = colormapData.vmin ?? 0;
            const fullVmax = colormapData.vmax ?? 100;
            const fullRange = fullVmax - fullVmin;

            const { filterVmin = null, filterVmax = null } = filterOptions;
            const displayVmin = filterVmin !== null ? filterVmin : fullVmin;
            const displayVmax = filterVmax !== null ? filterVmax : fullVmax;
            const displayRange = displayVmax - displayVmin;

            // Fractions of the full colormap covered by the display window
            const startFraction = fullRange > 0 ? (displayVmin - fullVmin) / fullRange : 0;
            const endFraction   = fullRange > 0 ? (displayVmax - fullVmin) / fullRange : 1;

            // ── Wrapper (bar + ticks side by side) ────────────────────────
            const wrapper = document.createElement('div');
            wrapper.className = 'legend-gradient-wrapper';

            // Gradient bar
            const bar = document.createElement('div');
            bar.className = 'legend-gradient-bar';
            bar.style.background = buildGradient(colors, startFraction, endFraction);
            wrapper.appendChild(bar);

            // Ticks container (absolutely positioned, same height as bar)
            const ticksEl = document.createElement('div');
            ticksEl.className = 'legend-ticks';

            const decimals = legendDecimalPlaces(Math.abs(displayRange));

            // Determine tick values
            let tickValues = [];

            if (colormapData.ticks && colormapData.ticks.length > 0) {
                // Use Reference rows — filter to those within the display range
                tickValues = colormapData.ticks
                    .map(t => t.value)
                    .filter(v => v >= displayVmin && v <= displayVmax);

                // Always include display endpoints
                if (tickValues.length === 0 || tickValues[0] > displayVmin) {
                    tickValues.unshift(displayVmin);
                }
                if (tickValues[tickValues.length - 1] < displayVmax) {
                    tickValues.push(displayVmax);
                }
            }

            // Fallback: auto ticks
            if (tickValues.length === 0) {
                for (let i = 0; i < AUTO_TICK_COUNT; i++) {
                    tickValues.push(displayVmin + (i / (AUTO_TICK_COUNT - 1)) * displayRange);
                }
            }

            tickValues.forEach(value => {
                // bottomPct: 0% = bottom (displayVmin), 100% = top (displayVmax)
                const fraction = displayRange > 0 ? (value - displayVmin) / displayRange : 0;
                const bottomPct = (Math.max(0, Math.min(1, fraction)) * 100).toFixed(2);

                const tick = document.createElement('div');
                tick.className = 'legend-tick';
                tick.style.bottom = `${bottomPct}%`;

                const line = document.createElement('div');
                line.className = 'legend-tick-line';

                const label = document.createElement('span');
                label.className = 'legend-tick-label';
                label.textContent = value.toFixed(decimals);

                tick.appendChild(line);
                tick.appendChild(label);
                ticksEl.appendChild(tick);
            });

            wrapper.appendChild(ticksEl);
            this.container.appendChild(wrapper);
        }
        // ── Legacy format (entries array) — kept for backward compatibility ─
        else if (colormapData.entries && colormapData.entries.length > 0) {
            const scale = document.createElement('div');
            scale.className = 'legend-scale';
            const MAX_STOPS = 8;
            const allEntries = [...colormapData.entries].reverse();
            const step = allEntries.length <= MAX_STOPS ? 1 : Math.ceil(allEntries.length / MAX_STOPS);
            allEntries.filter((_, idx) => idx % step === 0).forEach(entry => {
                const item = document.createElement('div');
                item.className = 'legend-item';
                const colorBox = document.createElement('div');
                colorBox.className = 'legend-color';
                colorBox.style.backgroundColor = entry.color;
                const valueLabel = document.createElement('div');
                valueLabel.className = 'legend-value';
                valueLabel.textContent = entry.value;
                item.appendChild(colorBox);
                item.appendChild(valueLabel);
                scale.appendChild(item);
            });
            this.container.appendChild(scale);
        }

        // ── Unit ───────────────────────────────────────────────────────────
        const unitText = (colormapData.unit && colormapData.unit.trim()) ? colormapData.unit.trim() : '?';
        const unitEl = document.createElement('div');
        unitEl.className = 'legend-unit';
        unitEl.textContent = unitText;
        this.container.appendChild(unitEl);
    }

    clear() {
        if (this.container) this.container.innerHTML = '';
        this.currentColormap = null;
    }

    show() {
        if (this.container) this.container.style.display = 'block';
    }

    hide() {
        if (this.container) this.container.style.display = 'none';
    }
}

