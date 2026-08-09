// The endorsements guide's client entry (docs/FRONTEND.md § Modules). esbuild
// bundles this import graph and guide.html.j2 inlines the result.
import { requireClientPayload } from './client-payload.mjs';
import { wireElectionDay } from './election-day.mjs';
import { wireGuide } from './guide-client.mjs';
import { wireMeterTooltips } from './meter-tooltip.mjs';
import { wireShellShare } from './share-link.mjs';

/**
 * Wire the guide.
 *
 * The shell is wired first because none of it depends on the payload: a page
 * whose payload cannot be read still shares, still carries its election-day
 * banner, and its meters — already rendered by the server — still open their
 * tooltips on hover, focus, or tap. Then the payload is admitted, which
 * either hands back the contract the rest of the page reads or stops the
 * page here, on the complete audited baseline the server rendered
 * (docs/FRONTEND.md, The data contract).
 */
export function boot() {
  wireShellShare();
  wireElectionDay();
  wireMeterTooltips();
  wireGuide(/** @type {GuidePayload} */ (requireClientPayload(document)));
}
