/**
 * Controls Module - Handles UI control interactions
 */

export class UIControls {
    constructor() {
        this.handlers = {};
    }
    
    /**
     * Set status message
     */
    setStatus(message, type = '') {
        const status = document.getElementById('status');
        if (status) {
            status.textContent = message;
            status.className = `status ${type}`;
        }
    }
    
    /**
     * Update time display
     */
    setTimeDisplay(dateString) {
        const display = document.getElementById('time-display');
        if (!display) return;
        
        if (!dateString) {
            display.textContent = '--:--';
            return;
        }
        
        const date = new Date(dateString);
        display.textContent = date.toLocaleString('es-AR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'America/Argentina/Buenos_Aires',
        });
    }
    
    /**
     * Populate a select dropdown with optional filtering
     */
    populateSelect(selectId, items, valueKey, labelKey, placeholder = 'Select...') {
        const select = document.getElementById(selectId);
        if (!select) return;
        
        select.innerHTML = `<option value="">${placeholder}</option>`;
        
        items.forEach(item => {
            const option = document.createElement('option');
            option.value = item[valueKey];
            option.textContent = item[labelKey];
            select.appendChild(option);
        });
    }
    
    /**
     * Populate product select with filtered/unfiltered products
     */
    populateProductSelect(allProducts, showUnfiltered = false) {
        const select = document.getElementById('product-select');
        if (!select) return;
        
        // Filter products based on whether they end with 'o' (unfiltered) or not (filtered)
        // Check for uppercase letter followed by lowercase 'o' at the end (e.g., RHOHVo, COLMAXo)
        const filteredProducts = allProducts.filter(product => {
            const productKey = product.product_key;
            const isUnfiltered = /[A-Z]o$/.test(productKey); // Uppercase letter + lowercase 'o' at end
            return showUnfiltered ? isUnfiltered : !isUnfiltered;
        });
        
        // Populate the select
        this.populateSelect('product-select', filteredProducts, 'product_key', 'product_title', 'Select product...');
    }
    
    /**
     * Update filter button appearance
     */
    updateFilterButton(showUnfiltered) {
        const btn = document.getElementById('btn-toggle-filter');
        const statusSpan = document.getElementById('filter-status');
        
        if (!btn || !statusSpan) return;
        
        if (showUnfiltered) {
            btn.classList.add('active');
            statusSpan.textContent = 'Unfiltered';
            btn.title = 'Showing unfiltered products (ending with "o")';
        } else {
            btn.classList.remove('active');
            statusSpan.textContent = 'Filtered';
            btn.title = 'Showing filtered products';
        }
    }
    
    /**
     * Enable/disable navigation buttons
     */
    enableNavButtons(enabled) {
        const buttons = ['btn-prev', 'btn-next', 'btn-latest'];
        buttons.forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.disabled = !enabled;
        });
    }
    
    /**
     * Enable/disable animation controls
     */
    enableAnimationControls(enabled) {
        const controls = ['btn-play-pause', 'btn-speed', 'animation-slider'];
        controls.forEach(id => {
            const element = document.getElementById(id);
            if (element) element.disabled = !enabled;
        });
    }
    
    /**
     * Update play/pause button
     */
    updatePlayButton(isPlaying) {
        const btn = document.getElementById('btn-play-pause');
        if (!btn) return;
        
        if (isPlaying) {
            btn.innerHTML = '⏸';
            btn.title = 'Pause';
        } else {
            btn.innerHTML = '▶';
            btn.title = 'Play';
        }
    }
    
    /**
     * Update speed button
     */
    updateSpeedButton(speed) {
        const btn = document.getElementById('btn-speed');
        if (!btn) return;
        
        btn.textContent = `${speed}x`;
        btn.title = `Speed: ${speed}x`;
    }
    
    /**
     * Update animation slider
     */
    updateAnimationSlider(currentIndex, totalFrames) {
        const slider = document.getElementById('animation-slider');
        if (!slider) return;
        
        slider.max = totalFrames - 1;
        slider.value = currentIndex;
    }
    
    /**
     * Update frame counter
     */
    updateFrameCounter(currentIndex, totalFrames) {
        const counter = document.getElementById('frame-counter');
        if (!counter) return;
        
        counter.textContent = `${currentIndex + 1} / ${totalFrames}`;
    }
    
    /**
     * Update opacity display
     */
    updateOpacityDisplay(opacity) {
        const display = document.getElementById('opacity-value');
        if (!display) return;
        
        display.textContent = `${Math.round(opacity * 100)}%`;
    }
    
    /**
     * Populate radar checkboxes
     */
    populateRadarCheckboxes(radars) {
        const container = document.getElementById('radar-list');
        if (!container) return;
        
        container.innerHTML = '';
        
        radars.forEach(radar => {
            const item = document.createElement('div');
            item.className = 'radar-checkbox-item';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `radar-${radar.code}`;
            checkbox.value = radar.code;
            checkbox.className = 'radar-checkbox';
            
            const label = document.createElement('label');
            label.htmlFor = `radar-${radar.code}`;
            label.textContent = radar.title;
            
            item.appendChild(checkbox);
            item.appendChild(label);
            container.appendChild(item);
        });
    }
    
    /**
     * Get selected radar codes
     */
    getSelectedRadars() {
        const checkboxes = document.querySelectorAll('.radar-checkbox:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    }
    
    /**
     * Select all radars
     */
    selectAllRadars() {
        const checkboxes = document.querySelectorAll('.radar-checkbox');
        checkboxes.forEach(cb => cb.checked = true);
    }
    
    /**
     * Clear all radar selections
     */
    clearAllRadars() {
        const checkboxes = document.querySelectorAll('.radar-checkbox');
        checkboxes.forEach(cb => cb.checked = false);
    }
    
    /**
     * Enable/disable load latest button
     */
    enableLoadLatestButton(enabled) {
        const btn = document.getElementById('btn-load-latest');
        if (btn) btn.disabled = !enabled;
    }
    
    /**
     * Enable/disable load time range button
     */
    enableLoadTimeRangeButton(enabled) {
        const btn = document.getElementById('btn-load-timerange');
        if (btn) btn.disabled = !enabled;
    }
    
    /**
     * Set time range input values
     */
    setTimeRangeValues(startDate, endDate) {
        const startInput = document.getElementById('start-date');
        const endInput = document.getElementById('end-date');
        
        if (startInput && startDate) {
            startInput.value = this.formatDateTimeLocal(startDate);
        }
        
        if (endInput && endDate) {
            endInput.value = this.formatDateTimeLocal(endDate);
        }
    }
    
    /**
     * Get time range input values as Date objects
     */
    getTimeRangeValues() {
        const startInput = document.getElementById('start-date');
        const endInput = document.getElementById('end-date');
        
        const startValue = startInput ? startInput.value : null;
        const endValue = endInput ? endInput.value : null;
        
        return {
            start: startValue ? new Date(startValue) : null,
            end: endValue ? new Date(endValue) : null,
        };
    }
    
    /**
     * Format Date object for datetime-local input
     */
    formatDateTimeLocal(date) {
        if (!date) return '';
        
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    }
    
    /**
     * Get selected value from dropdown
     */
    getSelectedValue(selectId) {
        const select = document.getElementById(selectId);
        return select ? select.value : null;
    }
}
