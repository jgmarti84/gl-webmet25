/**
 * Controls Module - Handles UI control interactions
 */

import { TimeWheel } from './time-wheel.js';

// Fix 3: message queue constants
const MSG_AUTO_CLEAR_MS  = 4000; // non-error messages auto-clear after 4 s
const MSG_MIN_DISPLAY_MS = 2000; // minimum time each message stays visible

export class UIControls {
    constructor() {
        this.handlers = {};

        // Fix 3: queue-based status message system
        this._msgQueue  = [];      // pending messages
        this._msgTimer  = null;    // setInterval for advancing the queue
        this._clearTimer = null;   // setTimeout for auto-clearing the current message
        this._msgShownAt = 0;      // timestamp when the current message was shown
    }

    // -------------------------------------------------------------------------
    // Fix 3: Status message system
    // Messages are shown in a dedicated fixed-height area below the animation
    // controls at the bottom centre of the page.  Each message stays visible for
    // at least MSG_MIN_DISPLAY_MS so rapid successive messages do not flash.
    // Non-error messages are auto-cleared after MSG_AUTO_CLEAR_MS.
    // Error messages persist until replaced.
    // -------------------------------------------------------------------------

    /**
     * Queue a status message.
     *
     * @param {string} message - Text to display
     * @param {string} type    - '' | 'loading' | 'error' | 'success'
     */
    setStatus(message, type = '') {
        this._msgQueue.push({ message, type });
        this._drainQueue();
    }

    /** Advance the message queue if possible. */
    _drainQueue() {
        if (this._msgQueue.length === 0) return;

        const now = Date.now();
        const elapsed = now - this._msgShownAt;

        if (this._msgShownAt > 0 && elapsed < MSG_MIN_DISPLAY_MS) {
            // Current message hasn't been visible long enough — schedule a retry
            if (!this._msgTimer) {
                this._msgTimer = setTimeout(() => {
                    this._msgTimer = null;
                    this._drainQueue();
                }, MSG_MIN_DISPLAY_MS - elapsed);
            }
            return;
        }

        // Show the next message
        const { message, type } = this._msgQueue.shift();
        this._showMessage(message, type);
    }

    /** Render a message into the #message-area element. */
    _showMessage(message, type) {
        if (this._clearTimer) {
            clearTimeout(this._clearTimer);
            this._clearTimer = null;
        }

        const area = document.getElementById('message-area');
        const text = document.getElementById('message-text');
        if (!area || !text) return;

        text.textContent = message;
        // Remove old type classes and apply new one
        area.className = 'message-area';
        if (type) area.classList.add(type);
        area.classList.add('visible');

        this._msgShownAt = Date.now();

        // Auto-clear non-error messages after MSG_AUTO_CLEAR_MS
        if (type !== 'error') {
            this._clearTimer = setTimeout(() => {
                this._clearTimer = null;
                // If there's another queued message show it; otherwise fade out
                if (this._msgQueue.length > 0) {
                    this._drainQueue();
                } else {
                    area.classList.remove('visible');
                    this._msgShownAt = 0;
                }
            }, MSG_AUTO_CLEAR_MS);
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
     * Populate product select with filtered/unfiltered products.
     *
     * @param {Array}   allProducts             - Full product list from API
     * @param {boolean} showUnfiltered          - true = show raw ('o' suffix) products
     * @param {boolean} filteredFieldsAvailable - When false (e.g. VIG mode) only raw
     *                                            products are shown regardless of the
     *                                            showUnfiltered toggle, because filtered
     *                                            fields simply do not exist for that mode.
     */
    populateProductSelect(allProducts, showUnfiltered = false, filteredFieldsAvailable = true) {
        const select = document.getElementById('product-select');
        if (!select) return;

        // When filtered fields are not available for the current coverage mode,
        // always show only raw/unfiltered products irrespective of the user toggle.
        const effectiveShowUnfiltered = filteredFieldsAvailable ? showUnfiltered : true;

        // Filter products based on whether they end with 'o' (unfiltered) or not (filtered)
        // Check for uppercase letter followed by lowercase 'o' at the end (e.g., RHOHVo, COLMAXo)
        const filteredProducts = allProducts.filter(product => {
            const productKey = product.product_key;
            const isUnfiltered = /o$/.test(productKey); // product_key ends with 'o' = raw/unfiltered data
            return effectiveShowUnfiltered ? isUnfiltered : !isUnfiltered;
        });
        
        // Populate the select
        this.populateSelect('product-select', filteredProducts, 'product_key', 'product_title', 'Select product...');
    }

    /**
     * Enable or disable the filtered-fields toggle.
     * Called when the coverage mode changes: in modes where only raw/unfiltered
     * fields exist the toggle is meaningless and should be disabled.
     *
     * @param {boolean} enabled
     */
    setFilterToggleEnabled(enabled) {
        const toggle = document.getElementById('toggle-show-filtered');
        if (toggle) toggle.disabled = !enabled;
    }
    
    /**
     * Change 2: Sync the "Filtered" toggle checkbox to application state.
     * Replaces the old button-based updateFilterButton().
     *
     * @param {boolean} showFiltered - true = show 'o'-suffix (raw) products
     */
    updateFilterToggle(showFiltered) {
        const toggle = document.getElementById('toggle-show-filtered');
        // Invert: toggle ON means filtered shown (showUnfilteredProducts=false),
        // so checked = !showUnfilteredProducts (i.e. !showFiltered)
        if (toggle) toggle.checked = !showFiltered;
    }

    /**
     * @deprecated Use updateFilterToggle() instead.
     * Kept as a no-op alias to avoid runtime errors from any missed call sites.
     */
    updateFilterButton() {}

    /**
     * Update Module A and Module B icon-bar badges.
     *
     * @param {number} selectedRadarCount - How many radars are currently checked
     * @param {string|null} selectedProduct - Currently selected product_key (or null)
     */
    updateModuleBadges(selectedRadarCount, selectedProduct) {
        const badgeA = document.getElementById('badge-module-a');
        if (badgeA) badgeA.textContent = String(selectedRadarCount || 0);

        const badgeB = document.getElementById('badge-module-b');
        if (badgeB) badgeB.textContent = selectedProduct || '—';
    }
    
    /**
     * Enable/disable navigation buttons
     */
    enableNavButtons(enabled) {
        const buttons = ['btn-first', 'btn-prev', 'btn-next', 'btn-latest'];
        buttons.forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.disabled = !enabled;
        });
    }
    
    /**
     * Enable/disable animation controls
     */
    enableAnimationControls(enabled) {
        const controls = ['btn-play-pause', 'speed-slider', 'animation-slider'];
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
     * @param {Array} radars - Array of radar objects (must include is_active field)
     * @param {boolean} showInactive - If true, inactive radars are visible but dimmed
     */
    /**
     * Order radars for the selection list:
     *   1. active before inactive
     *   2. RMA group before AR group (then any other prefix)
     *   3. numeric ascending within a group, with number 0 (e.g. RMA00) sorted last
     */
    sortRadarsForDisplay(radars) {
        const keyOf = (radar) => {
            const code = (radar.code || '').toUpperCase();
            const match = code.match(/^([A-Z]+)(\d+)$/);
            const prefix = match ? match[1] : code;
            const num = match ? parseInt(match[2], 10) : Number.MAX_SAFE_INTEGER;
            const prefixOrder = prefix === 'RMA' ? 0 : prefix === 'AR' ? 1 : 2;
            // 0 (RMA00) goes last within its prefix.
            const numKey = num === 0 ? Number.MAX_SAFE_INTEGER : num;
            return { prefixOrder, numKey, code };
        };
        return [...radars].sort((a, b) => {
            if (Boolean(a.is_active) !== Boolean(b.is_active)) {
                return a.is_active ? -1 : 1;
            }
            const ka = keyOf(a);
            const kb = keyOf(b);
            if (ka.prefixOrder !== kb.prefixOrder) return ka.prefixOrder - kb.prefixOrder;
            if (ka.numKey !== kb.numKey) return ka.numKey - kb.numKey;
            return ka.code.localeCompare(kb.code);
        });
    }

    populateRadarCheckboxes(radars, showInactive = false) {
        const container = document.getElementById('radar-list');
        if (!container) return;

        container.innerHTML = '';

        this.sortRadarsForDisplay(radars).forEach(radar => {
            const item = document.createElement('div');
            item.className = 'radar-checkbox-item';
            if (!radar.is_active) {
                item.classList.add('radar-inactive');
            }
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `radar-${radar.code}`;
            checkbox.value = radar.code;
            checkbox.className = 'radar-checkbox';
            
            const dot = document.createElement('span');
            dot.className = `radar-status-dot ${radar.is_active ? 'radar-status-active' : 'radar-status-inactive'}`;
            dot.title = radar.is_active ? 'Active' : 'Inactive';
            
            const label = document.createElement('label');
            label.htmlFor = `radar-${radar.code}`;
            label.textContent = `${radar.code} - ${radar.title}`;
            
            item.appendChild(checkbox);
            item.appendChild(dot);
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

        // Keep the visible date input + time wheel in sync with the canonical value.
        this._syncCompositeFromCanonical('start');
        this._syncCompositeFromCanonical('end');
    }

    // ── iOS-style time wheels for the custom range ──────────────────────────
    // The hidden `#start-date` / `#end-date` datetime-local inputs remain the
    // single source of truth; the date input + TimeWheel just drive them.

    initTimeWheels() {
        const startWheelEl = document.getElementById('start-time-wheel');
        const endWheelEl = document.getElementById('end-time-wheel');
        if (startWheelEl && !this.startWheel) {
            this.startWheel = new TimeWheel(startWheelEl, { onChange: () => this._composeDateTime('start') });
        }
        if (endWheelEl && !this.endWheel) {
            this.endWheel = new TimeWheel(endWheelEl, { onChange: () => this._composeDateTime('end') });
        }
        ['start', 'end'].forEach((prefix) => {
            const dateInput = document.getElementById(`${prefix}-date-date`);
            if (dateInput && !dateInput.dataset.bound) {
                dateInput.dataset.bound = '1';
                dateInput.addEventListener('change', () => this._composeDateTime(prefix));
            }
        });
    }

    /** Re-center wheels + re-sync from canonical after the panel becomes visible. */
    refreshTimeWheels() {
        this._syncCompositeFromCanonical('start');
        this._syncCompositeFromCanonical('end');
        if (this.startWheel) this.startWheel.refresh();
        if (this.endWheel) this.endWheel.refresh();
    }

    /** Combine the date input + wheel into the canonical datetime-local input. */
    _composeDateTime(prefix) {
        const dateInput = document.getElementById(`${prefix}-date-date`);
        const canonical = document.getElementById(`${prefix}-date`);
        const wheel = prefix === 'start' ? this.startWheel : this.endWheel;
        if (!dateInput || !canonical || !wheel) return;
        if (!dateInput.value) {
            canonical.value = '';
        } else {
            const hh = String(wheel.hour).padStart(2, '0');
            const mm = String(wheel.minute).padStart(2, '0');
            canonical.value = `${dateInput.value}T${hh}:${mm}`;
        }
        canonical.dispatchEvent(new Event('change', { bubbles: true }));
    }

    /** Push the canonical datetime-local value into the date input + wheel. */
    _syncCompositeFromCanonical(prefix) {
        const canonical = document.getElementById(`${prefix}-date`);
        const dateInput = document.getElementById(`${prefix}-date-date`);
        const wheel = prefix === 'start' ? this.startWheel : this.endWheel;
        if (!canonical || !canonical.value) return;
        const dt = new Date(canonical.value);
        if (Number.isNaN(dt.getTime())) return;
        if (dateInput) {
            const y = dt.getFullYear();
            const m = String(dt.getMonth() + 1).padStart(2, '0');
            const d = String(dt.getDate()).padStart(2, '0');
            dateInput.value = `${y}-${m}-${d}`;
        }
        if (wheel) wheel.set(dt.getHours(), dt.getMinutes());
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
     * Show a semi-transparent loading overlay on top of the map.
     * The overlay is created dynamically on first call and reused thereafter.
     * @param {string} message - Text shown inside the overlay
     */
    showMapOverlay(message = 'Loading\u2026') {
        let overlay = document.getElementById('map-loading-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'map-loading-overlay';
            overlay.style.cssText = [
                'position:absolute',
                'top:0',
                'left:0',
                'width:100%',
                'height:100%',
                'background:rgba(0,0,0,0.45)',
                'display:flex',
                'align-items:center',
                'justify-content:center',
                'z-index:1000',
                'color:#fff',
                'font-size:1.1rem',
                'font-weight:600',
                'pointer-events:none',
                'border-radius:inherit',
            ].join(';');
            const mapEl = document.getElementById('map');
            if (mapEl) {
                if (window.getComputedStyle(mapEl).position === 'static') {
                    mapEl.style.position = 'relative';
                }
                mapEl.appendChild(overlay);
            }
        }
        overlay.textContent = message;
        overlay.style.display = 'flex';
    }

    /**
     * Update the text of a visible map overlay without showing/hiding it.
     * @param {string} message - New text to display
     */
    updateMapOverlay(message) {
        const overlay = document.getElementById('map-loading-overlay');
        if (overlay && overlay.style.display !== 'none') {
            overlay.textContent = message;
        }
    }

    /**
     * Hide the map loading overlay.
     */
    hideMapOverlay() {
        const overlay = document.getElementById('map-loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    /**
     * Get selected value from dropdown
     */
    getSelectedValue(selectId) {
        const select = document.getElementById(selectId);
        return select ? select.value : null;
    }
}
