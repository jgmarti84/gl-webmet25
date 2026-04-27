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

const BASE_FRAME_INTERVAL_MS = 100; // interval at 1× speed (ms per frame)

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

        // Bound DOM elements — populated by initControls()
        this._ui = null;
    }

    // =========================================================================
    // Read-only properties
    // =========================================================================

    get isPlaying()    { return this._playing; }
    get currentFrame() { return this._currentFrame; }

    get _frameIntervalMs() {
        return Math.round(BASE_FRAME_INTERVAL_MS / this._speedMultiplier);
    }

    // =========================================================================
    // Controls wiring
    // =========================================================================

    /**
     * Wire animation-related DOM controls.
     *
     * @param {Object} ui — same ui object built by app-v2.js containing the
     *   play/pause button, prev/next/latest buttons, frame slider, speed selector.
     */
    initControls(ui) {
        this._ui = ui;

        if (ui.playPauseBtn) {
            ui.playPauseBtn.addEventListener('click', () => this.toggle());
        }
        if (ui.prevFrameBtn) {
            ui.prevFrameBtn.addEventListener('click', () => this.previous());
        }
        if (ui.nextFrameBtn) {
            ui.nextFrameBtn.addEventListener('click', () => this.next());
        }
        if (ui.latestFrameBtn) {
            ui.latestFrameBtn.addEventListener('click', () => this.goToLatest());
        }

        if (ui.frameSlider) {
            ui.frameSlider.addEventListener('input', e => {
                const idx = parseInt(e.target.value, 10);
                if (!isNaN(idx)) this.goToFrame(idx);
            });
        }

        if (ui.speedSelect) {
            ui.speedSelect.addEventListener('change', e => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v)) this.setSpeed(v);
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
    }

    next() {
        if (this._frames.length === 0) return;
        this._currentFrame = this._currentFrame < this._frames.length - 1
            ? this._currentFrame + 1
            : 0;
        this._showCurrentFrame();
    }

    previous() {
        if (this._frames.length === 0) return;
        this._currentFrame = this._currentFrame > 0
            ? this._currentFrame - 1
            : this._frames.length - 1;
        this._showCurrentFrame();
    }

    goToLatest() {
        if (this._frames.length === 0) return;
        this._currentFrame = this._frames.length - 1;
        this._showCurrentFrame();
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
        if (!this._ui || !this._ui.playPauseBtn) return;
        this._ui.playPauseBtn.textContent = this._playing ? 'Pause' : 'Play';
        this._ui.playPauseBtn.classList.toggle('playing', this._playing);
    }
}
