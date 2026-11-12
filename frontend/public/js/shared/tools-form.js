/**
 * The "Herramientas" form shared by the admin panel and the institution panel: the radar views (lists, as before)
 * plus one checkbox per tool. Pure helpers: no DOM, testable with node.
 *
 * TOOL_LIST is the one list of tools on the page. To add a tool, add its entry here (key = the name the API uses in
 * `tools`, label = the checkbox text, short = the word in the tables); the form, the summaries and the readers below
 * follow it. The backend list is `TOOLS` in api/app/auth/permissions.py (see "How to add a tool" in docs/OPERATIONS.md).
 */
import { viewsSummary } from './radar-views.js';

export const TOOL_LIST = [{ key: 'tracking', label: 'Seguimiento de tormentas', short: 'Tracking' }];

/** "Todas · Tracking", "RMA1, RMA17" or "Ninguna · Tracking": the views summary plus the tools that are on. */
export function toolsSummary(views, tools) {
    const parts = [viewsSummary(views || [])];
    for (const tool of TOOL_LIST) {
        if (tools?.[tool.key]) parts.push(tool.short);
    }
    return parts.join(' · ');
}

/**
 * The "Herramientas" cell of a users table: one line with the person's own list and one with their institution's, so
 * it is clear which of the two a tool comes from (an institution admin uses the institution's list, so their own is
 * shown grey). `org` is the institution as the API returns it ({radar_detail_views, tools}) or null. `esc` escapes
 * text for HTML. `showInstitution: false` (the institution panel, where it is always the same institution) leaves just
 * the own summary, without labels.
 */
export function toolsCellHtml(user, org, esc, { showInstitution = true } = {}) {
    const own = toolsSummary(user.radar_detail_views, user.tools);
    if (!org || !showInstitution) return esc(own);
    const line = (label, text, muted = false) =>
        `<div class="cell-line${muted ? ' cell-line--muted' : ''}"><span class="cell-label">${label}</span> ${esc(text)}</div>`;
    const ignored = user.role === 'org_admin';
    return (
        line('Propias:', ignored ? `${own} (no se usan)` : own, ignored) +
        line('Institución:', toolsSummary(org.radar_detail_views, org.tools))
    );
}

/**
 * One checkbox per tool, in a "Herramientas" fieldset (the checkbox of a tool is named `tool_<key>`).
 * `values`: {key: bool} of what is ticked. `notes`: {key: text} shown under that tool, for example "No tiene efecto".
 * `only`: {key: bool}, the tools the institution has; when given, only the tools that are true there are offered
 * (an institution cannot give what it does not have), and an empty string comes back if there is none.
 */
export function toolsFieldsHtml({ values = {}, notes = {}, only = null } = {}) {
    const offered = TOOL_LIST.filter((tool) => only === null || only[tool.key] === true);
    if (!offered.length) return '';
    const rows = offered
        .map(
            (tool) => `
            <label class="checkbox-row"><input type="checkbox" name="tool_${tool.key}"${values[tool.key] ? ' checked' : ''}> ${tool.label}</label>
            ${notes[tool.key] ? `<p class="toolbar-note">${notes[tool.key]}</p>` : ''}`,
        )
        .join('');
    return `<fieldset class="views-radars"><legend>Herramientas</legend>${rows}</fieldset>`;
}

/** The tools of a submitted form as {key: bool}. With `only` (see toolsFieldsHtml), just the tools that were offered. */
export function readTools(formData, only = null) {
    const tools = {};
    for (const tool of TOOL_LIST) {
        if (only !== null && only[tool.key] !== true) continue;
        tools[tool.key] = formData.get(`tool_${tool.key}`) === 'on';
    }
    return tools;
}

/** True when the answer of GET /permissions/me says the user has this tool. */
export function hasTool(permissions, key) {
    return permissions?.tools?.[key] === true;
}
