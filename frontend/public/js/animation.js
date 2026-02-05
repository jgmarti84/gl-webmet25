/**
 * Animation Module - Handles animation controls and playback
 */

export class AnimationController {
    constructor() {
        this.isPlaying = false;
        this.currentIndex = 0;
        this.frames = [];
        this.speed = 1.0; // 1x speed
        this.interval = null;
        this.onFrameChange = null;
        this.loop = true;
    }
    
    /**
     * Set the frames to animate through
     */
    setFrames(frames) {
        this.frames = frames;
        this.currentIndex = 0;
        this.stop();
    }
    
    /**
     * Set callback for frame changes
     */
    setOnFrameChange(callback) {
        this.onFrameChange = callback;
    }
    
    /**
     * Get current frame
     */
    getCurrentFrame() {
        if (this.frames.length === 0) return null;
        return this.frames[this.currentIndex];
    }
    
    /**
     * Get current index
     */
    getCurrentIndex() {
        return this.currentIndex;
    }
    
    /**
     * Get total frame count
     */
    getFrameCount() {
        return this.frames.length;
    }
    
    /**
     * Go to specific frame
     */
    goToFrame(index) {
        if (index < 0 || index >= this.frames.length) return;
        
        this.currentIndex = index;
        if (this.onFrameChange) {
            this.onFrameChange(this.currentIndex, this.frames[this.currentIndex]);
        }
    }
    
    /**
     * Go to next frame
     */
    next() {
        if (this.frames.length === 0) return;
        
        if (this.currentIndex < this.frames.length - 1) {
            this.currentIndex++;
        } else if (this.loop) {
            this.currentIndex = 0;
        }
        
        if (this.onFrameChange) {
            this.onFrameChange(this.currentIndex, this.frames[this.currentIndex]);
        }
    }
    
    /**
     * Go to previous frame
     */
    previous() {
        if (this.frames.length === 0) return;
        
        if (this.currentIndex > 0) {
            this.currentIndex--;
        } else if (this.loop) {
            this.currentIndex = this.frames.length - 1;
        }
        
        if (this.onFrameChange) {
            this.onFrameChange(this.currentIndex, this.frames[this.currentIndex]);
        }
    }
    
    /**
     * Go to latest frame (first in array)
     */
    goToLatest() {
        if (this.frames.length === 0) return;
        this.goToFrame(0);
    }
    
    /**
     * Set animation speed
     */
    setSpeed(speed) {
        this.speed = speed;
        if (this.isPlaying) {
            this.stop();
            this.play();
        }
    }
    
    /**
     * Get animation speed
     */
    getSpeed() {
        return this.speed;
    }
    
    /**
     * Start animation
     */
    play() {
        if (this.frames.length <= 1) return;
        
        this.isPlaying = true;
        
        // Base interval is 1000ms, adjusted by speed
        const intervalMs = 1000 / this.speed;
        
        this.interval = setInterval(() => {
            this.next();
        }, intervalMs);
    }
    
    /**
     * Stop animation
     */
    stop() {
        this.isPlaying = false;
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }
    
    /**
     * Toggle play/pause
     */
    toggle() {
        if (this.isPlaying) {
            this.stop();
        } else {
            this.play();
        }
    }
    
    /**
     * Check if playing
     */
    getIsPlaying() {
        return this.isPlaying;
    }
}
