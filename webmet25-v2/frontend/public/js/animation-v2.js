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

        // rAF state
        this._lastFrameTime   = 0;       // DOMHighResTimeStamp

        // Callback invoked after each frame advance so app-v2.js can update UI
        this._onFrameChange   = null;    // (frameIndex, frameObj) => void

        // DOM elements — populated by initControls()
        this._ui          = null;
        this._playPauseBtn = null;
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
        const prevBtn        = document.getElementById('btn-prev');
        const nextBtn        = document.getElementById('btn-next');
        const latestBtn      = document.getElementById('btn-latest');
        this._slider         = document.getElementById('animation-slider');
        this._speedSlider    = document.getElementById('speed-slider');
        this._speedValue     = document.getElementById('speed-value');
        this._frameCounter   = document.getElementById('frame-counter');
        this._timeDisplay    = document.getElementById('time-display');

        if (this._playPauseBtn) {
            this._playPauseBtn.addEventListener('click', () => this.toggle());
        }
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
        this._showCurrentFrame();
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();
    }

    next() {
        if (this._frames.length === 0) return;
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
        this._currentFrame = this._frames.length - 1;
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
    getCurrentFrameObj() {
        return this._frames[this._currentFrame] || null;
    }

    // =========================================================================
    // Callbacks
    // =========================================================================

    setOnFrameChange(cb) { this._onFrameChange = cb; }

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
        this._currentFrame = this._currentFrame < this._frames.length - 1
            ? this._currentFrame + 1
            : 0;
        this._showCurrentFrame();
        this._updateSlider();
        this._updateFrameCounter();
        this._updateTimeDisplay();
    }

    _showCurrentFrame() {
        const frame = this._frames[this._currentFrame];
        if (!frame) return;

        const radarCodes = Object.keys(frame.cogsByRadar || {});
        this._mapManager.showFrame(this._currentFrame, radarCodes, this._productKey);

        if (this._onFrameChange) {
            this._onFrameChange(this._currentFrame, frame);
        }
    }

    _updatePlayPauseButton() {
        if (!this._playPauseBtn) return;
        this._playPauseBtn.innerHTML = this._playing ? '&#9646;&#9646;' : '&#9654;';
        this._playPauseBtn.classList.toggle('playing', this._playing);
    }

    _updateSlider() {
        if (!this._slider) return;
        this._slider.max   = Math.max(0, this._frames.length - 1);
        this._slider.value = this._currentFrame;
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
        const ts = frame.timestamp || frame.observation_time;
        if (!ts) return;
        const d = new Date(ts);
        const pad = n => String(n).padStart(2, '0');
        this._timeDisplay.textContent =
            `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} ` +
            `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
    }
}
