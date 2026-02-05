/**
 * Legend Module - Renders color legend for radar products
 */

export class LegendRenderer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentColormap = null;
    }
    
    /**
     * Render legend from colormap data
     */
    render(colormapData) {
        if (!this.container) return;
        
        this.currentColormap = colormapData;
        
        // Clear existing content
        this.container.innerHTML = '';
        
        if (!colormapData || !colormapData.entries || colormapData.entries.length === 0) {
            return;
        }
        
        // Create legend title
        const title = document.createElement('div');
        title.className = 'legend-title';
        title.textContent = colormapData.product_key || 'Legend';
        this.container.appendChild(title);
        
        // Create scale container
        const scale = document.createElement('div');
        scale.className = 'legend-scale';
        
        // Render entries - API returns sorted ascending by value, reverse to show high values at top
        // Note: If your colormap API returns entries in a different order, adjust accordingly
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
        
        this.container.appendChild(scale);
        
        // Add unit if available
        if (colormapData.unit) {
            const unit = document.createElement('div');
            unit.className = 'legend-unit';
            unit.textContent = colormapData.unit;
            this.container.appendChild(unit);
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
