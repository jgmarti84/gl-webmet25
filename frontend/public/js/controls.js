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
     * Populate a select dropdown
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
     * Get selected value from dropdown
     */
    getSelectedValue(selectId) {
        const select = document.getElementById(selectId);
        return select ? select.value : null;
    }
}
