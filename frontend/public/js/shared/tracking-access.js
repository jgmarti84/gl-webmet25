/**
 * Who may use the storm tracking tool of the single-radar view.
 *
 * The one place that decides it. Today the rule is "whoever can open this
 * radar's view": the tool lives inside that view. When the per-radar tracking
 * permission exists (design doc §15.5), GET /permissions/me will also return
 * `radar_tracking: [codes]` and only this function changes.
 *
 * No DOM here, so it can be tested with node.
 */
import { canOpenDetailView } from './radar-views.js';

/**
 * @param {string} code        radar code of the view
 * @param {object} permissions the body of GET /permissions/me
 */
export function canUseTracking(code, permissions) {
    return canOpenDetailView(code, permissions?.radar_detail_views);
}
