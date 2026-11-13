/**
 * The "Herramientas" form shared by the admin panel and the institution panel: the radar views (lists, as before)
 * plus one checkbox per tool. Pure helpers: no DOM, testable with node.
 *
 * TOOL_LIST is the one list of tools on the page. To add a tool, add its entry here (key = the name the API uses in
 * `tools`, label = the checkbox text, short = the word in the tables); the form, the summaries and the readers below
 * follow it. The backend list is `TOOLS` in api/app/auth/permissions.py (see "How to add a tool" in docs/OPERATIONS.md).
 */
import { ALL_RADARS, viewsSummary } from './radar-views.js';

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
 * The views a person can really open, as a saved-style list (codes or ["*"]). A reader of an institution needs the view
 * in its own list AND in the institution's; an institution admin uses the institution's list; no institution means
 * the own list. Mirrors effective_radar_views in api/app/auth/permissions.py, but on saved lists (where "*" is every
 * radar) instead of the real codes.
 */
function effectiveViews(user, org) {
    const own = user.radar_detail_views || [];
    if (!org) return own;
    const company = org.radar_detail_views || [];
    if (user.role === 'org_admin') return company;
    if (own.includes(ALL_RADARS)) return company;
    if (company.includes(ALL_RADARS)) return own;
    return own.filter((code) => company.includes(code));
}

/** The tools a person can really use, {key: bool}: own AND the institution's (an institution admin: the institution's). */
function effectiveToolFlags(user, org) {
    const flags = {};
    for (const tool of TOOL_LIST) {
        const own = user.tools?.[tool.key] === true;
        const company = org?.tools?.[tool.key] === true;
        if (!org) flags[tool.key] = own;
        else flags[tool.key] = user.role === 'org_admin' ? company : own && company;
    }
    return flags;
}

/**
 * What the "Herramientas" column of a users table shows: the views and tools the person really has, in one text. A
 * person with no institution has their own; an institution admin has the institution's; a reader of an institution has
 * their own, as far as the institution has them too. `org` is the institution as the API returns it
 * ({radar_detail_views, tools}) or null.
 */
export function usableToolsSummary(user, org) {
    return toolsSummary(effectiveViews(user, org), effectiveToolFlags(user, org));
}

/**
 * What a reader of an institution is being given that the institution does not have, so it would do nothing (a reader
 * has what it was given AND what the institution has). `views` are the saved-style codes being ticked (["*"] for
 * "Todas"), `tools` is {key: bool}, `org` is the institution ({radar_detail_views, tools}). Returns
 * {all: true when "Todas" goes beyond the institution's list, radars: codes the institution lacks, tools: labels}.
 */
export function beyondInstitution(views, tools, org) {
    const companyViews = org.radar_detail_views || [];
    const companyAll = companyViews.includes(ALL_RADARS);
    const result = { all: false, radars: [], tools: [] };
    if (views.includes(ALL_RADARS)) result.all = !companyAll;
    else if (!companyAll) result.radars = views.filter((code) => !companyViews.includes(code));
    for (const tool of TOOL_LIST) {
        if (tools?.[tool.key] && !org.tools?.[tool.key]) result.tools.push(tool.label);
    }
    return result;
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
