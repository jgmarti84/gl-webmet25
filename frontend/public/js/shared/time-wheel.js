/**
 * TimeWheel — a compact, iOS-style scrolling HH:MM time picker.
 *
 * Renders two scroll-snapping columns (hours 00–23, minutes 00–59) with a
 * centered selection band. Emits `onChange(hour, minute)` after the user
 * settles on a value. The host is responsible for combining this with a date.
 *
 * Because scroll position cannot be set while the element is hidden, call
 * `refresh()` whenever the wheel becomes visible to re-center the selection.
 */

const ITEM_HEIGHT = 36; // px — must match .tw-item height in CSS

export class TimeWheel {
    constructor(container, { onChange } = {}) {
        this.container = container;
        this.onChange = onChange || (() => {});
        this.hour = 0;
        this.minute = 0;
        this._build();
    }

    _itemsHtml(count) {
        let html = '';
        for (let i = 0; i < count; i += 1) {
            html += `<div class="tw-item">${String(i).padStart(2, '0')}</div>`;
        }
        return html;
    }

    _build() {
        this.container.classList.add('time-wheel');
        this.container.innerHTML = `
            <div class="tw-col" data-unit="h"><div class="tw-list">${this._itemsHtml(24)}</div></div>
            <div class="tw-sep">:</div>
            <div class="tw-col" data-unit="m"><div class="tw-list">${this._itemsHtml(60)}</div></div>
            <div class="tw-selection" aria-hidden="true"></div>`;
        this.hCol = this.container.querySelector('[data-unit="h"]');
        this.mCol = this.container.querySelector('[data-unit="m"]');
        this._bindColumn(this.hCol, 24, 'hour');
        this._bindColumn(this.mCol, 60, 'minute');
    }

    _highlight(col, index) {
        col.querySelectorAll('.tw-item').forEach((el, i) => {
            el.classList.toggle('tw-active', i === index);
        });
    }

    _bindColumn(col, count, prop) {
        let settleTimer = null;
        const clampIndex = (idx) => Math.max(0, Math.min(count - 1, idx));

        col.addEventListener('scroll', () => {
            // Live highlight while scrolling.
            this._highlight(col, clampIndex(Math.round(col.scrollTop / ITEM_HEIGHT)));
            clearTimeout(settleTimer);
            settleTimer = setTimeout(() => {
                const index = clampIndex(Math.round(col.scrollTop / ITEM_HEIGHT));
                this[prop] = index;
                this._highlight(col, index);
                col.scrollTo({ top: index * ITEM_HEIGHT, behavior: 'smooth' });
                this.onChange(this.hour, this.minute);
            }, 120);
        });

        // Tap an item to select it directly.
        col.addEventListener('click', (event) => {
            const item = event.target.closest('.tw-item');
            if (!item) return;
            const index = clampIndex([...col.querySelectorAll('.tw-item')].indexOf(item));
            this[prop] = index;
            col.scrollTo({ top: index * ITEM_HEIGHT, behavior: 'smooth' });
            this._highlight(col, index);
            this.onChange(this.hour, this.minute);
        });
    }

    /** Set the wheel to a given hour/minute without firing onChange. */
    set(hour, minute) {
        this.hour = Math.max(0, Math.min(23, Number(hour) || 0));
        this.minute = Math.max(0, Math.min(59, Number(minute) || 0));
        this.refresh();
    }

    /** Re-apply scroll positions + highlight (call when the wheel becomes visible). */
    refresh() {
        this.hCol.scrollTop = this.hour * ITEM_HEIGHT;
        this.mCol.scrollTop = this.minute * ITEM_HEIGHT;
        this._highlight(this.hCol, this.hour);
        this._highlight(this.mCol, this.minute);
    }
}
