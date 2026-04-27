/**
 * Legend Module - Renders color legend for radar products
 */

// Configuration constants
// Max discrete color stops shown in legend (Fix 4: reduce for readability)
const MAX_LEGEND_STOPS = 8;

/**
 * Choose the number of decimal places for legend value labels based on range.
 * Fix 4: Smart decimal logic — integers for wide ranges, 1-2 decimals for narrow.
 *
 * @param {number} range - vmax - vmin
 * @returns {number} decimal places (0, 1, or 2)
 */
function legendDecimalPlaces(range) {
    if (range >= 10) return 0;
    if (range >= 1)  return 1;
    return 2;
}

export class LegendRenderer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentColormap = null;
    }
    
    /**
     * Render legend from new colormap data format
     * Supports both old format (entries array) and new format (colors array with vmin/vmax)
     */
    render(colormapData) {
        if (!this.container) return;
        
        this.currentColormap = colormapData;
        
        // Clear existing content
        this.container.innerHTML = '';
        
        if (!colormapData) {
            return;
        }
        
        // Create legend title
        const title = document.createElement('div');
        title.className = 'legend-title';
        title.textContent = colormapData.product_key || colormapData.colormap || 'Legend';
        this.container.appendChild(title);
        
        // Create scale container
        const scale = document.createElement('div');
        scale.className = 'legend-scale';
        
        // Handle new format (colors array with vmin/vmax)
        if (colormapData.colors && Array.isArray(colormapData.colors)) {
            const colors = colormapData.colors;
            const vmin = colormapData.vmin ?? 0;
            const vmax = colormapData.vmax ?? 100;
            // Fallback values (0 / 100) are generic defaults used only when
            // the API response is missing vmin/vmax — this should not happen in
            // normal operation since the API always returns these values.  If
            // they are missing, the legend will still render but colour-to-value
            // mapping will be approximate until real data is loaded.
            const range = vmax - vmin;
            const decimals = legendDecimalPlaces(range);
            
            // Fix 4: Use at most MAX_LEGEND_STOPS evenly-spaced stops.
            // High values appear at the top; low values at the bottom.
            const numStops = Math.min(MAX_LEGEND_STOPS, colors.length);
            
            // Iterate from high (top) to low (bottom): i goes numStops-1 → 0
            for (let i = numStops - 1; i >= 0; i--) {
                // fraction goes 1 → 0 as i goes numStops-1 → 0
                const fraction = (numStops === 1) ? 1 : i / (numStops - 1);
                const colorIndex = Math.round(fraction * (colors.length - 1));
                const value = vmin + fraction * range;
                
                const item = document.createElement('div');
                item.className = 'legend-item';
                
                // Color box
                const colorBox = document.createElement('div');
                colorBox.className = 'legend-color';
                colorBox.style.backgroundColor = colors[colorIndex];
                
                // Value label — smart decimal formatting (Fix 4)
                const valueLabel = document.createElement('div');
                valueLabel.className = 'legend-value';
                valueLabel.textContent = value.toFixed(decimals);
                
                item.appendChild(colorBox);
                item.appendChild(valueLabel);
                scale.appendChild(item);
            }
        }
        // Handle old format (entries array) - for backwards compatibility
        else if (colormapData.entries && colormapData.entries.length > 0) {
            // Fix 4: subsample entries to MAX_LEGEND_STOPS for readability
            const allEntries = [...colormapData.entries].reverse();
            const step = allEntries.length <= MAX_LEGEND_STOPS
                ? 1
                : Math.ceil(allEntries.length / MAX_LEGEND_STOPS);
            const entries = allEntries.filter((_, idx) => idx % step === 0);
            
            entries.forEach(entry => {
                const item = document.createElement('div');
                item.className = 'legend-item';
                item.title = entry.label || '';
                
                // Color box
                const colorBox = document.createElement('div');
                colorBox.className = 'legend-color';
                colorBox.style.backgroundColor = entry.color;
                
                // Value label
                const valueLabel = document.createElement('div');
                valueLabel.className = 'legend-value';
                valueLabel.textContent = entry.value;
                
                item.appendChild(colorBox);
                item.appendChild(valueLabel);
                scale.appendChild(item);
            });
        }
        
        this.container.appendChild(scale);
        
        // Add unit if available
        const unit = colormapData.unit || '';
        if (unit) {
            const unitEl = document.createElement('div');
            unitEl.className = 'legend-unit';
            unitEl.textContent = unit;
            this.container.appendChild(unitEl);
        }
    }
    
    /**
     * Clear legend
     */
    clear() {
        if (this.container) {
            this.container.innerHTML = '';
        }
        this.currentColormap = null;
    }
    
    /**
     * Show legend
     */
    show() {
        if (this.container) {
            this.container.style.display = 'block';
        }
    }
    
    /**
     * Hide legend
     */
    hide() {
        if (this.container) {
            this.container.style.display = 'none';
        }
    }
}
