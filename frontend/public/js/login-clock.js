// "HORA LOCAL" clock of the login page hero: the time on the visitor's own device, hh:mm:ss, ticking every second.
// Presentation only. The two helpers are pure so they can be unit tested without a browser
// (tests/js/test_login_clock.mjs); the part that touches the page only runs where there is a document.

const two = (value) => String(value).padStart(2, '0');

/** "10:12:30": 24 hour clock, local time, two digits for each part. */
export function formatLocalTime(date) {
    return `${two(date.getHours())}:${two(date.getMinutes())}:${two(date.getSeconds())}`;
}

/**
 * Milliseconds to wait for the next whole second. Scheduling each tick for the start of a second keeps the clock
 * from drifting (a plain setInterval of 1000 ms slowly falls behind). Never 0, so it cannot spin.
 */
export function msUntilNextSecond(date) {
    return 1000 - date.getMilliseconds();
}

function startClock(element) {
    const tick = () => {
        const now = new Date();
        element.textContent = formatLocalTime(now);
        setTimeout(tick, msUntilNextSecond(now));
    };
    tick();
}

if (typeof document !== 'undefined') {
    const element = document.getElementById('login-clock');
    if (element) startClock(element);
}
