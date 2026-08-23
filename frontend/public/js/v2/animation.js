/**
 * animation-v2.js — requestAnimationFrame-based animation controller.
 *
 * Replaces the setInterval approach in v1's animation.js with a rAF loop.
 * The loop runs only when _playing === true.  Setting _playing = false stops
 * the loop without needing cancelAnimationFrame().
 *
 * Key differences from v1
 * -----------------------
 * - Uses requestAnimationFrame instead of setInterval.
 * - Calls mapManager.showFrame() directly (no intermediate tile layer lookup).
 * - Speed multiplier controls the minimum ms between frame advances.
 * - initControls() wires DOM elements and replaces app.js's inline listeners.
 */

// Frame interval is calculated dynamically: 1000ms / speedMultiplier (matches v1)

/**
 * Format a UTC ISO timestamp for display in the animation
 * control panel.
 *
 * Strategy:
 * 1. Try to display in the user's local timezone using the
 *    browser's Intl API (most accurate — uses OS timezone)
 * 2. Fall back to UTC display if Intl is unavailable or
 *    throws (e.g. very old browsers)
 *
 * No geolocation or external API calls are made.
 * The browser's own timezone (from OS settings) is used.
 */
export function formatTimestamp(isoString) {
    if (!isoString) return '--:--';

    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '--:--';

        // Get the browser's local timezone from the OS
        const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone;

        // Format in local time with explicit timezone
        const formatted = new Intl.DateTimeFormat(undefined, {
            timeZone:  localTz,
            year:      'numeric',
            month:     '2-digit',
            day:       '2-digit',
            hour:      '2-digit',
            minute:    '2-digit',
            second:    '2-digit',
            hour12:    false,
        }).format(date);

        // Append short timezone name so user knows it's local
        const tzShort = new Intl.DateTimeFormat(undefined, {
            timeZone:     localTz,
            timeZoneName: 'short',
        }).formatToParts(date)
            .find(p => p.type === 'timeZoneName')?.value || '';

        return tzShort ? `${formatted} ${tzShort}` : formatted;

    } catch (err) {
        // Fallback — format as UTC explicitly
        console.warn('[timestamp] Local timezone failed,',
            'falling back to UTC:', err);
        return _formatUtcFallback(isoString);
    }
}

/**
 * UTC fallback formatter.
 * Used when Intl timezone resolution fails.
 * Appends "UTC" suffix so user knows it is not local time.
 */
function _formatUtcFallback(isoString) {
    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '--:--';
        const pad = n => String(n).padStart(2, '0');
        return [
            date.getUTCFullYear(),
            pad(date.getUTCMonth() + 1),
            pad(date.getUTCDate()),
        ].join('-') + ' ' + [
            pad(date.getUTCHours()),
            pad(date.getUTCMinutes()),
            pad(date.getUTCSeconds()),
        ].join(':') + ' UTC';
    } catch {
        return '--:--';
    }
}

/**
 * Pure helper: given the frame list and the current index, return the radar
 * codes that should be "held" (shown from the previous slot) because they are
 * present in frames[frameIndex-1] but absent in frames[frameIndex].
 *
 * One-gap rule: only the immediately prior slot is inspected, so if a radar
 * was already missing at frameIndex-1 the hold is NOT applied.
 *
 * @param {Array}  frames      [{cogsByRadar: {code: cog}}, ...]
 * @param {number} frameIndex  Current frame index
 * @returns {string[]}  Radar codes to hold (may be empty)
 */
export function computeHoldRadarCodes(frames, frameIndex) {
    if (frameIndex <= 0 || !frames[frameIndex] || !frames[frameIndex - 1]) return [];
    const currentRadars = new Set(Object.keys(frames[frameIndex].cogsByRadar || {}));
    return Object.keys(frames[frameIndex - 1].cogsByRadar || {})
        .filter(code => !currentRadars.has(code));
}

export class AnimationController {
    /**
     * @param {import('./map-v2.js').MapManager} mapManager
     */
    constructor(mapManager) {
        this._mapManager      = mapManager;

        // Frame data: set by updateFrames()
        this._frames          = [];      // [{timestamp, cogsByRadar, ...}, ...]
        this._productKey      = null;    // e.g. 'DBZH'
        this._currentFrame    = 0;
        this._playing         = false;
        this._speedMultiplier = 1.0;
        this._lockedToLatest  = false;   // true = hold at last frame; false = wrap to 0

        // rAF state
        this._lastFrameTime   = 0;       // DOMHighResTimeStamp

        // Callbacks
        this._onFrameChange   = null;    // (frameIndex, frameObj) => void
        this._onLockChange    = null;    // (lockedToLatest: bool) => void

        // DOM elements — populated by initControls()
        this._ui          = null;
        this._playPauseBtn = null;
        this._firstFrameBtn = null;
        this._slider      = null;
        this._speedSlider = null;
        this._speedValue  = null;
        this._frameCounter = null;
        this._timeDisplay  = null;
    }

    // =========================================================================
    // Read-only properties
    // =========================================================================

    get isPlaying()    { return this._playing; }
    get currentFrame() { return this._currentFrame; }

    get _frameIntervalMs() {
        return Math.round(1000 / this._speedMultiplier);
    }

    // =========================================================================
    // Controls wiring
    // =========================================================================

    /**
     * Wire animation-related DOM controls via document.getElementById.
     * The UIControls object does not expose these as properties, so we
     * look them up directly from the DOM.
     *
     * @param {Object} ui — UIControls instance (kept for API compatibility)
     */
    initControls(ui) {
        this._ui = ui;

        this._playPauseBtn  = document.getElementById('btn-play-pause');
        const firstBtn       = document.getElementById('btn-first');
        const prevBtn        = document.getElementById('btn-prev');
        const nextBtn        = document.getElementById('btn-next');
        const latestBtn      = document.getElementById('btn-latest');
        this._firstFrameBtn  = firstBtn;
        this._slider         = document.getElementById('animation-slider');
        this._speedSlider    = document.getElementById('speed-slider');
        this._speedValue     = document.getElementById('speed-value');
        this._frameCounter   = document.getElementById('frame-counter');
        this._timeDisplay    = document.getElementById('time-display');

        if (this._playPauseBtn) {
            this._playPauseBtn.addEventListener('click', () => this.toggle());
        }
        if (firstBtn)  firstBtn.addEventListener('click',  () => this.goToFirst());
        if (prevBtn)   prevBtn.addEventListener('click',   () => this.previous());
        if (nextBtn)   nextBtn.addEventListener('click',   () => this.next());
        if (latestBtn) latestBtn.addEventListener('click', () => this.goToLatest());

        if (this._slider) {
            this._slider.addEventListener('input', e => {
                const idx = parseInt(e.target.value, 10);
                if (!isNaN(idx)) this.goToFrame(idx);
            });
        }

        if (this._speedSlider) {
            this._speedSlider.addEventListener('input', e => {
                const multiplier = parseFloat(e.target.value);
                if (!isNaN(multiplier)) {
                    this.setSpeed(multiplier);
                    if (this._speedValue) {
                        this._speedValue.textContent = `${multiplier.toFixed(1)}x`;
                    }
                }
            });
        }
    }

    // =========================================================================
    // Playback control
    // =========================================================================

    play() {
        if (this._playing || this._frames.length <= 1) return;
        this._playing     = true;
        this._lastFrameTime = 0; // force immediate first advance
        this._scheduleLoop();
    }

    pause() {
        this._playing = false;
        this._updatePlayPauseButton();
    }

    toggle() {
        if (this._playing) {
            this.pause();
        } else {
            this.play();
        }
    }

    /** Alias kept for v1 compatibility */
    stop() { this.pause(); }

    // =========================================================================
    // Frame navigation
    // =========================================================================

    goToFrame(index) {
        if (this._frames.length === 0) return;
        const clamped = Math.max(0, Math.min(index, this._frames.length - 1));
        this._currentFrame = clamped;
        this.setLockedToLatest(false);
        this._showCurrentFrame();
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();
    }

    next() {
        if (this._frames.length === 0) return;
        this.setLockedToLatest(false);
        this._currentFrame = this._currentFrame < this._frames.length - 1
            ? this._currentFrame + 1
            : 0;
        this._showCurrentFrame();
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();
    }

    previous() {
        if (this._frames.length === 0) return;
        this.setLockedToLatest(false);
        this._currentFrame = this._currentFrame > 0
            ? this._currentFrame - 1
            : this._frames.length - 1;
        this._showCurrentFrame();
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();
    }

    goToLatest() {
        if (this._frames.length === 0) return;
        this.setLockedToLatest(true);
        this._currentFrame = this._frames.length - 1;
        this._showCurrentFrame();
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();
    }

    goToFirst() {
        if (this._frames.length === 0) return;
        this.setLockedToLatest(false);
        this._currentFrame = 0;
        this._showCurrentFrame();
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();
    }

    // =========================================================================
    // Frame data update
    // =========================================================================

    /**
     * Update the frame list.  Called by app-v2.js after loadFrames() completes,
     * and after incremental live refresh changes.
     *
     * Does not stop animation if it was already playing — the loop continues
     * seamlessly with the new data.
     *
     * @param {Array}  frames     [{timestamp, cogsByRadar, ...}, ...]
     * @param {string} productKey  Currently active product key
     */
    /**
     * @param {Array}  frames
     * @param {string} productKey
     * @param {number|null} currentIndex  Optional explicit frame index to jump to.
     *   If null, the current index is clamped to the new array length.
     */
    updateFrames(frames, productKey, currentIndex = null) {
        const wasPlaying   = this._playing;
        this._productKey   = productKey;
        this._frames       = frames;

        if (currentIndex !== null) {
            this._currentFrame = Math.max(0, Math.min(currentIndex, frames.length - 1));
        } else if (this._currentFrame >= frames.length) {
            // Clamp current frame pointer
            this._currentFrame = Math.max(0, frames.length - 1);
        }

        // Show current frame immediately so the map doesn't go blank
        if (frames.length > 0) {
            this._showCurrentFrame();
        }

        // Update slider range and counters for the new frame list
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();

        // Re-start if was playing but loop died (e.g. frames had been empty)
        if (wasPlaying && !this._playing) {
            this.play();
        }
    }

    // =========================================================================
    // Speed
    // =========================================================================

    setSpeed(multiplier) {
        this._speedMultiplier = multiplier;
    }

    getSpeed() { return this._speedMultiplier; }

    // =========================================================================
    // Getters for app-v2.js
    // =========================================================================

    getFrameCount()     { return this._frames.length; }
    getCurrentIndex()   { return this._currentFrame; }
    getIsPlaying()      { return this._playing; }
    isLockedToLatest()  { return this._lockedToLatest; }
    setLockedToLatest(val) {
        this._lockedToLatest = val;
        if (this._onLockChange) this._onLockChange(val);
    }
    getCurrentFrameObj() {
        return this._frames[this._currentFrame] || null;
    }

    // =========================================================================
    // Callbacks
    // =========================================================================

    setOnFrameChange(cb) { this._onFrameChange = cb; }
    setOnLockChange(cb)  { this._onLockChange  = cb; }

    // =========================================================================
    // Internal
    // =========================================================================

    _scheduleLoop() {
        const loop = (timestamp) => {
            if (!this._playing) {
                this._updatePlayPauseButton();
                return;
            }
            if (this._lastFrameTime === 0 ||
                (timestamp - this._lastFrameTime) >= this._frameIntervalMs) {
                this._tick();
                this._lastFrameTime = timestamp;
            }
            requestAnimationFrame(loop);
        };
        this._updatePlayPauseButton();
        requestAnimationFrame(loop);
    }

    _tick() {
        if (this._frames.length === 0) { this.pause(); return; }
        if (this._currentFrame < this._frames.length - 1) {
            this._currentFrame++;
        } else if (!this._lockedToLatest) {
            this._currentFrame = 0;
        }
        // else: locked to latest — hold at last frame until new data arrives
        this._showCurrentFrame();
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();
    }

    _showCurrentFrame() {
        const i     = this._currentFrame;
        const frame = this._frames[i];
        if (!frame) return;

        const holdCodes = computeHoldRadarCodes(this._frames, i);
        const radarCodes = [
            ...Object.keys(frame.cogsByRadar || {}),
            ...holdCodes,
        ];
        this._mapManager.showFrame(i, radarCodes, this._productKey, holdCodes);

        if (this._onFrameChange) {
            this._onFrameChange(i, frame, holdCodes);
        }
    }

    _updatePlayPauseButton() {
        if (!this._playPauseBtn) return;
        // The SVG holds both icons; toggling .playing swaps which one is visible
        // (see #btn-play-pause rules in styles.css). Do NOT replace innerHTML — that
        // is what made the button jump size/aspect between play and pause states.
        this._playPauseBtn.classList.toggle('playing', this._playing);
        const label = this._playing ? 'Pausar' : 'Reproducir';
        this._playPauseBtn.title = label;
        this._playPauseBtn.setAttribute('aria-label', label);
    }

    _updateSlider() {
        if (!this._slider) return;
        this._slider.max   = Math.max(0, this._frames.length - 1);
        this._slider.value = this._currentFrame;
        // Keep btn-first disabled when already at the first frame
        if (this._firstFrameBtn) {
            this._firstFrameBtn.disabled = (this._frames.length === 0 || this._currentFrame === 0);
        }
    }

    _updateFrameCounter() {
        if (!this._frameCounter) return;
        if (this._frames.length === 0) {
            this._frameCounter.textContent = '0 / 0';
        } else {
            this._frameCounter.textContent = `${this._currentFrame + 1} / ${this._frames.length}`;
        }
    }

    _updateTimeDisplay() {
        if (!this._timeDisplay) return;
        const frame = this._frames[this._currentFrame];
        if (!frame) return;
        const ts = frame.displayTimestamp || frame.timestamp || frame.observation_time;
        if (!ts) return;
        this._timeDisplay.textContent = formatTimestamp(ts);
    }
}
