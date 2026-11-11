/**
 * Who may use the storm tracking tool of the single-radar view: the one place that decides it on the page.
 *
 * Both are needed: the view of this radar AND the tracking tool (GET /permissions/me, already intersected with the
 * institution). The server checks the same thing (nginx asks /auth/check before a per-radar tracking request);
 * here it only decides whether the button is shown. No DOM here, so it can be tested with node.
 */
import { canOpenDetailView } from './radar-views.js';

/**
 * @param {string} code        radar code of the view
 * @param {object} permissions the body of GET /permissions/me
 */
export function canUseTracking(code, permissions) {
    return canOpenDetailView(code, permissions?.radar_detail_views) && permissions?.tools?.tracking === true;
}
