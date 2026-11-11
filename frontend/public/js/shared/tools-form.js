/**
 * The "Herramientas" form shared by the admin panel and the institution panel: the radar views (lists, as before)
 * plus one checkbox per tool. Today the only tool is storm tracking. Pure helpers: no DOM, testable with node.
 */
import { viewsSummary } from './radar-views.js';

/** "Todas · Tracking", "RMA1, RMA17" or "Ninguna · Tracking": the views summary plus the tools that are on. */
export function toolsSummary(views, tools) {
    const parts = [viewsSummary(views || [])];
    if (tools?.tracking) parts.push('Tracking');
    return parts.join(' · ');
}

/** The tracking checkbox. `note` (optional) is shown under it, for example "No tiene efecto: …". */
export function trackingFieldHtml({ checked = false, note = '' } = {}) {
    return `
        <fieldset class="views-radars"><legend>Herramientas</legend>
            <label class="checkbox-row"><input type="checkbox" name="tracking"${checked ? ' checked' : ''}> Seguimiento de tormentas</label>
            ${note ? `<p class="toolbar-note">${note}</p>` : ''}
        </fieldset>`;
}

/** The tools of a submitted form: {tracking: bool}. */
export function readTools(formData) {
    return { tracking: formData.get('tracking') === 'on' };
}
