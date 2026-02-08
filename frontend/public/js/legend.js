/**
 * Legend Module - Renders color legend for radar products
 */

// Configuration constants
const MAX_LEGEND_STOPS = 15;  // Maximum number of color stops to display in legend

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
            const vmin = colormapData.vmin || 0;
            const vmax = colormapData.vmax || 100;
            
            // Show approximately 10-15 color stops for the legend
            const numStops = Math.min(MAX_LEGEND_STOPS, colors.length);
            const step = Math.floor(colors.length / numStops);
            
            // Reverse to show high values at top
            for (let i = numStops - 1; i >= 0; i--) {
                const colorIndex = i * step;
                const value = vmin + (colorIndex / colors.length) * (vmax - vmin);
                
                const item = document.createElement('div');
                item.className = 'legend-item';
                
                // Color box
                const colorBox = document.createElement('div');
                colorBox.className = 'legend-color';
                colorBox.style.backgroundColor = colors[colorIndex];
                
                // Value label
                const valueLabel = document.createElement('div');
                valueLabel.className = 'legend-value';
                valueLabel.textContent = value.toFixed(1);
                
                item.appendChild(colorBox);
                item.appendChild(valueLabel);
                scale.appendChild(item);
            }
        }
        // Handle old format (entries array) - for backwards compatibility
        else if (colormapData.entries && colormapData.entries.length > 0) {
            const entries = [...colormapData.entries].reverse();
            
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
